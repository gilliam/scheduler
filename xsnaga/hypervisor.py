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


class _Hypervisor(object):

    def __init__(self, log, clock, model, interval, proc_store,
                 requests=requests):
        self.log = log
        self.clock = clock
        self.model = model
        self._proc_store = proc_store
        self._health_check = LoopingCall(clock, self._check)
        self._interval = interval

    def start(self):
        """Start interacting with the remote hypervisor."""
        self._health_check.start(self._interval)

    def _encode_proc_name(self, proc):
        return '%s.%d.%s.%s' % (proc.app.name, 
                                proc.deploy.id,
                                proc.name,
                                proc.proc_id)

    def _check(self):
        procs = dict([(self._encode_proc_name(proc), proc)
            for proc in self._proc_store.procs_for_hypervisor(self.model)])
        unwanted_proc = set()

        uri = 'http://%s/proc' % (self.model.host,)
        while uri is not None:
            response = self.requests.get(uri)
            response.raise_for_status()
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
        for proc_name in unwanted_proc:
            self._stop_proc(procs.get(proc_name))

    def _spawn_proc(self, proc, callback_url, image, command,
                    config):
        """Spawn a new process."""

    def _stop_proc(self, proc):
        """Stop process on remote hypervisor."""
        try:
            response = self.requests.delete('http://%s/proc/%s' % (
                    proc.hypervisor.host,
                    self._encode_proc_name(proc)))
            response.raise_for_status()
        except HTTPError:
            self.log.error(
                "failed to remove proc %s from hypervisor" % (
                    proc))
            # FIXME: retry?


class HypervisorService(object):

    def __init__(self, log, clock, eventbus):
        self.eventbus = eventbus
        self._hypervisors = {}

    def start(self):
        self.eventbus.on('hypervisor-start', self._start_hypervisor)
        self.eventbus.on('hypervisor-stop', self._stop_hypervisor)

    def get(self, hypervisor_id):
        return self._hypervisors.get(hypervisor_id)

    def _start_hypervisor(self, model):
        self._hypervisors[model.id] = _hypervisor = _Hypervisor(
            self.log, self.clock, model)
        _hypervisor.start()

    def _stop_hypervisor(self, model):
        _hypervisor = self._hypervisors.pop(model.id, None)
        if _hypervisor is not None:
            _hypervisor.stop()



