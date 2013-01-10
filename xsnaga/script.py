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

from docopt import docopt

"""Orchestrator for Gilliam, a 12 factor application deployment system.

Usage:
  gilliam-orchestrator [options]

Options:
  -h --help                show this help message and quit
  --version                show version and exit
  -p, --port PORT          listen on PORT for API requests [default: 5000]

"""

def main():
    """."""
    options = docopt(__doc__, version='0.0')
    
