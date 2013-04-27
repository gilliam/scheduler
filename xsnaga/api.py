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
from webob.dec import wsgify
from webob.exc import HTTPNotFound, HTTPBadRequest
from webob import Response
from routes import Mapper, URLGenerator


def _build_app(url, app):
    """Return a representation of the app."""
    data = {
        'kind': 'gilliam#app',
        'name': app.name,
        'text': app.text,
        'links': {
            'self': url('app', app_name=app.name),
            }
        }
    return data


def _build_release(url, app, release):
    """Return a representation of the deploy."""
    return {
        'kind': 'gilliam#release',
        'version': release.version,
        'text': release.text,
        'build': release.build,
        'image': release.image,
        'pstable': release.pstable,
        'config': release.config,
        'scale': release.scale or {},
        'timestamp': release.timestamp.isoformat(' '),
        'links': {
            'self': url('release', app_name=app.name,
                        version=release.version),
            'scale': url('scale_release', app_name=app.name,
                         version=release.version),
            }
        }


def _build_hypervisor(url, hypervisor):
    return {
        'kind': 'gilliam#hypervisor', 'host': hypervisor.host,
        'port': hypervisor.port,
        'options': hypervisor.options,
        'capacity': hypervisor.capacity,
        'links': {
            'self': url('hypervisor', hostname=hypervisor.host)
            }
        }


def _build_proc(url, app, release, hypervisor, proc):
    return {
        'kind': 'gilliam#proc',
        'type': proc.proc_type,
        'name': proc.proc_name,
        'state': proc.actual_state,
        'changed_at': proc.changed_at.isoformat(' '),
        'release': _build_release(url, app, release),
        'host': hypervisor.host,
        'port': proc.port,
        }


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

    def _method_not_allowed(*args, **kw):
        return Response(status=405)

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

    index = _method_not_allowed
    create = _method_not_allowed
    update = _method_not_allowed
    delete = _method_not_allowed
    show = _method_not_allowed


class AppResource(_BaseResource):
    """The app resource."""

    def __init__(self, log, url, app_store):
        self.log = log
        self.url = url
        self.app_store = app_store

    def index(self, request):
        items = self.app_store.apps()
        return _collection(request, items, partial(self.url, 'apps'),
                           partial(_build_app, self.url))

    def show(self, request, app_name):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        return Response(json=_build_app(self.url, app), status=200)

    def create(self, request):
        data = self._assert_request_content(request, 'name')
        app = self.app_store.create(unicode(data['name']),
                                    unicode(data.get('text', data['name'])))
        response = Response(json=_build_app(self.url, app), status=201)
        response.headers.add('Location', self.url('app', app_name=app.name))
        return response

    def update(self, request, app_name):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        data = self._assert_request_content(request)
        app.text = unicode(data.get('text', app.name))
        self.app_store.persist(app)
        return Response(json=_build_app(self.url, app), status=200)

    def delete(self, request, app_name):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        self.app_store.remove(app)
        return Response(status=204)
        

class ReleaseResource(_BaseResource):

    def __init__(self, log, url, app_store, release_store):
        self.log = log
        self.url = url
        self.app_store = app_store
        self.release_store = release_store

    def index(self, request, app_name):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        releases = self.release_store.for_app(app)
        return _collection(request, releases,
                           partial(self.url, 'releases', app_name=app_name),
                           partial(_build_release, self.url, app))

    def create(self, request, app_name):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        data = self._assert_request_content(request, 'build', 'image',
                                            'pstable', 'config', 'text')
        release = self.release_store.create(app,
                                            unicode(data['text']),
                                            unicode(data['build']),
                                            unicode(data['image']),
                                            data['pstable'],
                                            data['config'])
        response = Response(json=_build_release(self.url, app, release),
                            status=201)
        response.headers.add('Location',
                             self.url('release', app_name=app.name,
                                      version=release.version))
        return response

    def show(self, request, app_name, version):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        release = self.release_store.by_app_version(app, version)
        self._check_not_found(release)
        return Response(json=_build_release(self.url, app, release),
                        status=200)

    def set_scale(self, request, app_name, version):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        release = self.release_store.by_app_version(app, version)
        self._check_not_found(release)
        scale = self._assert_request_content(request)
        if not self._check_valid_scale(release, scale):
            raise HTTPBadRequest()
        release.scale = scale
        self.release_store.persist(release)
        return Response(json=_build_release(self.url, app, release),
                        status=200)

    def _check_valid_scale(self, release, scale):
        for proc_type in scale:
            if proc_type not in release.pstable:
                return False
        return True

    def delete(self, request, app_name, version):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        release = self.release_store.by_app_version(app, version)
        self._check_not_found(release)
        self.release_store.remove(release)
        return Response(status=204)

    
