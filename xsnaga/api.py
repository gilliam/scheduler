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
from webob.exc import HTTPNotFound
from routes import Mapper, url

mapper = Mapper()

def route(p):
    def decl(f):
        mapper.connect(p, action=f)
        return f
    return dec

class _BaseResource(object):
    """Base resource that do not allow anything."""

    def _method_not_allowed(self, request, *args, **kw):
        return Response(status=405)

    def _check_not_found(self, item):
        if item is None:
            raise HTTPNotFound()

    index = _method_not_allowed
    create = _method_not_allowed
    new = _method_not_allowed
    update = _method_not_allowed
    delete = _method_not_allowed
    show = _method_not_allowed
    edit = _method_not_allowed


def link(_url_name, **kw):
    title = kw.pop('title', None)
    link = {'href': url(url_name, **kw)}
    if title is not None:
        link['title'] = title
    return link


def links(**kw):
    return kw


class AppResource(_BaseResource):

    def _build(self, app):
        """Return a representation of the app."""
        return {
            'name': app.name, 'scale': app.scale,
            }

    def scale(self, request, name):
        """Set new scale parameters for the app."""
        app = self.app_store.by_name(name)
        self._check_not_found(app)
        # Simply set them without checking anything really.
        app.scale = request.json
        

class DeployResource(_BaseResource):
    """The deploy collection that lives under an application."""

    def __init__(self, log, app_store, deploy_store):
        pass

    def _build(self, app, deploy):
        """Construct a deploy JSON blob."""
        return {
            'build': deploy.build, 'image': deploy.image,
            'pstable': deploy.pstable, 'config': deploy.config,
            'text': deploy.text, 'when': deploy.when.isoformat(' '),
            'id': deploy.id,
            '_links': links(
                self=url('deploy', name=app.name, id=deploy.id),
                )
            }

    def index(self, request, name):
        app = self.app_store.by_name(name)
        self._check_not_found(app)

        offset = request.params.get('offset', 0)
        page_size = request.params.get('page_size', 10)
        deploys = list(app.deploys[offset:offset + page_size])
        body = {
            'deploys': [self._build(app, deploy) for deploy in deploys],
            '_links': links(
                next=url('deploys', name=app.name, 
                         offset=offset + page_size,
                         page_size=page_size))
            }
        return Response(status=200, body=body)

    def create(self, request, name):
        app = self.app_store.by_name(name)
        self._check_not_found(app)
        data = request.json
        deploy = self.deploy_store.create(app, data['build'], data['image']‚
            data['pstable'], data['config'], data['text'])
        response = Response(status=201)
        response.headers.add('Location', url('deploy', name=name, id=deploy.id))
        return response

    def latest(self, request, name):
        pass


class API(object):

    def __init__(self, log):
        self.controllers = {
            'deploys': DeployResource(log, app_store, deploy_store),
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


def transaction(storm, f):
    """Make a transaction wrapper around f."""
    def wrapper(*args, **kw):
        try:
            try:
                return f(*args, **kw)
            except:
                store.rollback()
                raise
        finally:
            store.commit()
    return wrapper


class API(object):

    def __init__(self, log, clock, app_store, proc_store,
                 deploy_store):
        """."""
        self.log = log
        self.clock = clock
        self.app_store = app_store
        self.proc_store = proc_store
        self.deploy_store = deploy_store

    def _make_app(self, app):
        return {
            'name': app.name,
            'repository': app.name,
            'text': app.text,
            }

    @route('/app/{name}', method=['GET'])
    def get_app(self, request, name):
        pass

    def _make_deploy(self, deploy):
        return {
            'build': deploy.build, 'image': deploy.image,
            'pstable': deploy.pstable, 'config': deploy.config,
            'text': deploy.text, 'when': deploy.when.isoformat(' '),
            'id': deploy.id
            }

    @route('/app/{name}/deploy', method='POST')
    def create_deploy(self, request, name):
        data = request.json()
        app = self.app_store.by_name(name)
        deploy = self.deploy_store.create(app, data['build'], data['image']‚
            data['pstable'], data['config'], data['text'])
        response = Response(status=201)
        response.headers.add('Location', '/api/%s/deploy/%d' % (
                app.name, deploy.id))
        return response

    @route('/app/{name}/deploy', method='GET')
    def index_deploy(self, request, name, deploy_id):
        app = self.app_store.by_name(name)
        offset = request.params.get('offset', 0)
        page_size = request.params.get('page_size', 10)
        deploys = list(app.deploys[offset:offset + page_size])
        body = {'deploys': []}
        for deploy in deploys:
            body['deploys'].append(self._make_deploy(deploy))
        if len(deploys) == n:
            body['next'] = '/app/%s/deploy?offset=%d&page_size=%d' % (
                name, offset + page_size, page_size)
        return Response(status=200, body=body)

    @route('/app/{name}/deploy/latest', method='GET')
    def latest_deploy(self, request, name):
        app = self.app_store.by_name(name)
        return Response(status=200, body=self._make_deploy(app.deploy))

    @route('/app/{name}/deploy/{deploy_id}', method='GET')
    def get_deploy(self, request, name, deploy_id):
        app = self.app_store.by_name(name)
        deploy = self.deploy_store.by_id_for_app(int(deploy_id), app)
        return Response(status=200, body=self._make_deploy(deploy))

    @route('/app/{name}/scale', method='GET')
    def get_scale(self, request, name):
        """Return scale for an application."""
        app = self.app_store.by_name(name)
        return Response(status=200, body=app.scale or {})

    @route('/app/{name}/scale', method='PUT')
    def set_scale(self, request, name):
        """Set scale for an application."""
        app = self.app_store.by_name(name)
        app.set_scale(request.json())
        return Response(status=200)

    @route('/app', method=['POST'])
    def create_app(self, request):
        """Create a new application instance."""
        data = request.json()
        self.app_store.create(data['name'], data['repository'],
                              data.get('text', data['name']))
        response = Response(status=201)
        response.headers.add('Location', '/api/' + data['name'])
        return response

    @route('/app', method=['POST'])
    def index_app(self, request):
        """Return a list of all applications."""
        body = {}
        for app in self.app_store.apps():

    @wsgify
    def __call__(self, request):
        route = mapper.match(request.path_info, request.environ)
        action = route.pop('action')
        return action(request, **action)
