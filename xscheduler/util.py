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

import time

from gevent.event import Event
import gevent

from etcd import EtcdError


def first(it, default):
    return next(iter(it), default)


class TokenBucketRateLimiter(object):

    def __init__(self, clock, rate, time):
        self.clock = clock
        self.rate = rate
        self.time = time
        self._allowance = rate
        self._last_check = self.clock.time()

    def check(self):
        current = self.clock.time()
        time_passed = current - self._last_check
        self._last_check = current
        self._allowance += (time_passed * (self.rate / self.time))
        if self._allowance > self.rate:
            self._allowance = self.rate
        if self._allowance < 1.0:
            return False
        else:
            self._allowance -= 1.0
            return True


class RecurringTask(object):

    def __init__(self, interval, fn):
        self.interval = interval
        self.fn = fn
        self._wakeup = Event()
        self._stopped = Event()
        self._gthread = None

    def touch(self):
        """Make sure the task is executed now."""
        self._wakeup.set()
    
    def start(self):
        self._gthread = gevent.spawn(self._run)

    def stop(self):
        self._stopped.set()
        self._wakeup.set()

    def _run(self):
        while not self._stopped.is_set():
            self.fn()
            self._wakeup.wait(timeout=self.interval)
            self._wakeup.clear()


class Lock(object):

    def __init__(self, etcd, key, name, ttl=30):
        """."""
        self.etcd = etcd
        self.key = key
        self.name = name
        self._gthread = None
        self._ttl = ttl
        self._stopped = Event()

    def _heartbeat(self):
        while True:
            self._stopped.wait(self._ttl / 2)
            if self._stopped.is_set():
                break
            self.etcd.testandset(self.key, self.name, self.name,
                                 ttl=self._ttl)

    def lock(self):
        # This is to work around bugs in etcd.  Not very atomic
        # at all :(
        while True:
            try:
                e = self.etcd.get(self.key)
            except EtcdError, err:
                e = self.etcd.set(self.key, self.name)
                self._gthread = gevent.spawn(self._heartbeat)
                break
            else:
                time.sleep(self._ttl / 2)

    def unlock(self):
        self._stopped.set()
        self._gthread.join()
        try:
            self.etcd.delete(self.key)
        except EtcdError:
            pass

    def __enter__(self):
        self.lock()

    def __exit__(self, *args):
        self.unlock()
