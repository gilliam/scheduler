# Copyright 2013 Johan Rydberg.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from gevent.event import Event
import gevent
import requests
import json
import logging

from glock.task import LoopingCall


class _Container(dict):
    __getattr__ = dict.get


class _APIClient(object):

    def __init__(self, httpclient, name, formation):
        self.httpclient = httpclient
        self.name = name
        self.formation = formation

    @property
    def _url(self):
        return 'http://%s.api.%s.service:9000' % (self.name,
                                                  self.formation)

    def _build_container_request(self, instance):
        return {
            'image': instance.image, 'command': instance.command,
            'formation': instance.formation, 'service': instance.service,
            'instance': instance.instance, 'env': instance.env or {},
            'ports': instance.ports or []
            }

    # methods for talking to the executor via the API.  break out
    # these into a client of their own?

    def create(self, inst):
        request = self._build_container_request(inst)
        response = self.httpclient.post('%s/container' % (self._url,),
                                        data=json.dumps(request))
        response.raise_for_status()
        return _Container(**response.json())

    def restart(self, cid, inst):
        request = self._build_container_request(inst)
        response = self.httpclient.put('%s/container/%s' % (self._url, cid),
                                       data=json.dumps(request))
        response.raise_for_status()
        return _Container(**response.json())

    def delete(self, cid):
        response = self.httpclient.delete('%s/container/%s' % (
                self._url, cid))
        response.raise_for_status()

    def containers(self):
        response = self.httpclient.get('%s/container' % (self._url,))
        response.raise_for_status()
        return {cid: _Container(**value)
                for (cid, value) in response.json().iteritems()}


class ExecutorError(Exception):
    pass


class DispatchError(ExecutorError):
    pass


class _ExecutorController(object):

    def __init__(self, clock, name, apiclient, store_query, interval):
        self.log = logging.getLogger('executor.controller.%s' % (name,))
        self.name = name
        self.apiclient = apiclient
        self.store_query = store_query
        self.interval = interval
        self._problematic = True
        self._terminated = []
        self._containers = {}
        self._task = LoopingCall(clock, self._check_status)
        self._started = Event()

    def containers(self):
        return self._containers.keys()

    def start(self):
        self._task.start(self.interval)
        self._started.wait()
        return self

    def dispatch(self, inst):
        container = self._handle_error(self.apiclient.create, inst)
        self._remember(container.id, container)

    def statuses(self, instances):
        for instance in instances:
            container = self.find(instance)
            yield (container.state if container is not None
                   else 'unknown')

    def delete(self, instance):
        """Delete instance."""
        container = self.find(instance)
        if container is not None:
            self._forget(container.id)
            try:
                self._handle_error(self.apiclient.delete, container.id)
            except Exception:
                self._terminated.add(container.id)
                raise

    def restart(self, instance):
        container = self.find(instance)
        if container is not None:
            container = self._handle_error(
                self.apiclient.restart, container.id, instance)
            self._remember(container.id, container)

    def _check_status(self):
        try:
            containers = self.apiclient.containers()
        except Exception:
            raise
        else:
            if self._problematic:
                self._reconcile(containers)
                self._problematic = False
            for id, container in containers.items():
                self._remember(id, container)
            self._update_state()
        self._started.set()

    def _update_state(self):
        for id, container in self._containers.items():
            if container.state == 'error':
                inst = self._geti(container)
                if inst is not None and inst.state != inst.STATE_LOST:
                    inst.set_state(inst.STATE_LOST)

    def _reconcile(self, containers):
        self._reconcile_missing_containers(containers)
        self._mark_lost_containers_as_lost(containers)
        self._delete_terminated_containers(containers)

    def _reconcile_missing_containers(self, containers):
        missing = (set(containers)
                   - set(self._containers)
                   - set(self._terminated))
        self.log.info("reconscile: %s" % (', '.join(missing)))
        for cid, state in [(cid, containers[cid]) for cid in missing]:
            if self._geti(state) is not None:
                self._remember(cid, state)
            # FIXME: what to do with containers where the instance
            # cannot be found?  at what stage do we remove them?
            # NOW!?  self._delete_container(cid)

    def _mark_lost_containers_as_lost(self, containers):
        missing = set(self._containers) - set(containers)
        self.log.info("mark containers %s as lost" % (
                ', '.join(missing)))
        for state in [self._containers[cid] for cid in missing]:
            inst = self._geti(state)
            if inst is not None and inst.state != inst.STATE_LOST:
                inst.set_state(inst.STATE_LOST)

    def _delete_terminated_containers(self, containers):
        for cid in self._terminated:
            if cid in containers:
                self._client.delete(cid)
        del self._terminated[:]

    def _handle_error(self, m, *args, **kwargs):
        if self._problematic:
            raise DispatchError("problematic")
        try:
            return m(*args, **kwargs)
        except Exception, err:
            self._problematic = True
            raise DispatchError(str(err))

    def _geti(self, container):
        return self.store_query.get(container.formation,
                                    container.service,
                                    container.instance)

    def find(self, inst):
        """Lookup container based on instance."""
        for container in self._containers.itervalues():
            if (container.formation == inst.formation
                   and container.service == inst.service
                   and container.instance == inst.instance):
                return container
        return None

    def _remember(self, cid, container):
        self._containers[cid] = container

    def _forget(self, cid):
        del self._containers[cid]


class ExecutorManager(object):

    def __init__(self, clock, registry, store_query, interval,
                 formation='executor'):
        self.clock = clock
        self.registry = registry
        self.store_query = store_query
        self.check_interval = interval
        self.formation = formation
        self._form_cache = None
        self._client = {}

    def start(self):
        """Start manager."""
        self._form_cache = self.registry.formation_cache(self.formation)
        for name, data in self._form_cache.query().items():
            self._create(data['instance'])
        # FIXME: make sure that we re-populate with new entries.

    def get(self, name):
        return self._client.get(name)

    def clients(self):
        return self._client.values()

    def _create(self, name):
        """Create ..."""
        apiclient = _APIClient(requests.Session(), name, self.formation)
        self._client[name] = _ExecutorController(
            self.clock, name, apiclient, self.store_query,
            self.check_interval).start()

    def dispatch(self, inst, name):
        """Dispatch C{inst} to C{name}."""
        logging.info("DISPATCH %r to %s: %r" % (inst, name, self._client))
        self.get(name).dispatch(inst)

    def restart(self, inst):
        self.get(inst.assigned_to).restart(inst)

    def terminate(self, inst):
        self.get(inst.assigned_to).delete(inst)

    def wait(self, instance, name, timeout=None):
        """Wait an instance to boot or to fail."""
        client = self.get(name)
        with gevent.Timeout(timeout):
            while True:
                status, = client.statuses([instance])
                if status in ('running', 'fail', 'done', 'error'):
                    return status
                self.clock.sleep(5)

    def containers(self, instances):
        """Return containers for instances."""
        for instance in instances:
            if instance.assigned_to is None:
                yield None
            else:
                client = self.get(instance.assigned_to)
                yield client.find(instance)
