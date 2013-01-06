# Copyright (c) 2013 Johan Rydberg.

from storm.locals import Int, Unicode, Reference, ReferenceSet, JSON


class Deploy(object):
    """Representation of a deployment."""
    __storm_table__ = 'deploy'

    id = Int(primary=True)
    app_id = Int()
    build = Unicode()
    image = Unicode()
    pstable = JSON()
    config = JSON()
    text = Unicode()


class App(object):
    """

    @ivar deploy: The current deploy.  May be C{None} if there has not
        been a deploy yet for this application.
    """
    __storm_table__ = 'app'

    id = Int(primary=True)
    name = Unicode()
    deploy_id = Int()
    deploy = Reference(deploy_id, Deploy.id)
    deploys = ReferenceSet(id, Deploy.app_id)
    scale = JSON()
    repository = Unicode()
    text = Unicode()


class Proc(object):
    """

    @ivar state: Current known state of the process.  One of the
        following values: C{init}, C{boot}, C{run}, C{abort} or
        C{exit}.  The process starts out in C{init} when the spawn
        request is sent to the supervisor. From there it goes to
        C{run} via C{boot}.  
    """
    __storm_table__ = 'proc'

    id = Int(primary=True)
    app_id = Int()
    app = Reference(app_id, App.id)
    proc_id = Unicode()
    name = Unicode()
    state = Unicode()
    deploy = Int()
    host = Unicode()
    port = Int()
    hypervisor_id = Int()
    hypervisor = Reference(hypervisor_id, 'Hypervisor.id')

    def __init__(self, app, name, deploy_id, proc_id, hypervisor):
        self.app = app
        self.name = name
        self.deploy = deploy_id
        self.proc_id = proc_id
        self.hypervisor = hypervisor
        self.state = 'init'


class Hypervisor(object):
    """."""
    __storm_table__ = 'hypervisor'

    id = Int(primary=True)
    host = Unicode()
    procs = ReferenceSet(Hypervisor.id, Proc.hypervisor_id)
