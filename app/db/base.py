"""
app/db/base.py — Declarative Base Registry

📚 LESSON: Why a dedicated base.py?

    SQLAlchemy's `Base = declarative_base()` is the registry that knows
    about ALL your ORM models. When you call `Base.metadata.create_all(engine)`,
    it iterates this registry to know which tables to create.

    The critical rule: every model must import from THIS base.
    If two modules define their own Base, they have separate registries —
    create_all() on one won't create the other's tables. Subtle, nasty bug.

    Keeping Base in its own tiny module breaks circular import chains:
        models.py → imports Base → imports session.py → imports engine
        vs
        models.py → imports base.py (no engine, no session)
        session.py → imports base.py (no models)
        main.py → imports both freely
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
