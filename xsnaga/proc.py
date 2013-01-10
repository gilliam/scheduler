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

import datetime
from xsnaga.model import Proc


def _datetime(clock):
    return datetime.datetime.utcfromtimestamp(clock.time())


class ProcStore(object):
    """Database facade for procs."""

    def __init__(self, clock, store):
        self.clock = clock
        self.store = store

    def create(self, app, name, deploy_id, proc_id,
               hypervisor, created_at):
        p = Proc(app, name, deploy_id, proc_id, hypervisor)
        p.set_state('init', created_at)
        self.store.add(p)
        return p

    def remove(self, proc):
        self.store.remove(proc)

    def procs_for_app(self, app):
        """Return all processes for the given app.

        @return: an interator that will get you all the processes.
        """
        return self.store.find(Proc, Proc.app_id == app.id)

    def procs_for_hypervisor(self, hypervisor):
        """Return all processes for the given hypervisor.
        """
        return self.store.find(Proc, Proc.hypervisor_id == hypervisor.id)

    def expired_state_procs(self):
        """Return all processes that are 'expired' (has a state that is either
        abort or exit).
        """
        return self.store.find(Proc, (Proc.state == 'abort')
                                     | (Proc.state == 'exit'))

    def expired_deploy_procs(self):
        """Return all processes that have an outdated deploy."""
        states = ('init', 'boot', 'running')
        return self.store.find(Proc,
              Proc.state.is_in(states) & Proc.app_id == App.id
              & App.deploy == Deploy.id & Deploy.id != Proc.deploy)


class RandomPlacementPolicy(object):
    """Random placement policy."""

    def __init__(self, log, store):
        self.log = log
        self.store = store

    def allocate(self, app, name):
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


class ProcFactory(object):
    """Process factory - spawn and stop procs."""

    def __init__(self, log, clock, proc_store, policy, hypervisor_service):
        self.log = log
        self.clock = clock
        self.proc_store = proc_store
        self.policy = policy
        self.hypervisor_service = hypervisor_service

    def spawn_proc(self, app, deploy, name, command):
        hypervisor = self.policy.allocate(app, name)
        proc = self.proc_store.create(app, name, deploy.id,
                                      shortuuid.uuid(),
                                      hypervisor,
                                      _datetime(self.clock))

        try:
            controller = self.hypervisor_service.get(hypervisor.id)
            controller.spawn_proc(proc, self._callback_url(proc),
                                  deploy.image, command, deploy.config)
        except Exception:
            proc.set_state('abort', _datetime(self.clock))
            raise

    def stop_proc(self, proc):
        """Stop (but not remove) the given process."""
        # fixme: check state ...
        proc.set_state('stop', _datetime(self.clock))
        try:
            controller = self.hypervisor_service.get(hypervisor.id)
            controller.stop_proc(proc)
        except Exception:
            self.log.error(
                "failed to remove proc %s from hypervisor" % (proc,))

    def kill_proc(self, proc):
        """Remove the proc completely."""
        self.proc_store.remove(proc)
