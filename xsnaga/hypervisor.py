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

import requests
import json
from urlparse import urljoin
from requests.exceptions import RequestException
from glock.task import LoopingCall

from .util import async


class APIError(Exception):
    pass


class _HypervisorAPI(object):
    """Abstraction of the REST API that a hypervisor exposes."""

    def __init__(self, log, http, hypervisor):
        self.log = log
        self.http = http
        self.hypervisor = hypervisor

    def index(self):
        """Given a hypervisor and something that can do HTTP requests for
        us try to iterate over all remote procs.
        """
        try:
            page_url = self.hypervisor.proc_url()
            while page_url is not None:
                response = self.http.get(page_url)
                response.raise_for_status()
                data = response.json()
                page_url = data.get('links', {}).get('next')
                for proc_name, spec in data.iteritems():
                    if proc_name == 'links':
                        continue
                    yield spec
        except RequestException:
            self.log.exception("index error")
            raise APIError()

    def create(self, app, name, image, command, config, callback):
        try:
            data = {'app': app, 'name': name, 'image': image,
                    'command': command, 'config': config,
                    'callback': callback}
            response = self.http.post(self.hypervisor.proc_url(),
                                      data=json.dumps(data))
            response.raise_for_status()
            return urljoin(self.hypervisor.proc_url(),
                           response.headers.get('Location'))
        except RequestException:
            self.log.exception("failed to create %s:%s" % (app, name))
            raise APIError()

    def delete(self, entity):
        try:
            response = self.http.delete(urljoin(
                self.hypervisor.proc_url(), entity))
            response.raise_for_status()
        except RequestException:
            self.log.exception("failed to delete proc")
            raise APIError()


class HypervisorClient(object):

    def __init__(self, log, clock, interval, proc_store,
                 app_store, model, http=requests):
        self.log = log
        self.clock = clock
        self.interval = interval
        self.proc_store = proc_store
        self.app_store = app_store
        self.model = model
        self._health_check = LoopingCall(clock, self._check)
        self._api = _HypervisorAPI(log, http, model)

    def start(self):
        """Start interacting with the remote hypervisor."""
        self._health_check.start(self.interval)

    def spawn_proc(self, proc, app, release, callback):
        """Spawn proc on the hypervisor.

        @param proc: The proc that should be created on the
            hypervisor.

        @param callback: State change callback URL for the proc.

        @param command: The command that should be executed inside the
            container.
        """
        try:
            proc.cont_entity = unicode(self._api.create(
                app.name, proc.proc_name, release.image,
                release.pstable[proc.proc_type], release.config,
                callback))
            self.proc_store.persist(proc)
        except APIError:
            # Could not create the proc for some reason.
            pass

    def stop_proc(self, proc):
        """Stop process on remote hypervisor."""
        if proc.cont_entity:
            self._api.delete(proc.cont_entity)

    def _check(self):
        """Perform check and sync state with hypervisor."""
        toremove = set()
        seen = set()
        try:
            pmap = self._make_proc_app_name_map()
            for remote_proc in self._api.index():
                unwanted = self._check_remote_proc(remote_proc, pmap)
                if unwanted:
                    toremove.add(unwanted)
                else:
                    seen.add((remote_proc['app'], remote_proc['name']))
        except APIError:
            pass
        else:
            self._change_state_of_missing_procs(pmap, seen)

        # If we got any processes we should try to delete do so now.
        self._terminate_procs(toremove)

    def _check_remote_proc(self, remote_proc, pmap):
        proc = pmap.get((remote_proc['app'], remote_proc['name']))
        if proc is not None:
            self._update_proc_state(proc, remote_proc['state'])
        if proc is None or proc.desired_state in (u'stop', u'abort'):
            return remote_proc['links']['self']

    def _change_state_of_missing_procs(self, pmap, seen):
        missing = set(pmap.keys()) - set(seen)
        for proc in (pmap[k] for k in missing):
            self.proc_store.set_actual_state(proc, u'fail')
        
    def _make_proc_app_name_map(self):
        pmap = {}
        for proc in self.proc_store.for_hypervisor(self.model):
            app = self.app_store.get(proc.app_id)
            pmap[(app.name, proc.proc_name)] = proc
        return pmap

    def _update_proc_state(self, proc, remote_state):
        """Given the remote state of a proc, see if the proc model
        state should be updated to reflect the remote state.
        """
        if proc.actual_state != remote_state:
            self.proc_store.set_actual_state(proc, remote_state)

    def _terminate_procs(self, entities):
        for entity in entities:
            # We do not know if the entity URLs are qualified or just
            # a path so we join with the base URL of the proc
            # collection.
            try:
                self._api.delete(entity)
            except APIError:
                pass


class HypervisorController(object):
    """Controller of hypervisors that acts upon events on the
    eventbus.
    """

    def __init__(self, eventbus, store, factory):
        self.eventbus = eventbus
        self.store = store
        self.factory = factory
        self._clients = {}

    def start(self):
        for hypervisor in self.store.all():
            self._hypervisor_create(hypervisor)
        # listen for hypervisor events
        self.eventbus.on('hypervisor-create', async(self._hypervisor_create))
        self.eventbus.on('hypervisor-dispose', async(self._hypervisor_dispose))
        # listen for proc events
        self.eventbus.on('proc-create', async(self._proc_create))
        self.eventbus.on('proc-dispose', async(self._proc_dispose))
        
    def _proc_create(self, proc, app, release, callback):
        """Create a proc on a hypervisor."""
        self._clients.get(proc.hypervisor_id).spawn_proc(
            proc, app, release, callback)

    def _proc_dispose(self, proc):
        """Dispose a proc."""
        self._clients.get(proc.hypervisor_id).stop_proc(proc)

    def _hypervisor_create(self, model):
        self._clients[model.id] = client = self.factory(model)
        client.start()

    def _hypervisor_dispose(self, model):
        client = self._clients.pop(model.id, None)
        if client is not None:
            client.stop()
