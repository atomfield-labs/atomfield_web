"""
The task contract between the platform and domain packs.

A domain pack (afscripts today) ships one ``catalog.json``. The platform
reads only that file: it never imports a pack's code, so any pack that
writes the same format can be plugged in.
"""
