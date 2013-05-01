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
import random

from glock.task import LoopingCall
from collections import defaultdict

from . import util


class _BaseHandler(object):
    """Base class for our handlers."""

    def __init__(self, log, clock, interval):
        self.log = log
        self.clock = clock
        self.interval = interval
        self._handle_call = LoopingCall(clock, self._handle)

    def start(self):
        self._handle_call.start(self.interval)


class SlowBootHandler(_BaseHandler):
    """Handler responsible for setting a proc's desired state to 'abort'
    if it does not boot quickly enough.
    """

    def __init__(self, log, clock, interval, proc_store, app_store,
                 threshold):
        _BaseHandler.__init__(self, log, clock, interval)
        self.proc_store = proc_store
        self.app_store = app_store
        self.threshold = threshold

    def _handle(self):
        now = datetime.datetime.utcfromtimestamp(self.clock.time())
        for proc in self.proc_store.all():
            dt = now - proc.changed_at
            if proc.desired_state == u'start' \
                    and proc.actual_state != 'running' \
                    and util.total_seconds(dt) >= self.threshold:
                app = self.app_store.get(proc.app_id)
                self.log.info(
                    'no state change for proc %s:%s in %d seconds -> abort' % (
                        app.name, proc.proc_name, self.threshold))
                self.proc_store.set_desired_state(proc, u'abort')


class SlowTermHandler(_BaseHandler):
    """Handler responsible for setting a proc's desired state to
    'abort' if it does not shut down quickly enough.
    """

    def __init__(self, log, clock, interval, proc_store, app_store,
                 threshold):
        _BaseHandler.__init__(self, log, clock, interval)
        self.proc_store = proc_store
        self.app_store = app_store
        self.threshold = threshold

    def _handle(self):
        now = datetime.datetime.utcfromtimestamp(self.clock.time())
        for proc in self.proc_store.all():
            dt = now - proc.changed_at
            if proc.desired_state == u'stop' \
                    and proc.actual_state not in ('done', 'fail', 'abort') \
                    and util.total_seconds(dt) >= self.threshold:
                app = self.app_store.get(proc.app_id)
                self.log.info(
                    'no stop for proc %s:%s in %d seconds -> abort' % (
                        app.name, proc.proc_name, self.threshold))
                self.proc_store.set_desired_state(proc, u'abort')


class ExpiredProcHandler(_BaseHandler):
    """Handler responsible for removing aborted procs.

    A proc can end up with a desired state 'abort' if it has not
    reacted quickly enough to instructed state changes.
    """
    
    def __init__(self, log, clock, interval, proc_store,
                 app_store, proc_factory):
        _BaseHandler.__init__(self, log, clock, interval)
        self.proc_store = proc_store
        self.app_store = app_store
        self.proc_factory = proc_factory

    def _handle(self):
        for proc in self.proc_store.all():
            if proc.desired_state == u'abort':
                app = self.app_store.get(proc.app_id)
                self.log.info("force kill proc %s:%s" % (
                        app.name, proc.proc_name))
                self.proc_factory.kill_proc(proc)


class RemoveTerminatedProcHandler(_BaseHandler):
    """Handler responsible for removing procs that has terminated."""
    
    def __init__(self, log, clock, interval, proc_store,
                 app_store, proc_factory):
        _BaseHandler.__init__(self, log, clock, interval)
        self.proc_store = proc_store
        self.app_store = app_store
        self.proc_factory = proc_factory

    def _handle(self):
        for proc in self.proc_store.all():
            if proc.actual_state in (u'done', u'fail', u'abort'):
                app = self.app_store.get(proc.app_id)
                self.log.info("remove proc %s:%s because of state %s" % (
                        app.name, proc.proc_name, proc.actual_state))
                self.proc_factory.kill_proc(proc)


class ScaleHandler(_BaseHandler):
    """Handler that is responsible for scaling up or down a release"""

    def __init__(self, log, clock, interval, release_store, app_store,
                 proc_store, proc_factory, pool):
        _BaseHandler.__init__(self, log, clock, interval)
        self.release_store = release_store
        self.app_store = app_store
        self.proc_factory = proc_factory
        self.proc_store = proc_store
        self.pool = pool

    def _handle(self):
        self.pool.map(self._handle_release, self.release_store.all())

    def _handle_release(self, release):
        procs = defaultdict(list)
        for proc in self.proc_store.for_release(release):
            procs[proc.proc_type].append(proc)

        for proc_type in release.pstable:
            scale = release.scale or {}
            desired = scale.get(proc_type, 0)
            current = [proc for proc in procs.get(proc_type, [])
                       if proc.desired_state == 'start']
            if len(current) == desired:
                continue

            app = self.app_store.get(release.app_id)
            self.log.debug('%s:%s: current=%d wanted=%d' % (
                    app.name, proc_type, len(current), desired))
            if len(current) > desired:
                n = len(current) - desired
                self._scale_down(n, current)
            elif len(current) < desired:
                n = desired - len(current)
                self._scale_up(n, app, release, proc_type)

    def _scale_down(self, n, choices):
        for proc in random.sample(choices, n):
            self.proc_factory.stop_proc(proc)

    def _scale_up(self, n, app, release, proc_type):
        for i in range(n):
            self.proc_factory.spawn_proc(app, release, proc_type)
