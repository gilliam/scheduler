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

from xsnaga.model import App


class AppStore(object):
    """Application store."""

    def __init__(self, store):
        self.store = store

    def create(self, name, repository, text):
        """Create a new application."""
        app = App(name=name, repository=repository, text=text)
        self.store.add(app)
        self.store.commit()
        return app

    def by_name(self, name):
        return self.store.find(App, App.name == name).one()

    def apps(self):
        """Return an iterable for all apps."""
        return self.store.find(App)
