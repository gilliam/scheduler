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

from webob.dec import wsgify
from webob.exc import HTTPNotFound, HTTPBadRequest
from webob import Response
from routes import Mapper, URLGenerator


class _BaseResource(object):
    """Base resource that do not allow anything."""

    def _method_not_allowed(*args, **kw):
        return Response(status=405)

    def _check_not_found(self, item):
        if item is None:
            raise HTTPNotFound()

    def _assert_request_content(self, request):
        if not request.content_length:
            raise HTTPBadRequest()
        if request.json is None:
            raise HTTPBadRequest()
        return request.json

    index = _method_not_allowed
    create = _method_not_allowed
    update = _method_not_allowed
    delete = _method_not_allowed
    show = _method_not_allowed


def _build_app(url, app):
    """Return a representation of the app."""
    return {
        'kind': 'gilliam#app', 'name': app.name,
        'repository': app.repository, 'text': app.text,
        '_links': {
            'self': url('app', app_name=app.name),
            }
        }


def _build_deploy(url, app, deploy):
    """Return a representation of the deploy."""
    return {
        'kind': 'gilliam#deploy', 'build': deploy.build,
        'image': deploy.image, 'pstable': deploy.pstable,
        'config': deploy.config, 'text': deploy.text,
        'when': deploy.timestamp.isoformat(' '), 'id': deploy.id,
        '_links': {
            'self': url('deploy', app_name=app.name,
                        deploy_id=deploy.id),
            }
        }


def _build_hypervisor(url, hypervisor):
    return {
        'kind': 'gilliam#hypervisor', 'host': hypervisor.host,
        '_links': {
            'self': url('hypervisor', hostname=hypervisor.host)
            }
        }


class _AppResource(_BaseResource):
    """The app resource."""

    def __init__(self, log, url, app_store):
        self.log = log
        self.url = url
        self.app_store = app_store

    def index(self, request, format=None):
        """."""
        apps = self.app_store.apps()
        items = [_build_app(self.url, app) for app in apps]
        return Response(json={'items': items}, status=200)

    def show(self, request, app_name, format=None):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        return Response(json=_build_app(self.url, app), status=200)

    def create(self, request, format=None):
        data = self._assert_request_content(request)
        app = self.app_store.create(data['name'], data['repository'],
                                    data.get('text', data['name']))
        print repr(app)
        response = Response(json=_build_app(self.url, app), status=201)
        response.headers.add('Location', self.url('app', app_name=app.name))
        return response

    def update(self, request, app_name, format=None):
        """Update an existing app."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        data = self._assert_request_content(request)
        app.repository = data['repository']
        app.text = data.get('text', app.name)
        self.app_store.update(app)
        return Response(json=_build_app(self.url, app), status=200)

    def delete(self, request, app_name, format=None):
        """Delete the app."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        self.app_store.remove(app)
        return Response(status=204)

    def scale(self, request, app_name, format=None):
        """Return current scale for the app."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        return Response(json=app.scale, status=200)

    def set_scale(self, request, app_name, format=None):
        """Set new scale parameters for the app."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        data = self._assert_request_content(request)
        self.app_store.set_scale(app, data)
        return Response(status=200)
        

