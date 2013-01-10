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

from glock.task import LoopingCall


class _BaseHandler(object):
    """Base class for our handlers."""

    def __init__(self, log, clock, interval):
        self.log = log
        self.clock = clock
        self.interval = interval
        self._handle_call = LoopingCall(clock, self._handle)

    def start(self):
        self._handle_call.start(self.interval)


class OldDeployHandler(_BaseHandler):
    """Responsible for cleaning up processes from old deploys."""
    
    def __init__(self, log, clock, interval, proc_store,
                 proc_factory):
        _BaseHandler.__init__(self, log, clock, interval)
        self.proc_store = proc_store
        self.proc_factory = proc_factory

    def start(self):
        self._call.start(self.interval)

    def _handle(self):
        for proc in self.proc_store.expired_deploy_procs():
            self.proc_factory.stop_proc(proc)


class ExpiredProcHandler(_BaseHandler):
    """Responsible for really removing old processes from the store."""
    
    def __init__(self, log, clock, interval, proc_store,
                 proc_factory):
        _BaseHandler.__init__(self, log, clock, interval)
        self.proc_store = proc_store
        self.proc_factory = proc_factory

    def start(self):
        self._call.start(self.interval)

    def _handle(self):
        for proc in self.proc_store.expired_state_procs():
            self.proc_factory.kill_proc(proc)


class ScaleHandler(_BaseHandler):
    """Handler that is responsible for scaling up or down an app."""

    def __init__(self, log, clock, interval, app_store, proc_store,
                 proc_factory, pool):
        _BaseHandler.__init__(self, log, clock, interval)
        self.app_store = app_store
        self.proc_store = proc_store
        self.proc_factory = proc_factory
        self.pool = pool

    def _handle(self):
        apps = self.app_store.apps()
        self.pool.map(self._handle_app, apps)

    def _handle_app(self, app):
        procs = defaultdict(list)
        for proc in self.proc_store.procs_for_app(app):
            procs[proc.name].append(proc)
        for name, command in app.deploy.pstable.items():
            scale = app.scale.get(name, 0)
            existing = procs.get(name, [])
            current = [proc for proc in existing
                       if proc.deploy == app.deploy.id]
            if len(current) > scale:
                n = len(current) - scale
                self._scale_down(n, existing)
            elif len(current) < scale:
                n = scale - len(current)
                self._scale_up(n, app, name, command)

    def _scale_down(self, n, choices):
        for i in range(n):
            self.proc_factory.stop_proc(proc)

    def _scale_up(self, n, app, name, command):
        for i in range(n):
            self.proc_factory.spawn_proc(
                app, app.deploy, name, command)
