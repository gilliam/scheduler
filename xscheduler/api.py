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

import logging
import json
from optparse import OptionParser
import os
import time

import etcd
from functools import partial
from gevent import pywsgi
from gilliam.service_registry import (ServiceRegistryClient, Resolver)
from routes import Mapper, URLGenerator
from webob.dec import wsgify
from webob.exc import HTTPNotFound, HTTPBadRequest
from webob import Response
from etcd import EtcdError

from .cache import make_client as make_cache_client
from xscheduler import store
from xscheduler.release import ReleaseStore, Release


def _collection(request, items, url, build, **links):
    """Convenience function for handing a collection request (aka
    'index').

    @param request: The HTTP request.
    @param items: Something that can be sliced and that will be fed
        into the C{build} function to generate a JSON representation
        of the item.
    @param url: a callable that returns a URL to the collection, and
        that also accepts keyword argments that will become query
        parameters to the URL.
    @param build: a callable that takes a single parameter, the item,
        and returns a python C{dict} that is the item representation.
        
    @param links: Additional links for the representation.
    """
    offset = int(request.params.get('offset', 0))
    page_size = int(request.params.get('page_size', 10))
    items = list(items[offset:offset + page_size])
    links['self'] = url(offset=offset, page_size=page_size)
    if offset > 0:
        links['prev'] = url(offset=offset - page_size,
                            page_size=page_size)
    if len(items) == page_size:
        links['next'] = url(offset=offset + page_size,
                            page_size=page_size)

    return Response(json={'items': [build(item) for item in items],
                          'links': links}, status=200)


class _BaseResource(object):
    """Base resource that do not allow anything."""

    def _check_not_found(self, item):
        if item is None:
            raise HTTPNotFound()

    def _assert_request_content(self, request, *fields):
        if not request.content_length:
            raise HTTPBadRequest()
        if request.json is None:
            raise HTTPBadRequest()
        data = request.json
        for field in fields:
            if not field in data:
                raise HTTPBadRequest()
        return data


class FormationStore(object):
    PREFIX = 'formation'

    def __init__(self, etcd):
        self.etcd = etcd

    def _make_key(self, formation):
        return '%s/%s' % (self.PREFIX, formation)

    def _split_key(self, key):
        _prefix, formation = key.split('/', 1)
        assert _prefix == self.PREFIX
        return formation

    def get(self, name):
        try:
            result = self.etcd.get(self._make_key(name))
        except EtcdError:
            return None
        else:
            return json.loads(result.value)

    def create(self, name, data):
        try:
            return self.etcd.testandset(
                self._make_key(name), '', json.dumps(data))
        except EtcdError:
            raise Exception("already there.")

    def delete(self, name):
        self.etcd.delete(self._make_key(name))

    def index(self):
        for key, data in self.etcd.get_recursive(self.PREFIX):
            formation = self._split_key(key)
            yield formation, json.loads(data)

        
class FormationResource(_BaseResource):
    """The formation resource."""

    def __init__(self, log, url, curl, store):
        self.log = log
        self.url = url
        self.curl = curl
        self.store = store

    def _build(self, data):
        data = data.copy()
        data.update({'kind': 'gilliam#formation'})
        return data

    def index(self, request):
        items = self.store.index()
        return _collection(request, items, self.curl, self._build)

    def show(self, request, formation):
        data = self.store.get(formation)
        self._check_not_found(data)
        return Response(json=self._build(data), status=200)

    def create(self, request):
        params = self._assert_request_content(request, 'name')
        self.store.create(params['name'], params)
        response = Response(json=self._build(params), status=201)
        response.headers.add('Location', 
                             self.url(formation=params['name']))
        return response

    def delete(self, request, formation):
        data = self.store.get(formation)
        self._check_not_found(data)
        self.store.remove(formation)
        return Response(status=204)
        

class ReleaseResource(_BaseResource):
    """The app resource."""

    def __init__(self, log, url, curl, store, factory):
        self.log = log
        self.url = url
        self.curl = curl
        self.store = store
        self.factory = factory

    def index(self, request, formation):
        items = [i for (k, i) in self.store.index(formation)]
        return _collection(request, items,
                           partial(self.curl, formation=formation),
                           self._build)

    def _build(self, data):
        data = data.copy()
        data.update({'kind': 'gilliam#release'})
        return data

    def show(self, request, formation, name):
        data = self.store.get(formation, name)
        self._check_not_found(data)
        return Response(json=self._build(data), status=200)

    def create(self, request, formation):
        data = self._assert_request_content(request, 'name', 'services')
        self.store.create(formation, data['name'], data)
        response = Response(json=self._build(data), status=201)
        response.headers.add('Location', self.url(formation=formation,
                                                  name=data['name']))
        return response

    def delete(self, request, formation, name):
        data = self.store.get(formation, name)
        self._check_not_found(data)
        self.store.delete(formation, name)
        return Response(status=204)

    def scale(self, request, formation, name):
        params = self._assert_request_content(request, 'scales')
        data = self.store.get(formation, name)
        self._check_not_found(data)
        release = self.factory(formation, name, data['services'])
        more = release.scale(params['scales'])
        return Response(json=more or False, status=200)

    def migrate(self, request, formation, name):
        params = self._assert_request_content(request)
        data = self.store.get(formation, name)
        self._check_not_found(data)
        release = self.factory(formation, name, data['services'])
        more = release.migrate(params.get('from'))
        print "MIGRATE RESULT", more
        return Response(json=more or False, status=200)


