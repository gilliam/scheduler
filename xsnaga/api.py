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
    

class DeployResource(_BaseResource):
    """The deploy collection that lives under an application."""

    def __init__(self, log, app_store, deploy_store):
        pass

    def _make_deploy(self, deploy):
        """Construct a deploy JSON blob."""
        return {
            'build': deploy.build, 'image': deploy.image,
            'pstable': deploy.pstable, 'config': deploy.config,
            'text': deploy.text, 'when': deploy.when.isoformat(' '),
            'id': deploy.id,
            'links': {
                '': ''
                }
            }

    def index(self, request, name):
        app = self.app_store.by_name(name)
        offset = request.params.get('offset', 0)
        page_size = request.params.get('page_size', 10)
        deploys = list(app.deploys[offset:offset + page_size])
        body = {'deploys': []}
        for deploy in deploys:
            body['deploys'].append(self._make_deploy(deploy))
        if len(deploys) == n:
            body['next'] = url('deploys', name=name, offset=offset + page_size,
                               page_size=page_size)
        return Response(status=200, body=body)

    def create(self, request, name):
        data = request.json()
        app = self.app_store.by_name(name)
        deploy = self.deploy_store.create(app, data['build'], data['image']‚
            data['pstable'], data['config'], data['text'])
        response = Response(status=201)
        response.headers.add('Location', url('deploy', name=name, id=deploy.id))
        return response

    def latest(self, request, name):
        pass


class API(object):

    def __init__(self, log):
        self._controllers = {
            'deploys': DeployResource(log, app_store, deploy_store),
            }
        self.mapper = Mapper()
        self.mapper.resource("deploy", "deploys", path_prefix='/app/{name}',
                             collection={'latest': 'GET'})



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
