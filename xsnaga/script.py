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

import logging
import os

from storm.locals import Store, create_database
from gevent import pywsgi, pool, socket, monkey
monkey.patch_all(thread=False, time=False)
from glock.clock import Clock
from xsnaga.store import ProcStore, AppStore, ReleaseStore, HypervisorStore
from xsnaga.hypervisor import HypervisorController, HypervisorClient
from xsnaga.api import (API, AppResource, ReleaseResource,
                        HypervisorResource, ProcResource)
from xsnaga.handler import (SlowBootHandler, SlowTermHandler,
                            ExpiredProcHandler, ScaleHandler,
                            RemoveTerminatedProcHandler)
from xsnaga.proc import ProcFactory, RandomPlacementPolicy
from pyee import EventEmitter


HEALTH_THRESHOLD = 2
HEALTH_CHECK_INTERVAL = 30
SLOW_BOOT_INTERVAL = 3
SLOW_BOOT_THRESHOLD = 60
SLOW_TERM_INTERVAL = 3
SLOW_TERM_THRESHOLD = 20
EXPIRED_INTERVAL = 3
SCALE_INTERVAL = 5
REMOVE_TERMINATED_INTERVAL = 10


def main(clock, eventbus, options):
    format = '%(levelname)-8s %(name)s: %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=format)
    store = Store(create_database(options['DATABASE']))
    eventbus = EventEmitter()
    proc_store = ProcStore(clock, store)
    app_store = AppStore(store)
    release_store = ReleaseStore(clock, store)
    hypervisor_store = HypervisorStore(store)

    def hypervisor_client_factory(model):
        return HypervisorClient(logging.getLogger(
                'hypervisor.client[%s]' % (model.host,)),
                clock, HEALTH_CHECK_INTERVAL,
                proc_store, app_store, model)

    hypervisor_controller = HypervisorController(
        eventbus, hypervisor_store, hypervisor_client_factory)
    hypervisor_controller.start()

    policy = RandomPlacementPolicy(logging.getLogger('placement.random'),
                                   hypervisor_store)
    environ = {'SERVER_NAME': options.get('SERVER_NAME', socket.getfqdn()),
               'SERVER_PORT': str(options['PORT'])}

    api = API(logging.getLogger('api'), environ)
    proc_factory = ProcFactory(logging.getLogger('proc.factory'),
                               clock, eventbus, proc_store, policy,
                               api.callback_url)
    api.add('apps', AppResource(api.log, api.url, app_store))
    api.add('releases', ReleaseResource(api.log, api.url, app_store,
                                        release_store))
    api.add('hypervisor', HypervisorResource(api.log, api.url, eventbus,
                                             hypervisor_store))
    api.add('procs', ProcResource(api.log, api.url, app_store, proc_store,
                                  release_store, hypervisor_store,
                                  proc_factory))


    handlers = []
    handlers.append(SlowBootHandler(logging.getLogger('handler.slow-boot'),
                                    clock, SLOW_BOOT_INTERVAL,
                                    proc_store, app_store,
                                    int(options.get('SLOW_BOOT_THRESHOLD',
                                                    SLOW_BOOT_THRESHOLD))))
    handlers.append(SlowTermHandler(logging.getLogger('handler.slow-term'),
                                    clock, SLOW_TERM_INTERVAL,
                                    proc_store, app_store,
                                    SLOW_TERM_THRESHOLD))
    handlers.append(ExpiredProcHandler(logging.getLogger('handler.expired'),
                                       clock, EXPIRED_INTERVAL,
                                       proc_store, app_store,
                                       proc_factory))
    handlers.append(RemoveTerminatedProcHandler(
            logging.getLogger( 'handler.terminated'), clock, 
            int(options.get('REMOVE_TERMINATED_INTERVAL',
                            REMOVE_TERMINATED_INTERVAL)),
            proc_store, app_store, proc_factory))
    handlers.append(ScaleHandler(logging.getLogger('handler.scale'),
                                 clock, SCALE_INTERVAL,
                                 release_store, app_store, proc_store,
                                 proc_factory, pool.Pool(5)))
    for handler in handlers:
        handler.start()
    logging.info("Start serving requests on %d" % (int(options['PORT'])))
    return pywsgi.WSGIServer(('', int(options['PORT'])), api)


def _start():
    main(Clock(), EventEmitter(), os.environ).serve_forever()

if __name__ == '__main__':
    _start()
