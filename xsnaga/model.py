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

from datetime import datetime
from storm.locals import (Int, Unicode, Reference, ReferenceSet, JSON,
                          DateTime, Store)


class Deploy(object):
    """Representation of a deployment."""
    __storm_table__ = 'deploy'

    id = Int(primary=True)
    app_id = Int()
    build = Unicode()
    image = Unicode()
    pstable = JSON()
    config = JSON()
    text = Unicode()
    timestamp = DateTime()


class App(object):
    """

    @ivar deploy: The current deploy.  May be C{None} if there has not
        been a deploy yet for this application.
    """
    __storm_table__ = 'app'

    id = Int(primary=True)
    name = Unicode()
    deploy_id = Int()
    deploy = Reference(deploy_id, Deploy.id)
    deploys = ReferenceSet(id, Deploy.app_id)
    scale = JSON()
    repository = Unicode()
    text = Unicode()


class Proc(object):
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
    app = Reference(app_id, App.id)
    proc_id = Unicode()
    name = Unicode()
    state = Unicode()
    deploy = Int()
    host = Unicode()
    port = Int()
    hypervisor_id = Int()
    hypervisor = Reference(hypervisor_id, 'Hypervisor.id')
    changed_at = DateTime()


class Hypervisor(object):
    """."""
    __storm_table__ = 'hypervisor'

    id = Int(primary=True)
    host = Unicode()
    procs = ReferenceSet(Hypervisor.id, Proc.hypervisor_id)
