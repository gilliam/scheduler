# Bootstrap

1. run a one-off container with image "_worker" and argument "--bootstrap".
 since it is running by an executor it will have access to a proxy.

 FIXME: create a bootstrap script that knows how to talk to a executor?

2. create a "_store" container.

3. write formation to that _store container (including the just created
instance).  one api instance, two worker instances, one store instance.

4. take the worker lock.

5. start one of the scheduler-worker containers manually.  it will
 hang waiting for the lock.

5. stop the bootstrap script, unlocking the worker lock.

6. the new scheduler-worker (5) will take the lock and start acting
 as a normal worker, spinning up the of the instances.


# Leader Election

Only one instance can do scheduling at the same time.  But for
reliability we of course want multiple instances running at the same
time.

Leader election and coordination is done through `etcd`.  There's a
`/leader` key that should hold the instance name of the instance that
is currently leader.

## Implementation.

The election mechanism relies on the `testAndSet` and TTL expire
mechanisms of `etcd`.

Each candidate constantly (every `N` seconds) tries to write its name
to `/leader` with an empty `prevValue` and a TTL set to `N*2` seconds.
This will cause writes to fail if there already is a key with that
name.  If the write succeeds, the now elected leader should continue
to update the key, but now with a `prevValue` set to its name.  This
will refresh the key, making sure that it is not automatically
expired.

# Storage Layout

Data is stored in a `etcd` instance, that is private to the scheduler
formation.

Desired state is stored under
`/formation/<form_name>/<service>/<instance>` like this:

    /formation/scheduler/api/api.ma9FYRLZwxYZbCqMQwvJWU -> { ... }

The leader has a watch on `/formation` and gets notified when changes
are made to the desired state.

    /_scheduler/formation/api/api....../assign ->


      
 

