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

import json

from gevent.event import Event
import gevent
import pyee


class Instance(object):
    """Information about an instance."""

    __attributes__ = (
        'name', 'instance', 'service', 'formation', 'placement',
        'state', 'assigned_to', 'image', 'command', 'env')

    STATE_PENDING_ASSIGNMENT = 'pending-assignment'
    STATE_PENDING_DISPATCH = 'pending-dispatch'
    STATE_DISPATCHED = 'dispatched'
    STATE_RUNNING = 'running'

    STATE_LOST = 'lost'

    def __init__(self, store_command, **kwargs):
        self._store_command = store_command
        for attr in self.__attributes__:
            setattr(self, attr, None)
        self._update(kwargs)

    def update(self, **kwargs):
        self._update(kwargs)
        self._store_command.update(self)

    def assign(self, executor):
        """Assign this instance to given executor."""
        self.update(state=self.STATE_PENDING_DISPATCH,
                    assigned_to=executor)

    def dispatch(self, manager):
        manager.dispatch(self)
        self.update(state=self.STATE_RUNNING)

    def set_state(self, state):
        self.update(state=state)

    def delete(self):
        """Delete this instance."""
        self._store_command.delete(self)

    def to_json(self):
        """Return a python dict."""
        return dict((attr, getattr(self, attr))
                    for attr in self.__attributes__)

    def _update(self, kwargs):
        for attr in self.__attributes__:
            if attr in kwargs:
                setattr(self, attr, kwargs[attr])


class _InstanceStoreCommon(object):
    FACTORY = Instance
    PREFIX = 'formation'

    def _make_key(self, instance):
        return '%s/%s/%s' % (self.PREFIX, instance.formation,
                             instance.name)

    def _split_key(self, key):
        _prefix, form_name, name = key.split('/')
        assert _prefix == self.PREFIX
        return form_name, name


class InstanceStoreCommand(_InstanceStoreCommon):
    """Interface against the instance store that allows commands."""

    def __init__(self, client):
        self.client = client

    def create(self, **kwargs):
        instance = self.FACTORY(self, **kwargs)
        self.client.set(self._make_key(instance), json.dumps(instance.to_json()))

    def delete(self, instance):
        """Delete the given instance."""
        self.client.delete(self._make_key(instance))

    def update(self, instance):
        """Update instance."""
        self.client.set(self._make_key(instance), json.dumps(instance.to_json()))


class InstanceStoreQuery(pyee.EventEmitter,_InstanceStoreCommon):
    """Interface against the instance store that allows querying."""

    def __init__(self, client, store_command):
        pyee.EventEmitter.__init__(self)
        self.client = client
        self.store_command = store_command
        self._store = {}
        self._watcher = None
        self._stopped = Event()
        self._get = lambda f, n: self._store.get((f, n))

    def get(self, f, s, i):
        return self._get(f, '%s.%s' % (s, i))

    def start(self):
        """Start the instance store by reading all state into memory.
        """
        self._store.clear()
        self._get_all_instances()
        self._start_watching()

    def stop(self):
        self._stopped.set()

    def _start_watching(self):
        self._watcher = gevent.spawn(self._do_watch)

    def _get_all_instances(self):
        keys_values = self.client.get_recursive(self.PREFIX)
        for value in keys_values.itervalues():
            print keys_values, repr(value)
            self._create(json.loads(value))

    def _handle_event_SET(self, event):
        print event
        formation, name = self._split_key(event.key)
        instance = self._get(formation, name)
        if instance is not None:
            value = json.loads(event.value)
            if value == instance.to_json():
                # ignore the event if there wasn't any change.
                return
            self._update(instance, value)
        else:
            self._create(value)

    def _handle_event_DELETE(self, event):
        formation, name = self._split_key(event.key)
        instance = self._get(formation, name)
        if instance is not None:
            self._delete(instance)

    def _do_watch(self):
        index = None
        while not self._stopped.is_set():
            event = self.client.watch(self.PREFIX, index=index, timeout=5)
            if event is None:
                continue
            if index is None:
                index = event.index
            if event.index > index:
                index = event.index
            methodname = '_handle_event_%s' % (event.action,)
            getattr(self, methodname)(event)

    def unassigned(self):
        """Return an iterator that yields unassigned instances.
        """
        return (inst for inst in self._store.itervalues()
                if inst.state == 'pending-assignment' or inst.state == None)

    def undispatched(self):
        return (inst for inst in self._store.itervalues()
                if inst.state == 'pending-dispatch')

    def running(self):
        return (inst for inst in self._store.itervalues()
                if inst.state == 'running')

    def _create(self, value):
        inst = Instance(self.store_command, **value)
        self._store[(inst.formation, inst.name)] = inst
        self.emit('create', inst)
        return inst

    def _update(self, instance, values):
        """Update the given instance with new values."""
        instance._update(values)
        self.emit('update', instance)

    def _delete(self, instance):
        """Delete the given instance."""
        del self._store[(instance.formation, instance.name)]
        self.emit('delete', instance)



