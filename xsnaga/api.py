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
from routes import Mapper, url


class _BaseResource(object):
    """Base resource that do not allow anything."""

    def _method_not_allowed(self, request, *args, **kw):
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


def _build_app(app):
    """Return a representation of the app."""
    return {
        'kind': 'gilliam#app', 'name': app.name,
        'repository': app.repository, 'text': app.text,
        '_links': {
            'self': url('app', app_name=app.name),
            }
        }


def _build_deploy(app, deploy):
    """Return a representation of the deploy."""
    return {
        'kind': 'gilliam#deploy', 'build': deploy.build,
        'image': deploy.image, 'pstable': deploy.pstable,
        'config': deploy.config, 'text': deploy.text,
        'when': deploy.when.isoformat(' '), 'id': deploy.id,
        '_links': {
            'self': url('deploy', app_name=app.name,
                        deploy_id=deploy.id),
            }
        }


class _AppResource(_BaseResource):
    """The app resource."""

    def __init__(self, log, app_store):
        self.log = log
        self.app_store = app_store

    def create(self, request):
        data = self._assert_request_content(request)
        app = self.app_store.create(data['name'], data['repository'],
                                    data.get('text', data['name']))
        response = Response(_build_app(app), status=201)
        response.headers.add('Location', url('app', app_name=app.name))
        return response

    def update(self, request, app_name):
        """Update an existing app."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        data = self._assert_request_content(request)
        app.repository = data['repository']
        app.text = data.get('text', app.name)
        self.app_store.update(app)
        return Response(_build_app(app), status=200)

    def delete(self, request, app_name):
        """Delete the app."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        self.app_store.remove(app)
        return Response(status=204)

    def scale(self, request, app_name):
        """Return current scale for the app."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        return Response(app.scale, status=200)

    def set_scale(self, request, app_name):
        """Set new scale parameters for the app."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        data = self._assert_request_content(request)
        self.app_store.set_scale(app, data)
        return Response(status=200)
        

class _DeployResource(_BaseResource):
    """The deploy collection that lives under an application."""

    def __init__(self, log, app_store, deploy_store):
        self.log = log
        self.app_store = app_store
        self.deploy_store = deploy_store

    def index(self, request, app_name):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        offset = int(request.params.get('offset', 0))
        page_size = int(request.params.get('page_size', 10))
        deploys = list(app.deploys[offset:offset + page_size])

        links = {
            'self': url('deploys', app_name=app_name,
                        offset=offset, page_size=page_size),
            'latest': url('deploy', app_name=app_name,
                          deploy_id='latest')
            }
        if offset > 0:
            links['prev'] = url('deploys', app_name=app.name,
                                offset=offset - page_size,
                                page_size=page_size)
        if len(deploys) == page_size:
            links['next'] = url('deploys', app_name=app.name,
                                offset=offset + page_size,
                                page_size=page_size)

        items = [_build_deploy(app, deploy) for deploy in deploys],
        return Response({'items': items, '_links': links}, status=200)

    def create(self, request, app_name):
        """Create a new deploy for the app."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        data = self._assert_request_content(request)
        app.deploy = self.deploy_store.create(app, data['build'], data['image']‚
            data['pstable'], data['config'], data['text'])
        self.app_store.update(app)
        response = Response(_build_deploy(app, app.deploy), status=201)
        response.headers.add('Location', url('deploy', app_name=app.name,
                                             deploy_id=app.deploy.id))
        return response

    def show(self, request, app_name, deploy_id):
        """Return a specific deploy."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        deploy = self.by_id_for_app(int(deploy_id), app)
        self._check_not_found(deploy)
        return Response(_build_deploy(app, deploy), status=200)

    def delete(self, request, app_name, deploy_id):
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        deploy = self.by_id_for_app(int(deploy_id), app)
        self._check_not_found(deploy)
        if deploy is app.deploy:
            raise HTTPBadRequest()
        self.deploy_store.remove(deploy)
        return Response(status=204)

    def latest(self, request, app_name):
        """Latest deploy."""
        app = self.app_store.by_name(app_name)
        self._check_not_found(app)
        return Response(_build_deploy(app, app.deploy), status=200)


class API(object):
    """Our REST API WSGI application."""

    def __init__(self, log, clock, app_store, proc_store, deploy_store):
        self.controllers = {
            'apps': _AppResource(log, app_store),
            'deploys': _DeployResource(log, app_store, deploy_store),
            }

        self.mapper = Mapper()
        
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
            member_actions=['show', 'delete'], member_prefix='/{proc_id')

        hypervisor_collection = self.mapper.collection("hypervisors",
            "hypervisor", path_prefix='/hypervisor',
             collection_actions=['index', 'create'],
             member_actions=['show', 'update', 'delete'],
             member_prefix='/{host}')

    @wsgify
    def __call__(self, request):
        route = mapper.match(request.path_info, request.environ)
        controller = self.controllers[route.pop('controller')]
        action = getattr(controller, route.pop('action'))
        return action(request, **action)
