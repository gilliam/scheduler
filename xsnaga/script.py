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

"""Orchestrator for Gilliam, a 12 factor application deployment
system.

Usage:
  gilliam-orchestrator [options] DATABASE

Options:
  -h --help                show this help message and quit
  --version                show version and exit
  -p, --port PORT          listen on PORT for API requests [default: 8000]

"""

import logging

from docopt import docopt
from storm.locals import Store, create_database
from gevent import pywsgi
from xsnaga.store import ProcStore, AppStore, DeployStore, HypervisorStore
from xsnaga.hypervisor import HypervisorService
from xsnaga.api import API


def main():
    logging.basicConfig()
    options = docopt(__doc__, version='0.0')
    store = Store(create_database(options['DATABASE']))
    proc_store = ProcStore(clock, store)
    app_store = AppStore(store)
    deploy_store = DeployStore(clock, store)
    hypervisor_store = HypervisorStore(clock, store)
    hypervisor_service = HypervisorService(
        logging.getLogger('hypervisor.service'), clock, store)
    api = API(logging.getLogger('api'), clock, app_store, proc_store,
              deploy_store, hypervisor_service)
    pywsgi.WSGIServer(('', int(options['--port'])), api).serve_forever()
