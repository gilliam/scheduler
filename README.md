# Snaga - the orchestrator #

Snaga is the heart of Gilliam.  It is responsible making sure
processes are running, and where they are running.  Right now it also
provides the external API that the client tool `gilliam` is using, but
that will hopefully change in the future.

There's a special command-line tool, `sharku`, to control Snaga.  Use
that to manage supervisors.

# Installation



# Administration


# Design Overview

First of all, Snaga is not horizontally scalabe nor has it any
redundancy.  This is bad, but not required for a MVP or a prototype.

For each supervisor there's a piece of logic that is responsible for
the communication.  This logic lives in `xsnaga/supervisor.py`.  This
code is responsible for managing processes on the supervisor and will
also monitor process state and status.  

There's a orchestrator per application.  

## Doing a Deploy

