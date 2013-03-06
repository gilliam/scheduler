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
import random
import shortuuid
from xsnaga.model import Proc


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
        hypervisors = list(self.store.items)
        if not hypervisors:
            raise ValueError()
        hypervisor = random.choice(hypervisors)
        return hypervisor


class ProcFactory(object):
    """Process factory - spawn and stop procs."""

    def __init__(self, log, clock, eventbus, proc_store, policy, callback_url):
        self.log = log
        self.clock = clock
        self.eventbus = eventbus
        self.proc_store = proc_store
        self.policy = policy
        self.callback_url = callback_url

    def spawn_proc(self, app, deploy, name, command):
        hypervisor = self.policy.allocate(app, name)
        proc = self.proc_store.create(app, name, deploy, shortuuid.uuid(),
                                      hypervisor)
        self.eventbus.emit('proc-create', proc,
                           self.callback_url(proc), command)

    def stop_proc(self, proc):
        """Stop (but not remove) the given process."""
        # FIXME: check state ...
        self.proc_store.set_state(proc, u'stop')
        self.eventbus.emit('proc-dispose', proc)

    def kill_proc(self, proc):
        """Remove the proc completely."""
        self.proc_store.remove(proc)
