"""
Number job changes inside their transaction; publish them after commit.

Every status change goes through ``transition``, ``release_children``
or ``mark_descendants``, and each of them calls ``record_changes``.
The notes wait on the session until ``commit_and_publish``:

1. number them: each run's counter goes up by its number of changes,
   in the same transaction, so number order is commit order;
2. commit;
3. publish.

Two guards keep the notes honest. A rollback drops them, so nothing
that was undone is ever announced. A plain ``commit()`` with notes
still waiting raises, so no code path can change a job without
numbering the change: an unnumbered change would be invisible even to
the stream's ping.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import NamedTuple

from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from app.events.bus import EventBus
from app.events.models import JobEvent, state_fields
from app.models.job import Job
from app.models.run import Run
from app.runs.bundles import close_run_if_finished
from app.runs.states import JobStatus

CHANGES_KEY = "atomfield.job_changes"


class UnpublishedChangesError(RuntimeError):
    """
    A transaction that changed jobs was committed with a plain
    ``commit()``; use ``commit_and_publish``.
    """


class JobChange(NamedTuple):
    """
    A job's state right after a change. Copied out of the ORM object so
    it stays valid after commit.
    """

    run_id: uuid.UUID
    job_id: uuid.UUID
    status: JobStatus
    attempt: int
    error_message: str | None
    started: bool


def record_changes(session: AsyncSession, jobs: Iterable[Job]) -> None:
    """
    Note jobs whose status just changed in this transaction.

    A later change to the same job replaces the earlier note: only the
    state at commit is ever visible to anyone.

    :param session: Session holding the transaction.
    :type session: AsyncSession
    :param jobs: Jobs as returned by the UPDATE that changed them.
    :type jobs: Iterable[Job]
    """
    pending = session.info.setdefault(CHANGES_KEY, {})
    for job in jobs:
        pending[job.id] = JobChange(run_id=job.run_id, **state_fields(job))


def take_changes(session: AsyncSession) -> list[JobChange]:
    """
    Remove and return the changes noted in this transaction.

    :param session: Session holding the transaction.
    :type session: AsyncSession
    :return: Changes in the order they were first noted.
    :rtype: list[JobChange]
    """
    return list(session.info.pop(CHANGES_KEY, {}).values())


async def number_run_changes(
    session: AsyncSession,
    run_id: uuid.UUID,
    changes: Sequence[JobChange],
) -> list[JobEvent]:
    """
    Advance one run's counter and give each change the next number.

    The UPDATE locks the run's row until commit, so two transactions
    changing the same run take turns and their numbers never overlap.

    :param session: Session holding the transaction.
    :type session: AsyncSession
    :param run_id: Run whose jobs changed.
    :type run_id: uuid.UUID
    :param changes: That run's changes.
    :type changes: Sequence[JobChange]
    :return: One numbered event per change.
    :rtype: list[JobEvent]
    """
    statement = (
        update(Run)
        .where(Run.id == run_id)
        .values(event_seq=Run.event_seq + len(changes))
        .returning(Run.event_seq)
        .execution_options(synchronize_session=False)
    )
    last = (await session.execute(statement)).scalar_one()
    first = last - len(changes) + 1
    return [
        JobEvent(seq=first + offset, **change._asdict())
        for offset, change in enumerate(changes)
    ]


async def number_changes(
    session: AsyncSession,
    changes: Sequence[JobChange],
) -> list[JobEvent]:
    """
    Number changes run by run, and close each run whose jobs are now
    all final.

    :param session: Session holding the transaction.
    :type session: AsyncSession
    :param changes: Changes noted in this transaction.
    :type changes: Sequence[JobChange]
    :return: Numbered events.
    :rtype: list[JobEvent]
    """
    by_run: defaultdict[uuid.UUID, list[JobChange]] = defaultdict(list)
    for change in changes:
        by_run[change.run_id].append(change)
    events = []
    # Every transaction locks runs in the same (id) order, so two of
    # them can never each hold a run the other is waiting for.
    for run_id in sorted(by_run):
        events += await number_run_changes(session, run_id, by_run[run_id])
        # The run's row is locked now: checking here, never earlier,
        # is what lets the last finished job close the run.
        await close_run_if_finished(session, run_id)
    return events


async def commit_and_publish(
    session: AsyncSession,
    bus: EventBus,
) -> list[JobEvent]:
    """
    Number this transaction's job changes, commit, then publish them.

    Publishing comes after commit: a watcher must never be told about
    a change that could still be rolled back.

    :param session: Session holding the transaction.
    :type session: AsyncSession
    :param bus: Where the events go.
    :type bus: EventBus
    :return: The published events.
    :rtype: list[JobEvent]
    """
    events = await number_changes(session, take_changes(session))
    await session.commit()
    await bus.publish(events)
    return events


@event.listens_for(Session, "after_soft_rollback")
def drop_changes_on_rollback(
    session: Session,
    previous_transaction: SessionTransaction,
) -> None:
    """
    Forget the notes of a transaction that was rolled back.

    :param session: The (synchronous) session behind an AsyncSession.
    :type session: Session
    :param previous_transaction: The transaction that ended.
    :type previous_transaction: SessionTransaction
    """
    session.info.pop(CHANGES_KEY, None)


@event.listens_for(Session, "before_commit")
def refuse_unnumbered_changes(session: Session) -> None:
    """
    Stop a commit that would save job changes without numbering them.

    :param session: The (synchronous) session behind an AsyncSession.
    :type session: Session
    :raises UnpublishedChangesError: If changes are still waiting.
    """
    if session.info.get(CHANGES_KEY):
        raise UnpublishedChangesError(
            "Job changes must be committed with commit_and_publish"
        )
