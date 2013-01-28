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
from requests.exceptions import RequestException
from glock.task import LoopingCall


class _Hypervisor(object):

    def __init__(self, log, clock, model, interval, proc_store,
                 requests=requests):
        self.log = log
        self.clock = clock
        self.model = model
        self.proc_store = proc_store
        self._health_check = LoopingCall(clock, self._check)
        self._interval = interval
        self.requests = requests
        self.base_url = 'http://%s:6000/proc' % (self.model.host,)

    def start(self):
        """Start interacting with the remote hypervisor."""
        self._health_check.start(self._interval)

    def _encode_proc_name(self, proc):
        # We do not want to have dots in the name (routes issues).
        # and dash may be used in the app name.
        return '%s_%d_%s_%s' % (proc.app.name, 
                                proc.deploy,
                                proc.name,
                                proc.proc_id)

    def _check(self):
        procs = dict([(self._encode_proc_name(proc), proc)
            for proc in self.proc_store.procs_for_hypervisor(self.model)])
        unwanted_proc = set()
        seen_proc = set()

        uri = 'http://%s:6000/proc' % (self.model.host,)
        while uri is not None:
            try:
                response = self.requests.get(uri)
                response.raise_for_status()
            except RequestException, re:
                self.log.error('could not talk to hypervisor: %r' % (re,))
                # Just return.  We'll retry in a few anyway.
                return

            data = response.json()
            uri = data.get('_links', {}).get('next')
            for proc_name, spec in data.iteritems():
                if proc_name == '_links':
                    continue
                proc = procs.get(proc_name)
                if proc is None:
                    unwanted_proc.add(proc_name)
                elif proc.state in ('stop',):
                    unwanted_proc.add(proc_name)
                seen_proc.add(proc_name)
        for proc_name in unwanted_proc:
            self._stop_proc(proc_name)

        # For processes that were missing (and that has not state
        # init), we just remove them straight away.

        missing_procs = set(procs.keys()) - seen_proc
        for proc_name in missing_procs:
            proc = procs[proc_name]
            if proc.state in (u'running', u'boot'):
                self.proc_store.set_state(proc, u'abort')

    def spawn_proc(self, proc, callback_url, image, command, config):
        """Spawn a new process."""
        self.log.info('spawn new proc(%s, %s): command=%r' % (
                proc.name, proc.proc_id, command))
        try:
            request = {'name': self._encode_proc_name(proc),
                       'image': image, 'command': command,
                       'config': config, 'callback': callback_url}
            response = self.requests.post(self.base_url,
                data=json.dumps(request))
            response.raise_for_status()
        except RequestException, re:
            self.log.error('could not talk to hypervisor: %r' % (re,))
            # Just return.  We'll retry in a few anyway.

    def _stop_proc(self, proc_name):
        try:
            response = self.requests.delete('%s/%s' % (self.base_url, proc_name))
            response.raise_for_status()
        except RequestException:
            self.log.exception(
                "failed to remove proc %s from hypervisor" % (
                    proc))
            # FIXME: retry?

    def stop_proc(self, proc):
        """Stop process on remote hypervisor."""
        self._stop_proc(self._encode_proc_name(proc))


class HypervisorService(object):

    def __init__(self, log, clock, store, proc_store, interval=30):
        self.log = log
        self.clock = clock
        self.store = store
        self.proc_store = proc_store
        self._hypervisors = {}
        self.interval = 30

    def hypervisors():
        return self._hypervisors.itervalues()

    def start(self):
        for hypervisor in self.store.items:
            self._start_hypervisor(hypervisor)

    def create(self, *args):
        model = self.store.create(*args)
        return self._start_hypervisor(model)

    def remove(self, model):
        self._stop_hypervisor(model)
        self.store.remove(model)

    def get(self, host):
        model = self.store.by_host(host)
        return (self._hypervisors.get(model.id)
                if model is not None else none)

    def _start_hypervisor(self, model):
        self._hypervisors[model.id] = _hypervisor = _Hypervisor(
            self.log.getChild(model.host), self.clock, model,
            self.interval, self.proc_store)
        _hypervisor.start()
        return _hypervisor

    def _stop_hypervisor(self, model):
        _hypervisor = self._hypervisors.pop(model.id, None)
        if _hypervisor is not None:
            _hypervisor.stop()



