# The Gilliam Orchestrator

This is the scheduler and API component of Gilliam, a platform for 12
factor applications.

The scheduler is heart of the platform. It is responsible for making
sure that your instances are running.  It is also the one deciding
*where* they should be running.

Right now it also provides the API that the client tool `gilliam`
uses, but that may very well change in the future.

# Install

It has only been tested on Ubuntu 12.04 with sqlite3.  You need to
install the python bindings and the client tools for sqlite3.

It is recommended that you install in a virtual environment
(`virtualenv`) rather than risking your systems python installation:

    virtualenv .
    ./bin/pip install -r requirements.txt

Initialize database:

    sqlite3 -init schema.sql gilliam.db .quit
    -- Loading resources from schema.sql

# Run

Start the application using `honcho`:

    . ./bin/activate
    honcho start -p 8000

If you need to change any settings look at the `.env` file.
