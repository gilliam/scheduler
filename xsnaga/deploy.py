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


class _Application(object):
    """Handle an application when it comes to managing processes.

    Note that this class is not responsible for selecting where to the
    processes, only how many and which processes.  That is done by
    C{placement}.
    """

    def __init__(self, log, clock, eventbus, pool, placement,
                 interval):
        self.log = log
        self.clock = clock
        self.eventbus = eventbus
        self.placement = placement
        self.pool = pool
        self.interval = interval
        self._handle_call = LoopingCall(clock, self._handle_change)

    def start(self):
        self.eventbus.bind('app-change:%s' % (self.app.id,),
                           self._handle_change)
        self._handle_call.start(self.interval)

    def _handle_change(self, *args):
        """something has changed about the app."""
        self._handle_dead_procs()
        self._handle_dead_pstypes()
        self._handle_spawn_procs()
        self._handle_outdated_procs()

    def _handle_dead_pstypes(self):
        procs = self.placement.procs_for_app(self.app)
        for proc in procs:
            if proc.name not in self.app.deploy.pstable:
                if self.pool.full():
                    break
                self.pool.spawn(self.placement.stop_proc, proc)
        
    def _handle_dead_procs(self):
        procs = self.placement.procs_for_app(name)
        for proc in procs:
            if proc.state in ('abort', 'exit'):
                if self.pool.full():
                    break
                self.pool.spawn(self.placement.kill_proc, proc)

    def _handle_outdated_procs(self):
        procs = self.placement.procs_for_app(self.app.id)
        for proc in procs:
            if proc.deploy != self.app.deploy.id:
                if self.pool.full():
                    break
                self.pool.spawn(self.placement.stop_proc, proc)

    def _handle_spawn_procs(self):
        procs = list(self.placement.procs_for_app(self.app))
        for name, command in app.deploy.pstable.items():
            scale = self.app.scale.get(name, 0)
            existing = [proc for proc in procs
                        if proc.name == name
                        and proc.deploy == self.app.deploy.id]
            if len(existing) > scale:
                self._scale_down(len(existing) - scale, existing)
            elif len(existing) < scale:
                self._scale_up(scale - len(existing), name, command)

    def _scale_down(self, n, choices):
        for i in range(n):
            if self.pool.full():
                break
            proc = random.choice(choices)
            self.pool.spawn(self.placement.stop_proc,
                            proc)

    def _scale_up(self, n, name, command):
        for i in range(n):
            if self.pool.full():
                break
            self.pool.spawn(self.placement.spawn_proc,
                            self.app, self.app.deploy,
                            name, command)


class AppService(object):

    def __init__(self, log, clock, eventbus):
        eventbus.bind('app-start:*', self._start)
        self._apps = {}

    def _start(self, app):
        self._apps[app.id] = _app = _Application(
            self.log, self.clock, self.eventbus, app)
        _app.start()
        
