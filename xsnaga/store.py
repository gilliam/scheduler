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

import datetime

from xsnaga.model import Proc, App, Deploy, Hypervisor


def transaction(f):
    def wrapper(self, *args, **kw):
        try:
            try:
                return f(self, *args, **kw)
            except Exception:
                self.store.rollback()
                raise
        finally:
            self.store.commit()
    return wrapper


def _datetime(clock):
    return datetime.datetime.utcfromtimestamp(clock)


class ProcStore(object):
    """Database facade for procs."""

    def __init__(self, clock, store):
        self.clock = clock
        self.store = store

    @transaction
    def create(self, app, name, deploy_id, proc_id, hypervisor):
        p = Proc()
        p.name = name
        p.app_id = app.id
        p.deploy = deploy_id
        p.proc_id = unicode(proc_id)
        p.hypervisor = hypervisor
        p.changed_at = _datetime(self.clock.time())
        p.state = u'init'
        self.store.add(p)
        return p

    @transaction
    def remove(self, proc):
        self.store.remove(proc)

    @transaction
    def update(self, proc):
        proc.changed_at = _datetime(self.clock.time())

    @transaction
    def set_state(self, proc, state):
        """Set state."""
        proc.state = state
        proc.changed_at = _datetime(self.clock.time())

    def procs_for_app(self, app, proc_name=None):
        """Return all processes for the given app.

        @return: an interator that will get you all the processes.
        """
        if proc_name is None:
            return self.store.find(Proc, Proc.app_id == app.id)
        else:
            return self.store.find(Proc, (Proc.app_id == app.id)
                                   & (Proc.name == proc_name))

    def by_app_proc_and_id(self, app_name, proc_name, proc_id):
        return self.store.find(Proc, (Proc.app_id == App.id)
                               & (App.name == app_name)
                               & (Proc.name == proc_name)
                               & (Proc.proc_id == proc_id)).one()

    def procs_for_hypervisor(self, hypervisor):
        """Return all processes for the given hypervisor.
        """
        return self.store.find(Proc, Proc.hypervisor_id == hypervisor.id)

    def expired_state_procs(self):
        """Return all processes that are 'expired'.
        """
        return self.store.find(Proc, (Proc.state == u'abort')
                                     | (Proc.state == u'fail')
                                     | (Proc.state == u'done'))

    def expired_deploy_procs(self):
        """Return all processes that have an outdated deploy."""
        states = (u'init', u'boot', u'running')
        return self.store.find(Proc,
              Proc.state.is_in(states) & (Proc.app_id == App.id)
              & (App.deploy == Deploy.id) & (Deploy.id != Proc.deploy))

    def all(self):
        return self.store.find(Proc)


class AppStore(object):
    """Application store."""

    def __init__(self, store):
        self.store = store

    @transaction
    def create(self, name, repository, text):
        """Create a new application."""
        app = App()
        app.name = name
        app.repository = repository
        app.text = text
        app.scale = {}
        self.store.add(app)
        return app

    @transaction
    def set_scale(self, app, scale):
        app.scale = scale

    def update(self, app):
        self.store.flush()
        self.store.commit()

    def by_name(self, name):
        return self.store.find(App, App.name == name).one()

    def apps(self):
        """Return an iterable for all apps."""
        return self.store.find(App)


class DeployStore(object):

    def __init__(self, clock, store):
        self.clock = clock
        self.store = store

    @transaction
    def create(self, app, build, image, pstable, config, text):
        deploy = Deploy()
        deploy.app_id = app.id
        deploy.build = build
        deploy.image = image
        deploy.pstable = pstable
        deploy.config = config
        deploy.text = text
        deploy.timestamp = datetime.datetime.utcfromtimestamp(self.clock.time())
        self.store.add(deploy)
        return deploy

    def by_id_for_app(self, id, app):
        """Return a specific deploy."""
        return self.store.find(Deploy, (Deploy.app_id == app.id) & (
                Deploy.id == id)).one()


class HypervisorStore(object):

    def __init__(self, store):
        self.store = store

    @transaction
    def create(self, host):
        hypervisor = Hypervisor()
        hypervisor.host = host
        self.store.add(hypervisor)
        return hypervisor

    def by_host(self, host):
        """Return a specific hypervisor by host."""
        return self.store.find(Hypervisor, Hypervisor.host == host).one()

    @property
    def items(self):
        """."""
        return self.store.find(Hypervisor)

    @transaction
    def remove(self, hypervisor):
        self.store.remove(hypervisor)
