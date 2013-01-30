# The Gilliam Orchestrator

(aka Snaga)

The Orchestrator is pretty much the heart of Gilliam app platform.  It
is responsible for making sure that your instances are running.  It is
also the one deciding *where* they should be running.

Right now it also provides the API that the client tool `gilliam`
uses, but that may very well change in the future.

# Introduction to Gilliam

In short, Gilliam is a platform for hosting your [12 factor
apps](http://12factor.net/).  This philosphy of having a simple
environment where you run your hopefully stateless and horizontaly
scalable apps were spearheaded by [Heroku](http://heroku.com).

Gilliam is in no way trying to compete with Heroku.  Our usecase is
somewhat different. First, Gilliam will not provide any kind of
multitenant environment. It is assumed that all app are owned and
operated by the same person or organisation.  Secondly, since we not
really care about information leakage between instances we just run
them in a simple chroot jail (this may change in the future though).
Third, app hosted in Gilliam isn't really intended to be exposed to
the internet.  Instead the idea is that you use Gilliam to run your
stack of micro backend services.

Some of the goals of Gilliam are:
* easy to deploy services
* easy to scale services up and down
* the components of the system are decoupled

Non-goals:
* HTTP routing
* Multitenant

Some problems that have not been addressed yet:
* Logging
* Metrics and statistics
* CPU and memory limitations