class InstanceResource(_BaseResource):

    def __init__(self, log, url, curl, store, command,
                 state_cache):
        self.log = log
        self.url = url
        self.curl = curl
        self.store = store
        self.command = command
        self.state_cache = state_cache

    # we need a specific build function here since we need to
    # fetch the release.
    def _build(self, data):
        status = self.state_cache.get(data.formation,
                                      data.service,
                                      data.instance)
        data = data.to_json()
        data.update({
                'kind': 'gilliam#instance',
                'status': status.get('state', 'unknown'),
                'reason': status.get('reason', 'unknown'),
                })
        return data

    def index(self, request, formation):
        return _collection(request, self.store.query_formation(formation),
                           partial(self.curl, formation=formation),
                           self._build)

    def create(self, request, formation):
        data = self._assert_request_content(request, 'service', 
                                            'release', 'image',
                                            'command')
        inst = store.create(self.command, formation, data['service'],
                            data['release'], data['image'], data['command'],
                            data.get('env'), data.get('ports'),
                            data.get('assigned_to'),
                            data.get('placement'))
        return Response(status=201, json=self._build(inst))

    def show(self, request, formation, service, instance):
        inst = self.store.get(formation, service, instance)
        self._check_not_found(inst)
        return Response(status=200, json=self._build(inst))

    def delete(self, request, formation, service, instance):
        inst = self.store.get(formation, service, instance)
        self._check_not_found(inst)
        inst.delete()
        return Response(status=201)


class API(object):
    """Our REST API WSGI application."""

    def __init__(self, log, environ={}):
        self.log = log
        self.mapper = Mapper()
        self.url = URLGenerator(self.mapper, environ)
        self.controllers = {}
        
        self.mapper.collection("formations", "formation",
            path_prefix="/formation", controller="formation",
            collection_actions=['index', 'create'],
            member_actions=['show', 'delete'],
            member_prefix="/{formation}", formatted=False)
        release_collection = self.mapper.collection("releases", "release",
            path_prefix="/formation/{formation}/release",
            controller="release",
            collection_actions=['index', 'create'],
            member_actions=['show', 'delete'],
            member_prefix="/{name}", formatted=False)
        release_collection.member.link(
            'scale', 'scale_release', action='scale',
            method='POST', formatted=False)
        release_collection.member.link(
            'migrate', 'migrate_release', action='migrate',
            method='POST', formatted=False)

        instance_collection = self.mapper.collection(
            "instances", "instance",
            path_prefix="/formation/{formation}/instances",
            controller="instance",
            collection_actions=['index', 'create'],
            member_actions=['show', 'delete'],
            member_prefix="/{service}.{instance}",
            formatted=False)
        instance_collection.member.link(
            'restart', 'restart_instance', action='restart',
            method='POST', formatted=False)

    def add(self, name, controller):
        self.controllers[name] = controller

    @wsgify
    def __call__(self, request):
        route = self.mapper.match(request.path_info, request.environ)
        if route is None:
            raise HTTPNotFound()
        controller = self.controllers[route.pop('controller')]
        action = getattr(controller, route.pop('action'))
        return action(request, **route)


def main():
    parser = OptionParser()
    parser.add_option("-p", "--port", dest="port", type=int,
                      default=80, help="listen port",
                      metavar="PORT")
    (options, args) = parser.parse_args()

    format = '%(levelname)-8s %(name)s: %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=format)

    requests_log = logging.getLogger("requests")
    requests_log.setLevel(logging.WARNING)

    formation = os.getenv('GILLIAM_FORMATION')
    store_client = etcd.Etcd(host='_store.%s.service' % (formation,))

    formation_store = FormationStore(store_client)
    release_store = ReleaseStore(store_client)

    store_command = store.InstanceStoreCommand(store_client)
    store_query = store.InstanceStoreQuery(store_client, store_command)
    store_query.start()

    registry_client = ServiceRegistryClient(time)
    registry_resolver = Resolver(registry_client)
    state_cache = make_cache_client(registry_resolver,
                                    '_cache.{0}.service'.format(formation))
    
    api = API(logging.getLogger('api'), {})

    api.add(
        'formation', FormationResource(
            logging.getLogger('api.formation'),
            partial(api.url, 'formation'),
            partial(api.url, 'formations'),
            formation_store))
    api.add(
        'release', ReleaseResource(
            logging.getLogger('api.release'),
            partial(api.url, 'release'),
            partial(api.url, 'releases'),
            release_store,
            partial(Release, store_command, store_query)))
    api.add(
        'instance', InstanceResource(
            logging.getLogger('api.release'),
            partial(api.url, 'instance'),
            partial(api.url, 'instances'),
            store_query, store_command,
            state_cache))

    pywsgi.WSGIServer(('', options.port), api).serve_forever()
