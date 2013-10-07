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
import random
import logging

from etcd import EtcdError

from . import store

def _is_running(inst):
    return (inst.state == inst.STATE_PENDING or 
            inst.state == inst.STATE_RUNNING or
            inst.state == inst.STATE_MIGRATING)


class Release(object):

    def __init__(self, store_command, store_query,
                 formation, name, services):
        self.log = logging.getLogger('release.%s:%s' % (formation, name))
        self.store_command = store_command
        self.store_query = store_query
        self.formation = formation
        self.name = name
        self.services = services

    def _create(self, service):
        """Create an instance of service."""
        template = self.services[service]
        return store.create(self.store_command,
                            self.formation, service,
                            self.name,
                            template['image'],
                            template.get('command'),
                            env=template.get('env', {}),
                            ports=template.get('ports', []))

    def _collect(self, release=None):
        return [inst for inst in self.store_query.index()
                if inst.formation == self.formation
                and (release is None or release == inst.release)
                and _is_running(inst)]

    def _group(self, insts):
        groups = defaultdict(list)
        for inst in insts:
            groups[inst.service].append(inst)
        return groups

    def scale(self, scales):
        """Scale this release.

        Return true if there might be more to do to meet the scale.
        """
        insts = [inst for inst in self.store_query.index()
                 if inst.formation == self.formation
                 and inst.release == self.name
                 and _is_running(inst)]
        per_service = defaultdict(list)
        for inst in insts:
            per_service[inst.service].append(inst)
        for name, scale in scales.items():
            insts = per_service.get(name, [])
            if len(insts) > scale:
                random.choice(insts).shutdown()
                return True
            elif len(insts) < scale:
                # we need to create an instance
                self._create(name)
                return True

    def migrate(self, from_name=None):
        """Migrate existing instances to the given release.

        Returns true if there might be more instances to migrate.
        """
        inst_map = dict(self._group(self._collect(from_name)))
        return self._migrate_to_release(inst_map)

    def _compare_instance_to_service(self, inst, service):
        inst_env = inst.env or {}
        serv_env = service['env'] or {}
        inst_ports = inst.ports or []
        serv_ports = service['ports'] or []
        return (inst.image == service['image']
                and inst.command == service['command']
                and inst_env == serv_env
                and inst_ports == serv_ports)

    def _migrate_to_release(self, inst_map):
        insts = [inst
                 for name in self._build_order()
                 for inst in inst_map.get(name, [])]
        insts = [inst for inst in insts
                 if inst.release != self.name]
        cnt = len(insts)
        self.log.info("instances to migrate: %d" % (cnt,))
        for inst in insts:
            service = self.services[inst.service]
            if self._compare_instance_to_service(inst, service):
                self.log.info("re-release %s" % (inst.name,))
                inst.rerelease(self.name)
            else:
                self.log.info("migrate %s" % (inst.name,))
                inst.migrate(self.name, service['image'],
                             service['command'],
                             service.get('env', {}),
                             service.get('ports', []))
            return cnt > 1

    def _build_order(self):
        order = self.services.keys()
        for name, defn in self.services.items():
            requires = defn.get('requires', [])
            for require in requires:
                idx = order.index(require)
                if idx < order.index(name):
                    order.remove(name)
                    order.insert(idx, name)
        return reversed(order)


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
        try:
            for key, value in self.etcd.get_recursive(indexkey).items():
                formation, name = self._split_key(key)
                yield name, json.loads(value)
        except ValueError:
            pass

