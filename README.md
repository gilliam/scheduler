# The Gilliam Orchestrator

Gilliam is a platform for deploying your [12 factor
apps](http://12factor.net/), and this is the orchestrator.

The orchestrator is pretty much the heart of the Gilliam platform.  It
is responsible for making sure that your instances are running.  It is
also the one deciding *where* they should be running.

Right now it also provides the API that the client tool `gilliam`
uses, but that may very well change in the future.

# Install

It has only been tested on Ubuntu 12.04 with sqlite3.  You need to
install the python bindings and the client tools for sqlite3.

It is recommended that you install in a virtual environment
(`virtualenv`) rather than risking your systems python installation:

    $ git clone git@github.com:gilliam/orchestrator.git
    $ cd orchestrator
    $ virtualenv .
    $ ./bin/pip install -r requirements.txt

Initialize database:

    $ sqlite3 -init schema.sql gilliam.db .quit
    -- Loading resources from schema.sql

# Running

Start the application using `honcho`:

    $ . ./bin/activate
    $ honcho start -p 8000

If you need to change any settings look at the `.env` file.