class ProcResource(_BaseResource):
    """Resource that exposes all procs for a specific app."""

    def __init__(self, log, url, app_store, proc_store, release_store,
                 hypervisor_store, proc_factory):
        self.log = log
        self.url = url
        self.app_store = app_store
        self.proc_store = proc_store
        self.release_store = release_store
        self.hypervisor_store = hypervisor_store
        self.proc_factory = proc_factory

    # we need a specific build function here since we need to
    # fetch the release.
    def _build(self, app, proc):
        release = self.release_store.get(proc.release_id)
        hypervisor = self.hypervisor_store.get(proc.hypervisor_id)
        return _build_proc(self.url, app, release, hypervisor, proc)

    def index(self, request, app_name):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        return _collection(request, self.proc_store.for_app(app),
                           partial(self.url, 'procs', app_name=app_name),
                           partial(self._build, app))

    def show(self, request, app_name, proc_name):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        proc = self.proc_store.by_app_name(app, proc_name)
        self._check_not_found(proc)
        release = self.release_store.get(proc.release_id)
        hypervisor = self.hypervisor_store.get(proc.hypervisor_id)
        return Response(status=200,
                        json=_build_proc(self.url, app, release, hypervisor,
                                         proc))

    def delete(self, request, app_name, proc_name):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        proc = self.proc_store.by_app_name(app, proc_name)
        self._check_not_found(proc)
        self.proc_factory.stop_proc(proc)
        return Response(status=204)

    def set_state(self, request, app_name, proc_name):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        proc = self.proc_store.by_app_name(app, proc_name)
        if proc is not None:
            #proc.port = int(request.params.get('port'))
            self.proc_state.set_actual_state(unicode(request.params.get('state')))
        return Response(status=204)


class HypervisorResource(_BaseResource):
    """Resource controller for our hypervisors."""

    def __init__(self, log, url, eventbus, store):
        self.log = log
        self.url = url
        self.eventbus = eventbus
        self.store = store

    def _get(self, host):
        hypervisor = self.store.by_host(host)
        if hypervisor is None:
            raise HTTPNotFound()
        return hypervisor

    def index(self, request):
        procs = self.proc_store.procs_for_app(app, proc_name)
        return _collection(request, self.store.items,
                           partial(self.url, 'hypervisors'),
                           partial(_build_hypervisor, self.url))

    def show(self, request, hostname):
        hypervisor = self._get(hostname)
        return Response(json=_build_hypervisor(self.url, hypervisor),
                        status=200)

    def create(self, request):
        data = self._assert_request_content(request, 'host', 'port',
                                            'capacity', 'options')
        hypervisor = self.store.create(unicode(data['host']),
                                       int(data['port']),
                                       data['capacity'],
                                       data['options'])
        self.eventbus.emit('hypervisor-create', hypervisor)
        return Response(json=_build_hypervisor(self.url, hypervisor),
                        status=201)


class API(object):
    """Our REST API WSGI application."""

    def __init__(self, log, environ={}):
        self.log = log
        self.mapper = Mapper()
        self.url = URLGenerator(self.mapper, environ)
        self.controllers = {}
        
        app_collection = self.mapper.collection(
            "apps", "app",
            path_prefix='/app', controller="apps",
            collection_actions=['index', 'create'],
            member_actions=['show', 'update', 'delete'],
            member_prefix='/{app_name}', formatted=False)

        release_collection = self.mapper.collection(
            "releases", "release",
            path_prefix='/app/{app_name}/release', controller="releases",
            collection_actions=['index', 'create'],
            member_actions=['show', 'delete'], member_prefix='/{version}',
            formatted=False)
        release_collection.member.link(
            'scale', 'scale_release', action='set_scale',
            method='PUT', formatted=False)

        proc_collection = self.mapper.collection(
            "procs", "proc",
            path_prefix='/app/{app_name}/proc',
            controller='procs', collection_actions=['index'],
            member_actions=['show', 'delete'], member_prefix='/{proc_name}',
            formatted=False)
        proc_collection.member.link(
            'state', 'set_state', action='set_state',
            method='POST', formatted=False)

        hypervisor_collection = self.mapper.collection(
            "hypervisors", "hypervisor",
            path_prefix='/hypervisor',
            collection_actions=['index', 'create'],
            member_actions=['show', 'delete'],
            member_prefix='/{hostname}', formatted=False)

    def add(self, name, controller):
        self.controllers[name] = controller

    def callback_url(self, app, proc):
        return self.url('set_state', app_name=app.name,
                        proc_name=proc.proc_name, qualified=True)

    @wsgify
    def __call__(self, request):
        route = self.mapper.match(request.path_info, request.environ)
        if route is None:
            raise HTTPNotFound()
        controller = self.controllers[route.pop('controller')]
        action = getattr(controller, route.pop('action'))
        return action(request, **route)
