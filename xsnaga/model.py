from collections import namedtuple


class App(namedtuple('App', ['name', 'deploy', 'scale'])):
    pass


class Deploy(namedtuple('Deploy', ['id', 'build', 'image', 'pstable',
                                   'config'])):
    pass


class Proc(namedtuple('Proc', ['app', 'deploy', 'name', 'state',
                               'host'])):
    pass
