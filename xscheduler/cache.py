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

import logging
import json
import sys
from functools import partial

from gilliam.errors import ResolveError

from redis.connection import Connection as _Connection, ConnectionPool
from redis import StrictRedis, RedisError


log = logging.getLogger(__name__)


class RedisConnection(_Connection):
    """A redis connection that knows how to resolve addresses."""

    def __init__(self, resolver, host='localhost', port=6379, **kwargs):
        host, port = resolver.resolve_host_port(host, port)
        _Connection.__init__(self, host=host, port=port, **kwargs)


class StateCache(object):
    TTL = 24 * 60 * 60

    def __init__(self, redis):
        self.redis = redis

    def save(self, formation, service, instance, data):
        """Save state for the specified service instance."""
        try:
            sdata = json.dumps(data)
            data_key = '{0}:{1}:{2}'.format(formation, service, instance)
            self.redis.set(data_key, sdata, ex=self.TTL)
            topic = 'formation:{0}'.format(formation)
            self.redis.publish(topic, sdata)
        except RedisError:
            log.debug('cannot talk to redis', exc_info=True)
        except ResolveError:
            pass
        except:
            log.exception("redis")

    def get(self, formation, service, instance):
        try:
            data_key = '{0}:{1}:{2}'.format(formation, service, instance)
            data = self.redis.get(data_key)
            if data:
                return json.loads(data)
            else:
                return {}
        except RedisError:
            log.debug('cannot talk to redis', exc_info=True)
            return {}
        except ResolveError:
            return {}


def make_client(resolver, host, port=6379):
    """Make a state cache client."""
    redis = StrictRedis(connection_pool=ConnectionPool(
        host=host, port=port, connection_class=partial(RedisConnection, resolver)))
    return StateCache(redis)
