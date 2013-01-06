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

"""Functionality for managing processes."""


class ProcPlacement(object):

    def __init__(self, log, clock, store):
        self.log = log
        self.clock = clock
        self.store = store

    def procs_for_app(self, app):
        """Return all processes for the given app.

        @return: an interator that will get you all the processes.
        """
        return self.store.find(Proc, Proc.app_id == app.id)

    def _encode_proc_name(self, proc):
        return '%s.%d.%s.%s' % (proc.app.name, 
                                proc.deploy,
                                proc.name,
                                proc.proc_id)

    def spawn_proc(self, app, deploy, name, command):
        hypervisor = self._allocate(app, name)
        proc = Proc(app, name, deploy.id, shortuuid.uuid(), 
                    hypervisor)
        try:
            request = {'name': self._encode_proc_name(proc),
                       'callback': self._callback_url(proc),
                       'image': deploy.image,
                       'command': command,
                       'config': deploy.config}
            response = self.requests.post('http://%s/proc' % (
                    hypervisor.host,), data=json.dumps(request))
            response.raise_for_status()
        except Exception:
            proc.state = 'abort'
        self.store.flush()
        self.store.commit()

    def stop_proc(self, proc):
        """Stop (but not remove) the given process."""
        # fixme: check state ...
        proc.state = 'stop'
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
        self.store.flush()
        self.store.commit()
        
    def _allocate(self, app, name):
        """Allocate a hypervisor for process C{name} of C{app}."""
        # Here we should do this neat thingy to distribute stuff
        # evenly, and to amke sure that the same process do not run on
        # the same hypervisor.  But for now we only alloc on a random
        # hypervisor.
        hypervisors = list(self.store.find(Hypervisor))
        if not hypervisors:
            raise ValueError()
        hypervisor = random.choice(hypervisors)
        return hypervisor
