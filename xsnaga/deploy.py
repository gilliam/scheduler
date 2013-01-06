# Copyright (c) 2013 Johan Rydberg.

class _Application(object):
    """Handle an application when it comes to managing processes.

    Note that this class is not responsible for selecting where to the
    processes, only how many and which processes.
    """

    def __init__(self, log, clock, app):
        pass

    def start(self):
        self.eventbus.bind('app-change:%s' % (self.app,),
                           self._handle_change)
        self._supervisor.bind('proc-change:%s' % (self.app,),
                       self._handle_change)

    def _handle_change(self, *args):
        """something has changed about the app."""
        self._handle_dead_procs()
        self._handle_spawn_procs()
        self._handle_outdated_procs()
        
    def _handle_outdated_procs(self):
        app = self.app_db.get(self.app)
        procs = self.state_db.procs_for_app(name)
        for proc in procs:
            if proc.deploy != app.deploy.id:
                if self.pool.full():
                    break
                self.pool.spawn(self._stop_proc, proc)

    def _handle_dead_procs(self):
        procs = self.state_db.procs_for_app(name)
        for proc in procs:
            if proc.state in ('abort', 'dead'):
                if self.pool.full():
                    break
                self.pool.spawn(self._stop_proc, proc)

    def _handle_spawn_procs(self):
        app = self.app_db.get(self.app)
        procs = self.proc_db.for_app(self.app)
        for name, command in app.deploy.pstable.items():
            scale = app.scale.get(name, 0)
            existing = [proc for proc in procs
                        if proc.name == name
                        proc.deploy == app.deploy.id]
            if existing > scale:
                for n in range(existing - scale):
                    if self.pool.full():
                        break
                    proc = random.choice(existing)
                    self._stop_proc(proc)
            elif existing < scale:
                for n in range(scale - existing):
                    if self.pool.full():
                        break
                    self.pool.spawn(self._spawn_proc, app.deploy,
                                    name, command)

    def _spawn_proc(self, deploy, name, command):
        """."""
        self._orch.spawn_proc(self.app, deploy, name, command)
        # this updates the state db straight away, i hope.


class AppService(object):

    def __init__(self, log, clock, eventbus):
        eventbus.bind('app-start:*', self._start)
        self._apps = {}

    def _start(self, app):
        self._apps[app.name] = _app = _Application(
            self.log, self.clock, self.eventbus, app.name)
        _app.start()
        
