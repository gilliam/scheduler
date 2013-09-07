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

from collections import defaultdict
import json

import shortuuid

from etcd import EtcdError


def _is_running(inst):
    return (inst.state == inst.STATE_RUNNING or
            inst.state == inst.STATE_MIGRATING)


class Release(object):

    def __init__(self, store_command, store_query,
                 formation, name, services):
        self.store_command = store_command
        self.store_query = store_query
        self.formation = formation
        self.name = name
        self.services = services

    def _create(self, service):
        """Create an instance of service."""
        template = self.services[service]
        instance = shortuuid.uuid()
        return store.Instance(store_command, formation=formation,
                              service=service,
                              name='%s.%s' % (service, instance),
                              instance=instance,
                              image=template['image'],
                              command=template.get('command'),
                              env=template.get('env', {}))

    def scale(self, scales):
        """Scale this release.

        Return true if there might be more to do to meet the scale.
        """
        insts = [inst for inst in self.store_query.index()
                 if inst.formation == formation and _is_running(inst)]
        per_service = defaultdict(list)
        for inst in insts:
            per_service[inst.service].append(inst)
        for name, insts in per_service.items():
            scale = scales.get(name)
            if scale is None:
                continue
            if len(insts) > scale:
                random.choice(insts).shutdown()
                return True
            elif len(insts) < scale:
                # we need to create an instance
                self._create(service)
                return True

    def migrate(self):
        """Migrate existing instances to the given release.

        Returns true if there might be more instances to migrate.
        """
        insts = [inst for inst in self.store_query.index()
                 if inst.formation == formation and _is_running(inst)]
        for inst in insts:
            service = services.get(inst.service)
            if service is None:
                # this service do not exist in the new release.
                # shut it down!
                inst.shutdown()
                return True
            elif inst.release != release:
                # we need to migrate this to the new release.
                inst.migrate(release, service['image'],
                             service['command'],
                             service.get('env', {}))
                return True


class ReleaseStore(object):
    PREFIX = 'release'

    def __init__(self, etcd):
        self.etcd = etcd

    def _make_key(self, formation, name):
        return '%s/%s/%s' % (self.PREFIX, formation, name)

    def _split_key(self, key):
        _prefix, formation, name = key.split('/', 2)
        assert _prefix == self.PREFIX
        return formation, name

    def get(self, formation, name):
        try:
            result = self.etcd.get(self._make_key(formation, name))
        except EtcdError:
            return None
        else:
            return json.loads(result.value)

    def create(self, formation, name, data):
        try:
            return self.etcd.testandset(
                self._make_key(formation, name), '', json.dumps(data))
        except EtcdError:
            raise Exception("already there.")

    def delete(self, formation, name):
        self.etcd.delete(self._make_key(formation, name))

    def index(self, formation):
        indexkey = '%s/%s' % (self.PREFIX, formation)
        for key, value in self.etcd.get_recursive(indexkey).items():
            formation, name = self._split_key(key)
            yield name, json.loads(value)
