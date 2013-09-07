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

from gevent import monkey
monkey.patch_all()

import os
import time
import logging

import etcd
from gilliam.service_registry import ServiceRegistryClient
import shortuuid
import requests
import yaml

from xscheduler.scheduler import (RequirementRankPlacementPolicy,
                                  Scheduler, Dispatcher, Updater,
                                  Terminator)
from xscheduler.executor import ExecutorManager
from xscheduler import store, util


def _worker(executor_manager, store_query):
    while True:
        time.sleep(100)


def main():
    format = '%(levelname)-8s %(name)s: %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=format)

    formation = os.getenv('GILLIAM_FORMATION')
    srnodes = os.getenv('GILLIAM_SERVICE_REGISTRY_NODES')
    check_interval = int(os.getenv('CHECK_INTERVAL', 10))
    
    store_client = etcd.Etcd(host='_store.%s.service' % (formation,))
    store_command = store.InstanceStoreCommand(store_client)
    store_query = store.InstanceStoreQuery(store_client, store_command)

    registry_client = ServiceRegistryClient(time, srnodes.split(','))
    executor_manager = ExecutorManager(time, registry_client, store_query,
                                       check_interval)

    policy = RequirementRankPlacementPolicy()
    services = [
        Scheduler(time, store_query, executor_manager, policy),
        Dispatcher(time, store_query, executor_manager),
        Updater(time, store_query, executor_manager),
        Terminator(time, store_query, executor_manager)
        ]

    leader_lock = util.Lock(store_client, 'leader', 'bootstrapper')
    with leader_lock:
        executor_manager.start()
        store_query.start()
        for service in services:
            service.start()
        _worker(executor_manager, store_query)

