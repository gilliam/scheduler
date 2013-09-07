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


_DEFAULT_RANK = '-ncont'

from xscheduler.util import RecurringTask, TokenBucketRateLimiter


class RequirementRankPlacementPolicy(object):

    def select(self, executors, options):
        """Given a set of executors and placement options, select a
        executor where the instance should be placed.
        """
        e = self._rank_executors(
                self._filter_out_executors_that_do_not_match_requirements(
                    executors, options), options)
        return next(e, None)

    def _eval_requirement(self, requirement, executor):
        vars = {'tags': executor.tags, 'host': executor.host,
                'domain': executor.domain}
        return eval(requirement, vars, {})

    def _filter_out_executors_that_do_not_match_requirements(
            self, executors, options):
        requirements = options.get('requirements', [])
        if not requirements:
            return executors
        return [
            executor
            for requirement in requirements
            for executor in executors
            if self._eval_requirement(requirement, executor)]

    def _collect_vars(self, executor):
        """Collect rank variables."""
        return {'ncont': len(executor.containers)}

    def _eval_rank(self, rank, vars):
        return eval(rank, vars, {})

    def _rank_executors(self, executors, options):
        rank = options.get('rank', _DEFAULT_RANK)
        executors.sort(key=lambda executor: self._eval_rank(rank,
            self._collect_vars(executor)))
        return executors


class Scheduler(object):

    def __init__(self, clock, store_query, manager, policy):
        self._runner = RecurringTask(3, self._do_schedule)
        self.clock = clock
        self.store_query = store_query
        self.manager = manager
        self.policy = policy
        self._limiter = TokenBucketRateLimiter(clock, 100, 30)
        self.start = self._runner.start
        self.stop = self._runner.stop
        
    def _do_schedule(self):
        for instance in self.store_query.unassigned():
            if not self._schedule_limiter.check():
                break
            executor = self.policy.select(self.manager.clients(),
                                          instance.get('placement', {}))
            if executor is not None:
                instance.assign(executor.name)


class Dispatcher(object):

    def __init__(self, clock, store_query, manager):
        self._runner = RecurringTask(3, self._do_dispatch)
        self.store_query = store_query
        self.manager = manager
        self._limiter = TokenBucketRateLimiter(clock, 10, 30)
        self.start = self._runner.start
        self.stop = self._runner.stop

    def _do_dispatch(self):
        for instance in self.store_query.undispatched():
            if not self._limiter.check():
                break
            instance.dispatch(self.manager)


class Updater(object):

    def __init__(self, clock, store_query, manager):
        self._runner = RecurringTask(3, self._do_update)
        self.store_query = store_query
        self.manager = manager
        self._limiter = TokenBucketRateLimiter(clock, 10, 30)
        self.start = self._runner.start
        self.stop = self._runner.stop

    def _equal_instance_container(self, inst, cont):
        inst_env = inst.env or {}
        cont_env = cont.env or {}
        return (inst.image == cont.image
                and inst.command == cont.command)
                and inst_env == cont_env)

    def _do_update(self):
        instances = list(self.store_query.index())
        for instance, container in zip(
                instances, self.manager.containers(instances)):
            if contaner is None:
                continue
            if not self._equal_instance_container(instance, container):
                if not self._limiter.check():
                    break
                instance.restart(self.manager)


class Terminator(object):
    """Process responsible for moving instances from "shutting down"
    into "terminated" by killing them off.
    """

    def __init__(self, clock, store_query, manager):
        self._runner = RecurringTask(3, self._do_terminate)
        self.store_query = store_query
        self.manager = manager
        self._limiter = TokenBucketRateLimiter(clock, 10, 30)
        self.start = self._runner.start
        self.stop = self._runner.stop

    def _do_terminate(self):
        for instance in self.store_query.shutting_down():
            if not self._limiter.check():
                break
            instance.terminate(self.manager)
