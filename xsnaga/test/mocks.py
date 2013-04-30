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

from functools import partial
from gevent import pywsgi
from webob.dec import wsgify
from webob.exc import HTTPBadRequest, HTTPNotFound
from webob import Response
from routes import Mapper, URLGenerator
import pyee
import requests
import gevent
import uuid
import logging


class Proc(pyee.EventEmitter):

    def __init__(self, id, app, name, image, command, config):
        pyee.EventEmitter.__init__(self)
        self.id = id
        self.app = app
        self.name = name
        self.image = image
        self.command = command
        self.config = config
        self.state = 'init'
        self.port = 6000

    def set_state(self, state):
        self.state = state
        self.emit('state', state)

        
class MockHypervisor(object):
    """Hypervisor."""

    def __init__(self, clock, port, factory=Proc):
        self.log = logging.getLogger('hypervisor')
        self.clock = clock
        self.mapper = Mapper()
        self.mapper.collection("procs", "proc", controller='proc',
                               path_prefix='/proc',
                               collection_actions=['index', 'create'],
                               member_actions=['show', 'delete'],
                               formatted=False)
        self.url = URLGenerator(self.mapper, {'SERVER_NAME': 'localhost',
                                              'SERVER_PORT': port})
        self.server = pywsgi.WSGIServer(('', port), self)
        self.start = self.server.start
        self.stop = self.server.stop
        self.registry = {}
        self.httpclient = requests
        self.factory = factory
        self.requests = []
        self._id = 0

    def _build_proc(self, proc):
        """Build a proc representation.

        @return: a C{dict}
        """
        links = dict(self=self.url('proc', id=proc.id))
        return dict(id=proc.id, app=proc.app, name=proc.name,
                    image=proc.image, config=proc.config,
                    port=proc.port, state=proc.state,
                    command=proc.command, links=links)

    def _get(self, id):
        """Return process with given ID or C{None}."""
        proc = self.registry.get(id)
        if proc is None:
            raise HTTPNotFound()
        return proc

    def add(self, proc):
        self.registry[proc.id] = proc

    def create(self, request):
        """Create new proc."""
        data = self._assert_request_data(request)
        proc = self.factory(self._create_id(),
                            data['app'], data['name'],
                            data['image'], data['command'],
                            data['config'])
        self.registry[proc.id] = proc
        proc.on('state', partial(self._state_callback, proc,
                                 data['callback']))
        response = Response(json=self._build_proc(proc), status=201)
        response.headers.add('Location', self.url('proc', id=proc.id))
        return response

    def index(self, request):
        """Return a representation of all procs."""
        collection = {}
        for id, proc in self.registry.items():
            collection[id] = self._build_proc(proc)
        print collection
        return Response(json=collection, status=200)

    def show(self, request, id):
        """Return a presentation of a proc."""
        return Response(json=self._build_proc(self._get(id)), status=200)

    def delete(self, request, id):
        """Stop and delete process."""
        proc = self._get(id)
        self.registry.pop(proc.id)
        return Response(status=204)

    def _assert_request_data(self, request):
        if not request.json:
            raise HTTPBadRequest()
        return request.json

    def _state_callback(self, proc, callback_url, state):
        """Send state change to remote URL."""
        self.log.info("send state update for proc %s new state %s" % (
                proc.name, state))
        try:
            params = {'name': proc.name, 'port': proc.port, 'state': state}
            response = self.httpclient.post(callback_url,
                                            params=params,
                                            timeout=10,
                                            stream=False)
        except requests.Timeout:
            self.log.error("timeout while sending state change to %s" % (
                    callback_url))
        except RequestException:
            self.log.exception("could not send state update")

    def _create_id(self):
        """Create a new ID for the proc."""
        id = self._id
        self._id += 1
        return 'proc-%d' % (id,)

    @wsgify
    def __call__(self, request):
        route = self.mapper.match(request.path, request.environ)
        if route is None:
            raise HTTPNotFound()
        route.pop('controller')
        action = route.pop('action')
        self.requests.append((request.method, request.path))
        return getattr(self, action)(request, **route)


