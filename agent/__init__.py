"""
The AtomField agent: a small daemon that runs jobs on the machine it
lives on. It only ever calls out to the API (claim, heartbeat,
complete), so it works behind firewalls and needs no open port.

Run it with ``python -m agent``; settings come from the environment
(see ``agent.config``).
"""
