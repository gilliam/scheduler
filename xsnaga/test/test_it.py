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

"""Integration tests.

These are the slow tests that (hopefully) verifies that all parts of
the scheduler integrates well together.
"""

from gevent import monkey, subprocess, pywsgi
import gevent
monkey.patch_all(thread=False, time=False)

from webob.dec import wsgify
from webob import Response
from routes import Mapper, URLGenerator
from urlparse import urljoin

import unittest
import os.path
import requests
import json
import tempfile
from pyee import EventEmitter
from glock.clock import MockClock

from xsnaga.test import mocks
from xsnaga import script


class AbstractIntTestCase(unittest.TestCase):
    """Base class for integration tests."""
    
    SCHEMA = os.path.join(os.path.dirname(__file__), '../../schema.sql')

    def create_database(self):
        """Create a simple sqlite database."""
        filename = tempfile.mktemp()
        popen = subprocess.Popen(["sqlite3", "-init", self.SCHEMA,
                                  filename, '.quit'],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
        popen.communicate()
        self.assertEquals(popen.returncode, 2)
        self.addCleanup(os.remove, filename)
        return filename

    def create_hypervisor(self, port=5001):
        """Create a mock hypervisor and register it with the
        scheduler.
        """
        hv = mocks.MockHypervisor(self.clock, port)
        hv.start()
        request = {'host': 'localhost', 'port': port, 'capacity': 1,
                   'options': {}}
        response = self.http.post(os.path.join(self._url, 'hypervisor'),
                                  data=json.dumps(request))
        response.raise_for_status()
        return hv

    def _create_app(self):
        """Helper function for creating an app."""
        request = {'name': 'test'}
        return self.http.post(os.path.join(self._url, 'app'),
                              data=json.dumps(request))

    def _create_release(self, text, build, image, pstable, config):
        """Create a release."""
        request = {'text': text, 'build': build, 'image': image,
                   'pstable': pstable, 'config': config}
        response =  self.http.post(os.path.join(self._url, 'app',
                                                'test', 'release'),
                                   data=json.dumps(request))
        self.assertEquals(response.status_code, 201)
        return response.json()

    def set_scale_for_release(self, release, scale):
        response = self.http.put(urljoin(self._url, release['links']['scale']),
                                 data=json.dumps(scale))
        self.assertEquals(response.status_code, 204)

    def iterprocs(self):
        """Iterate through all procs."""
        url = '/app/test/proc'
        while url is not None:
            response = self.http.get(urljoin(self._url, url)).json()
            for item in response['items']:
                yield item
            url = response['links'].get('next')

    def get_proc(self, name):
        proc_map = dict([(proc['name'], proc) for proc in self.iterprocs()])
        return proc_map.get(name)

    def create_and_scale_release(self, **scales):
        pstable = dict([(k, 'cmd') for k in scales])
        release = self._create_release('test', 'build', 'image',
                                       pstable, {})
        self.set_scale_for_release(release, scales)
        self.advance(10)
        return release

    def advance(self, time, actual_time=1):
        self.clock.advance(time)
        gevent.sleep(actual_time)

    def setUp(self):
        self.options = {
            'DATABASE': 'sqlite:' + self.create_database(),
            'SLOW_BOOT_THRESHOLD': 60,
            'SLOW_TERM_THRESHOLD': 20,
            'PORT': '5000'
            }
        self.clock = MockClock()
        self.eventbus = EventEmitter()
        self._server = script.main(self.clock, self.eventbus, self.options)
        self._server.start()
        self._url = 'http://localhost:%s/' % (self.options['PORT'],)
        self.http = requests

    def tearDown(self):
        self._server.stop()


class HypervisorTestCase(AbstractIntTestCase):
    """Integration tests that are more targeted against the
    interaction between scheduler and hypervisor.
    """

    def setUp(self):
        AbstractIntTestCase.setUp(self)
        self.hv = self.create_hypervisor()

    def tearDown(self):
        self.hv.stop()
        AbstractIntTestCase.tearDown(self)

    def test_deletes_unknown_procs(self):
        """Verify that the scheduler removes proc's that should not be
        there.
        """
        self.hv.add(mocks.Proc('proc1', 'app', 'name', 'image', 'cmd',
                               {}))
        self.advance(30)
        self.assertIn(('DELETE', '/proc/proc1'), self.hv.requests)


class IntTestCase(AbstractIntTestCase):
    """Simple integration tests."""

    def setUp(self):
        AbstractIntTestCase.setUp(self)
        self.machine = self.create_hypervisor()
        self._create_app()

    def tearDown(self):
        self.machine.stop()
        AbstractIntTestCase.tearDown(self)

    def test_creates_procs_according_to_scale_factors(self):
        """Verify that procs are created according to the scale
        factor.
        """
        self.create_and_scale_release(web=3, api=5)
        self.assertEquals(len(self.machine.registry), 8)

    def test_slowly_booting_procs_are_expired(self):
        """Verify that procs that do not boot as quickly as we like
        are terminated.
        """
        self.create_and_scale_release(web=1)
        self.machine.registry['proc-0'].set_state('boot')
        self.advance(self.options['SLOW_BOOT_THRESHOLD'] * 2)
        self.assertIn(('DELETE', '/proc/proc-0'), self.machine.requests)

    def test_slowly_terminating_procs_are_expired(self):
        """Verify that procs that do not die as quikcly as we like
        are expired.
        """
        release = self.create_and_scale_release(web=1)
        self.machine.registry['proc-0'].set_state('running')
        self.set_scale_for_release(release, {'web': 0})
        self.advance(10)
        self.assertIn(('DELETE', '/proc/proc-0'), self.machine.requests)
        self.advance(self.options['SLOW_TERM_THRESHOLD'] + 10)
        self.assertEquals(len(list(self.iterprocs())), 0)

    def test_updates_proc_state_when_synchronizing_state(self):
        """Verify that the scheduler synchronizes proc state between
        hypeervisor and its internal state when it checks what procs
        the hypervisor has.
        """
        self.create_and_scale_release(web=1)
        self.machine.registry['proc-0'].state = 'running'
        self.advance(40)
        procs = list(self.iterprocs())
        self.assertEquals(len(procs), 1)
        self.assertEquals(procs[0]['state'], 'running')

    def test_updates_proc_state_on_callback(self):
        """Verify that a proc's state is updated when the state change
        callback is called.
        """
        self.create_and_scale_release(web=1)
        self.machine.registry['proc-0'].set_state('running')
        self.advance(1)
        procs = list(self.iterprocs())
        self.assertEquals(len(procs), 1)
        self.assertEquals(procs[0]['state'], 'running')

    def test_scale_down_terminates_procs(self):
        """Verify that procs are terminated when the scheduler is
        instructed to scale down a release.
        """
        release = self.create_and_scale_release(web=1)
        procs = list(self.iterprocs())
        self.assertEquals(len(procs), 1)
        self.set_scale_for_release(release, {'web': 0})
        self.advance(40)
        procs = list(self.iterprocs())
        self.assertEquals(len(procs), 0)
        self.assertIn(('DELETE', '/proc/proc-0'), self.machine.requests)

