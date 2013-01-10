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


class DeployStore(object):
    """."""

    def __init__(self, log, clock, store):
        self.log = log
        self.clock = clock
        self.store = store

    def create(self, app, build, image, pstable, config, text):
        deploy = Deploy()
        deploy.app_id = app.id
        deploy.build = build
        deploy.image = image
        deploy.pstable = pstable
        deploy.config = config
        deploy.text = text
        deploy.when = datetime.datetime.utcfromtimestamp(self.clock.time())
        self.store.add(deploy)
        self.store.commit()
        return deploy

    def by_id_for_app(self, id, app):
        """Return a specific deploy."""
        return self.store.find(Deploy, (Deploy.app_id == app.id) & (
                Deploy.id == id)).one()
