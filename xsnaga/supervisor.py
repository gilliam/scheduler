# Copyright (c) 2013 Johan Rydberg.

"""Functionality related to handling supervisors."""


class SupervisorX(object):

    def __init__(self, log, clock, state_db):
        self.log = log
        self.clock = clock
        self.state_db = state_db

    def state_changed(self, name, state, host, port):
        """."""
        app, proc, uid = self._split_proc_name(name)
        if state == 'starting':
            self.state_db.update_state(app, proc, uid)

    def _split_proc_name(self, name):
        app, deploy, proc, uid = name.split('.')
        return app, proc, deploy, uid
