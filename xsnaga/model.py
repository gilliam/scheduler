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

from storm.locals import (Int, Unicode, Reference, ReferenceSet, JSON,
                          DateTime, Store, Storm)


class Release(object):
    """Representation of a release."""
    __storm_table__ = 'release'

    id = Int(primary=True)
    app_id = Int()
    version = Int()
    text = Unicode()
    build = Unicode()
    image = Unicode()
    pstable = JSON()
    config = JSON()
    scale = JSON()
    timestamp = DateTime()


class App(object):
    """
    """
    __storm_table__ = 'app'

    id = Int(primary=True)
    name = Unicode()
    text = Unicode()


class Proc(Storm):
    """

    @ivar state: Current known state of the process.  One of the
        following values: C{init}, C{boot}, C{run}, C{abort} or
        C{exit}.  The process starts out in C{init} when the spawn
        request is sent to the supervisor. From there it goes to
        C{run} via C{boot}.  
    """
    __storm_table__ = 'proc'

    id = Int(primary=True)
    app_id = Int()
    proc_type = Unicode()
    proc_name = Unicode()
    desired_state = Unicode()
    actual_state = Unicode()
    changed_at = DateTime()
    release_id = Int()
    hypervisor_id = Int()
    port = Int()
    cont_entity = Unicode()


class Hypervisor(Storm):
    __storm_table__ = 'hypervisor'

    id = Int(primary=True)
    host = Unicode()
    port = Int()
    capacity = Int()
    options = JSON()

    procs = ReferenceSet('Hypervisor.id', Proc.hypervisor_id)

    def proc_url(self):
        """Return URL to the proc collection."""
        return 'http://%s:%d/proc' % (self.host, self.port)
