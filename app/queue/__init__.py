"""
Delivery of queued jobs to agents. Postgres stays the record; this is
only the messenger, and the sweeper refills it if anything is lost.
"""
