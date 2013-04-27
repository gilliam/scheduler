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


class DeployError(Exception):
    pass


class RandomPlacementPolicy(object):
    """Random placement policy."""

    def __init__(self, log, store):
        self.log = log
        self.store = store

    def allocate(self, app, proc_type):
        """Allocate a hypervisor for process C{name} of C{app}."""
        # Here we should do this neat thingy to distribute stuff
        # evenly, and to amke sure that the same process do not run on
        # the same hypervisor.  But for now we only alloc on a random
        # hypervisor.
        hypervisors = list(self.store.all())
        if not hypervisors:
            raise DeployError()
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

    def spawn_proc(self, app, release, proc_type):
        """Spawn a process for given app and release.

        @param app: The app that the process belongs to.
        @type app: a L{App}.

        @param release: The release of the process.
        @type release: a L{Release}.

        @param proc_type: The process to type create an instance of.
        @type proc_type: a C{str} or C{unicode}.
        """
        assert proc_type in release.pstable
        command = release.pstable[proc_type]
        hypervisor = self.policy.allocate(app, proc_type)
        proc_name = '%s.%s' % (proc_type, shortuuid.uuid())
        proc = self.proc_store.create(app,
                                      unicode(proc_type),
                                      unicode(proc_name),
                                      u'start',
                                      release,
                                      hypervisor)
        # XXX: If it wasn't for the callback URL we could have moved
        # the eventbus trigger into the store.
        self.eventbus.emit('proc-create', proc, app, release,
                           self.callback_url(app, proc))

    def stop_proc(self, proc):
        """Stop (but not remove) the given process."""
        self.proc_store.set_desired_state(proc, u'stop')
        self.eventbus.emit('proc-dispose', proc)

    def kill_proc(self, proc):
        """Remove the proc completely."""
        self.proc_store.remove(proc)
