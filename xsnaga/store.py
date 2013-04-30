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
from storm.expr import SQL, Asc, Desc

from xsnaga.model import Proc, App, Release, Hypervisor


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
    def create(self, app, proc_type, proc_name, desired_state, release, hypervisor):
        p = Proc()
        p.app_id = app.id
        p.proc_type = proc_type
        p.proc_name = proc_name
        p.desired_state = desired_state
        p.actual_state = u'unknown'
        p.changed_at = _datetime(self.clock.time())
        p.release_id = release.id
        p.hypervisor_id = hypervisor.id
        self.store.add(p)
        return p

    @transaction
    def persist(self, proc):
        pass

    @transaction
    def remove(self, proc):
        self.store.remove(proc)

    def set_desired_state(self, proc, state):
        proc.desired_state = state
        proc.changed_at = _datetime(self.clock.time())
        self.persist(proc)

    def set_actual_state(self, proc, state):
        """Set actual state and persist."""
        proc.actual_state = state
        proc.changed_at = _datetime(self.clock.time())
        self.persist(proc)

    def by_app_name(self, app, proc_name):
        """:"""
        return self.store.find(Proc, (Proc.app_id == app.id)
                               & (Proc.proc_name == proc_name)).one()

    def for_release(self, release):
        """Return all procs for the given release.

        @type release: a L{Release}.
        """
        return self.store.find(Proc, (Proc.release_id == release.id))

    def for_app(self, app):
        """Return all procs for the given app.

        @type app: a L{App}.
        """
        return self.store.find(Proc, (Proc.app_id == app.id))

    def for_hypervisor(self, hypervisor):
        """Return all procs for the given hypervisor.

        @type hypevisor: a L{Hypervisor}.
        """
        return self.store.find(Proc, (Proc.hypervisor_id == hypervisor.id))

    def all(self):
        """Return all procs."""
        return self.store.find(Proc)


class AppStore(object):
    """Application store."""

    def __init__(self, store):
        self.store = store

    @transaction
    def create(self, name, text):
        """Create a new application."""
        app = App()
        app.name = name
        app.text = text
        self.store.add(app)
        return app

    def get(self, app_id):
        return self.store.get(App, app_id)

    @transaction
    def persist(self, app):
        pass

    def by_name(self, name):
        return self.store.find(App, App.name == name).one()

    def apps(self):
        """Return an iterable for all apps."""
        return self.store.find(App)


class ReleaseStore(object):

    def __init__(self, clock, store):
        self.clock = clock
        self.store = store

    @transaction
    def create(self, app, text, build, image, pstable, config):
        # try to get the next version
        max_version = self.store.find(Release, (Release.app_id == app.id)).max(Release.version)
        if max_version is None:
            max_version = 0
        release = Release()
        release.app_id = app.id
        release.version = max_version + 1
        release.text = text
        release.build = build
        release.image = image
        release.pstable = pstable
        release.config = config
        release.timestamp = _datetime(self.clock.time())
        self.store.add(release)
        return release

    @transaction
    def persist(self, release):
        """Persist release."""
        # Normalize the scale.
        if release.scale is not None:
            scale = dict(
                [(proc_type, n)
                 for (proc_type, n) in release.scale.items()
                 if n != 0])
            release.scale = scale or None

    @transaction
    def remove(self, release):
        self.store.remove(release)

    def get(self, app_id):
        return self.store.get(Release, app_id)

    def all(self):
        return self.store.find(Release)

    def for_app(self, app):
        """Return an iterable of all releases for a specific app."""
        return self.store.find(Release, (Release.app_id == app.id)).order_by(
            Desc(Release.version))

    def with_scale(self):
        """Return an iterable of all releases that has a scale."""
        return self.store.find(Release, SQL("releases.scale IS NOT NULL"))

    def by_app_version(self, app, version):
        """Return a specific release."""
        return self.store.find(Release, (Release.app_id == app.id) 
                               & (Release.version == int(version))).one()


class HypervisorStore(object):

    def __init__(self, store):
        self.store = store

    def by_host(self, host):
        return self.store.find(Hypervisor, Hypervisor.host == host).one()

    @transaction
    def create(self, host, port, capacity, options):
        hypervisor = Hypervisor()
        hypervisor.host = host
        hypervisor.port = port
        hypervisor.capacity = capacity
        hypervisor.options = options
        self.store.add(hypervisor)
        return hypervisor

    def get(self, id):
        return self.store.get(Hypervisor, id)

    def by_host(self, host):
        """Return a specific hypervisor by host."""
        return self.store.find(Hypervisor, Hypervisor.host == host).one()

    def all(self):
        """."""
        return self.store.find(Hypervisor)

    @transaction
    def remove(self, hypervisor):
        self.store.remove(hypervisor)
