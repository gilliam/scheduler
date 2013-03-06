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

from collections import deque, defaultdict
import math


class _FailureDetector(object):
    """A PHI failure detector."""

    def __init__(self, samples=100):
        self.last_time = None
        self.intervals = deque([], samples)

    def add(self, arrival_time):
        last_time, self.last_time = self.last_time, arrival_time
        if last_time is not None:
            delta = arrival_time - last_time
            self.intervals.append(delta)

    def phi(self, current_time):
        if self.last_time is None or not self.intervals:
            return None
        current_interval = current_time - self.last_time
        exp = -1 * current_interval / self.interval_mean()
        return -1 * (math.log(pow(math.e, exp)) / math.log(10))

    def interval_mean(self):
        # FIXME: Not sure how fast len(deque) is here, but who cares
        # right now.
        return sum(self.intervals) / float(len(self.intervals))


class HealthStore(object):
    """A repository of hypervisor health state."""

    def __init__(self, clock, threshold):
        self._clock = clock
        self._threshold = threshold
        self._states = defaultdict(_FailureDetector)

    def mark(self, id):
        """Mark that the hypervisor with ID C{id} is alive at this
        point in time.
        """
        self._states[id].add(self._clock.time())

    def phi(self, id):
        """Return current PHI value for the host."""
        return self._states[id].phi(self._clock.time())
    
    def check(self, id):
        """Return C{True} if the hypervisor with ID C{id} is alive."""
        phi = self._states[id].phi(self._clock.time())
        # If we do not have a PHI value yet consider the machine dead.
        return False if phi is None else (phi <= self._threshold)
