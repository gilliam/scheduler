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
from gevent import pywsgi, pool
from glock.clock import Clock
from xsnaga.store import ProcStore, AppStore, DeployStore, HypervisorStore
from xsnaga.hypervisor import HypervisorService
from xsnaga.api import (API, AppResource, DeployResource,
                        HypervisorResource, ProcResource)
from xsnaga.handler import (OldDeployHandler, ExpiredProcHandler,
                            ScaleHandler, LostProcHandler)
from xsnaga.proc import ProcFactory, RandomPlacementPolicy


def main():
    options = os.environ
    format = '%(levelname)-8s %(name)s: %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=format)
    store = Store(create_database(options['DATABASE']))
    clock = Clock()
    proc_store = ProcStore(clock, store)
    app_store = AppStore(store)
    deploy_store = DeployStore(clock, store)
    hypervisor_store = HypervisorStore(store)
    hypervisor_service = HypervisorService(
        logging.getLogger('hypervisor.service'), clock, hypervisor_store,
        proc_store)
    hypervisor_service.start()
    policy = RandomPlacementPolicy(logging.getLogger('placement.random'),
                                   hypervisor_store)
    environ = {'SERVER_NAME': options.get('SERVER_NAME', 'localhost'),
               'SERVER_PORT': str(options['PORT'])}

    api = API(logging.getLogger('api'), clock, app_store, proc_store,
              deploy_store, hypervisor_service, environ)
    proc_factory = ProcFactory(logging.getLogger('proc.factory'),
                               clock, proc_store, policy,
                               hypervisor_service, api.callback_url)
    api.add('apps', AppResource(api.log, api.url, app_store))
    api.add('deploys', DeployResource(api.log, api.url, app_store,
                                      deploy_store))
    api.add('hypervisor', HypervisorResource(api.log, api.url, hypervisor_service))
    api.add('procs', ProcResource(api.log, api.url, app_store, proc_store,
                                  proc_factory))

    handlers = []
    handlers.append(OldDeployHandler(logging.getLogger('handler.old-deploy'),
                                     clock, 3, proc_store, proc_factory))
    handlers.append(ExpiredProcHandler(logging.getLogger('handler.expired'),
                                       clock, 3, proc_store, proc_factory))
    handlers.append(ScaleHandler(logging.getLogger('handler.scale'),
                                 clock, 5, app_store, proc_store, proc_factory,
                                 pool.Pool(5)))
    handlers.append(LostProcHandler(logging.getLogger('handler.lost'),
                                    clock, 7, proc_store, 120))
    for handler in handlers:
        handler.start()
    logging.info("Start serving requests on %d" % (int(options['PORT'])))
    pywsgi.WSGIServer(('', int(options['PORT'])), api).serve_forever()


if __name__ == '__main__':
    main()