class _DeployResource(_BaseResource):
    """The deploy collection that lives under an application."""

    def __init__(self, log, url, app_store, deploy_store):
        self.log = log
        self.url = url
        self.app_store = app_store
        self.deploy_store = deploy_store

    def index(self, request, app_name):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        offset = int(request.params.get('offset', 0))
        page_size = int(request.params.get('page_size', 10))
        deploys = list(app.deploys[offset:offset + page_size])
        links = {
            'self': self.url('deploys', app_name=app_name,
                        offset=offset, page_size=page_size),
            'latest': self.url('deploy', app_name=app_name,
                          deploy_id='latest')
            }
        if offset > 0:
            links['prev'] = self.url('deploys', app_name=app.name,
                                offset=offset - page_size,
                                page_size=page_size)
        if len(deploys) == page_size:
            links['next'] = self.url('deploys', app_name=app.name,
                                offset=offset + page_size,
                                page_size=page_size)

        items = [_build_deploy(self.url, app, deploy) for deploy in deploys],
        return Response(json={'items': items, '_links': links}, status=200)

    def create(self, request, app_name, format=None):
        """Create a new deploy for the app."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        data = self._assert_request_content(request)
        app.deploy = self.deploy_store.create(app, data['build'], data['image'],
            data['pstable'], data['config'], data['text'])
        self.app_store.update(app)
        response = Response(json=_build_deploy(self.url, app, app.deploy), status=201)
        response.headers.add('Location', self.url('deploy', app_name=app.name,
                                             deploy_id=app.deploy.id))
        return response

    def show(self, request, app_name, deploy_id, format=None):
        """Return a specific deploy."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        if deploy_id == 'latest':
            deploy = app.deploy
        else:
            deploy = self.deploy_store.by_id_for_app(int(deploy_id), app)
        self._check_not_found(deploy)
        return Response(json=_build_deploy(self.url, app, deploy), status=200)

    def delete(self, request, app_name, deploy_id, format=None):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        deploy = self.by_id_for_app(int(deploy_id), app)
        self._check_not_found(deploy)
        if deploy is app.deploy:
            raise HTTPBadRequest()
        self.deploy_store.remove(deploy)
        return Response(status=204)

    def latest(self, request, app_name, format=None):
        """Latest deploy."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        return Response(json=_build_deploy(self.url, app, app.deploy), status=200)


class _ProcResource(_BaseResource):

    def __init__(self, log, url, proc_store):
        self.log = log
        self.url = url
        self.proc_store = proc_store

    def set_state(self, request, app_name, proc_name, proc_id, format=None):
        """Set state for a specific process."""
        proc = self.proc_store.by_app_proc_and_id(app_name, proc_name, proc_id)
        if proc is not None:
            proc.state = unicode(request.params.get('state'))
            proc.port = int(request.params.get('port'))
            if 'host' in request.params:
                proc.host = unicode(request.params.get('host'))
            self.proc_store.update(proc)


class _HypervisorResource(_BaseResource):
    """Resource controller for our hypervisors."""

    def __init__(self, log, url, hypervisor_service):
        self.log = log
        self.url = url
        self.service = hypervisor_service

    def index(self):
        body = {}
        for controller in self.service.hypervisors():
            body[hypervisor.name] = _build_hypervisor(self.url, controller.model)
        return Response(json=body, status=200)

    def _get(self, request, host):
        controller = self.service.get(host)
        if hypervisor is None:
            raise HTTPNotFound()
        return controller

    def show(self, request, hostname):
        controller = self._get(hostname)
        return Response(json=_build_hypervisor(self.url, controller.model),
                        status=200)

    def create(self, request, format=None):
        """Create a hypervisor."""
        data = self._assert_request_content(request)
        controller = self.service.create(request.json['host'])
        return Response(json=_build_hypervisor(self.url, controller.model),
                        status=201)


class API(object):
    """Our REST API WSGI application."""

    def __init__(self, log, clock, app_store, proc_store, deploy_store,
                 hypervisor_service, environ={}):
        self.mapper = Mapper()
        self.url = URLGenerator(self.mapper, environ)
        self.controllers = {
            'apps': _AppResource(log, self.url, app_store),
            'deploys': _DeployResource(log, self.url, app_store, deploy_store),
            'hypervisor': _HypervisorResource(log, self.url, hypervisor_service),
            'procs': _ProcResource(log, self.url, proc_store),
            }
        
        app_collection = self.mapper.collection("apps", "app",
            path_prefix='/app', controller="apps",
            collection_actions=['index', 'create'],
            member_actions=['show', 'update', 'delete'],
            member_prefix='/{app_name}')
        app_collection.member.link('scale', 'scale_app', action='scale')
        app_collection.member.link('scale', 'scale_app', action='set_scale',
            method='PUT')

        deploy_collection = self.mapper.collection("deploys", "deploy",
            path_prefix='/app/{app_name}/deploy', controller="deploys",
            collection_actions=['index', 'create'],
            member_actions=['show', 'delete'], member_prefix='/{deploy_id}')
        deploy_collection.link('latest', 'latest_deploy', action='latest')

        proc_collection = self.mapper.collection("procs", "proc",
            path_prefix='/app/{app_name}/proc/{proc_name}',
            controller='procs', collection_actions=['index'],
            member_actions=['show', 'delete'], member_prefix='/{proc_id}')
        proc_collection.member.link('state', 'set_state', action='set_state',
                                    method='POST')

        hypervisor_collection = self.mapper.collection("hypervisors",
            "hypervisor", path_prefix='/hypervisor',
            collection_actions=['index', 'create'],
            member_actions=['show', 'delete'],
            member_prefix='/{hostname}')
        print self.mapper

    def callback_url(self, proc):
        return self.url('set_state', app_name=proc.app.name,
                        proc_name=proc.name, proc_id=proc.proc_id,
                        qualified=True)

    @wsgify
    def __call__(self, request):
        route = self.mapper.match(request.path_info, request.environ)
        if route is None:
            raise HTTPNotFound()
        controller = self.controllers[route.pop('controller')]
        action = getattr(controller, route.pop('action'))
        return action(request, **route)
