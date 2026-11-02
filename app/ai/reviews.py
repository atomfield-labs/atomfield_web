"""
One click of an AI button. Starting a review records it and answers at
once; the rest runs after the answer has gone, because a call of a minute
or more would not survive a tunnel. No database connection is held while
the vendor thinks.

Nothing here touches a run: a review only reads, and suggests.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.evidence import Evidence, EvidenceCollector, ReviewKind
from app.ai.prompts import (
    AiAnswer,
    build_question,
    render_evidence,
    setting_values,
)
from app.ai.suggestions import CheckedSuggestion, check_suggestions
from app.ai.vault import KeyUnreadableError, KeyVault
from app.ai.vendors import (
    AiVendor,
    LlmClient,
    LlmError,
    LlmReply,
    Question,
)
from app.catalog.catalog import Catalog, UnknownTaskError
from app.catalog.models import TaskDefinition
from app.models.ai import AiKey, AiReview, ReviewStatus
from app.models.job import Job, JobDependency
from app.models.run import Run
from app.releases.catalogs import ReleaseCatalogs
from app.runs.states import JobStatus
from app.storage.keys import ai_sent_key
from app.storage.store import ArtifactStore

logger = logging.getLogger(__name__)
ENCODING = "utf-8"
# Every wait has a bound, and a review past this one was lost with its
# server, since a call can't outlast the limit below.
CALL_LIMIT_SECONDS = 300.0
STALE_AFTER = timedelta(minutes=10)
ONE_RUNNING = text("status = 'running'")

KIND_OF_ENDING = {
    JobStatus.FAILED: ReviewKind.FIX,
    JobStatus.SUCCEEDED: ReviewKind.ANALYSIS,
}
NOTHING_TO_READ = "This step left nothing to read, so nothing was sent."
TOO_SLOW = "The vendor took too long to answer. Try again."
UNREADABLE = "The answer came back in a form that can't be read. Ask again."
INTERRUPTED = "This was interrupted before it finished. Ask again."
KEY_GONE = "Your AI key was removed before this could start. Add it again."
SECRET_CHANGED = (
    "This server's secret has changed since you saved your key. Add it again."
)
TASK_GONE = "This step's task is no longer in the catalog, so it can't be read."
SOMETHING_WRONG = "Something went wrong on this server. Try again."


def kind_for(job: Job) -> ReviewKind | None:
    """
    What a review of this job would do, which its ending decides. A step
    that was cancelled, or never ran, has nothing to review.

    :param job: The job.
    :type job: Job
    :return: The kind, or None if it can't be reviewed.
    :rtype: ReviewKind | None
    """
    return KIND_OF_ENDING.get(JobStatus(job.status))


def is_stale(review: AiReview, now: datetime | None = None) -> bool:
    """
    Whether a running review was lost with its server.

    :param review: The review.
    :type review: AiReview
    :param now: The time now; tests set it.
    :type now: datetime | None
    :return: True if it has been running too long to still be alive.
    :rtype: bool
    """
    moment = now or datetime.now(UTC)
    running = review.status == ReviewStatus.RUNNING
    return running and moment - review.created_at > STALE_AFTER


async def clear_stale(db: AsyncSession, job_id: uuid.UUID) -> None:
    """
    Mark a job's lost review as failed, so a new one can start.

    :param db: Asynchronous database session; the caller commits.
    :type db: AsyncSession
    :param job_id: The job.
    :type job_id: uuid.UUID
    """
    oldest_alive = datetime.now(UTC) - STALE_AFTER
    await db.execute(
        update(AiReview)
        .where(
            AiReview.job_id == job_id,
            AiReview.status == ReviewStatus.RUNNING,
            AiReview.created_at < oldest_alive,
        )
        .values(
            status=ReviewStatus.FAILED,
            error=INTERRUPTED,
            finished_at=func.now(),
        )
    )


def new_review_statement(job: Job, kind: ReviewKind, key: AiKey) -> Any:
    """
    Add a running review, unless the job already has one: the unique index
    decides, so two clicks at once can't both start one.

    :param job: The job.
    :type job: Job
    :param kind: What the review will do.
    :type kind: ReviewKind
    :param key: The key that pays, with its vendor and model.
    :type key: AiKey
    :return: The statement; it returns the new id, or nothing.
    :rtype: Any
    """
    return (
        insert(AiReview)
        .values(
            job_id=job.id,
            requested_by=key.user_id,
            kind=kind.value,
            status=ReviewStatus.RUNNING,
            vendor=key.vendor,
            model=key.model,
        )
        .on_conflict_do_nothing(
            index_elements=[AiReview.job_id], index_where=ONE_RUNNING
        )
        .returning(AiReview.id)
    )


async def start_review(
    db: AsyncSession, job: Job, kind: ReviewKind, key: AiKey
) -> tuple[AiReview, bool]:
    """
    Record a new review, unless one is already running for this job.

    :param db: Asynchronous database session; committed here.
    :type db: AsyncSession
    :param job: The job.
    :type job: Job
    :param kind: What the review will do.
    :type kind: ReviewKind
    :param key: The key that pays, with its vendor and model.
    :type key: AiKey
    :return: The review, and whether it is new.
    :rtype: tuple[AiReview, bool]
    """
    await clear_stale(db, job.id)
    statement = new_review_statement(job, kind, key)
    new_id = (await db.execute(statement)).scalar_one_or_none()
    await db.commit()
    return await latest_review(db, job.id), new_id is not None


async def latest_review(db: AsyncSession, job_id: uuid.UUID) -> AiReview | None:
    """
    A job's newest review.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param job_id: The job.
    :type job_id: uuid.UUID
    :return: The review, if there is one.
    :rtype: AiReview | None
    """
    query = (
        select(AiReview)
        .where(AiReview.job_id == job_id)
        .order_by(AiReview.created_at.desc())
        .limit(1)
    )
    return (await db.execute(query)).scalar_one_or_none()


def read_answer(reply: LlmReply) -> AiAnswer:
    """
    Read a model's reply, which should fit the shape it was told to use.

    :param reply: The reply.
    :type reply: LlmReply
    :return: The answer.
    :rtype: AiAnswer
    :raises LlmError: If it doesn't.
    """
    try:
        return AiAnswer.model_validate_json(reply.text)
    except ValidationError:
        raise LlmError(UNREADABLE) from None


def task_of(catalog: Catalog, job: Job) -> TaskDefinition:
    """
    A job's task, from its run's own catalog.

    :param catalog: The catalog of the run's release.
    :type catalog: Catalog
    :param job: The job.
    :type job: Job
    :return: The task.
    :rtype: TaskDefinition
    :raises LlmError: If that catalog no longer holds it.
    """
    try:
        return catalog.get(job.script_name)
    except UnknownTaskError:
        raise LlmError(TASK_GONE) from None


def finished_fields(
    evidence: Evidence,
    reply: LlmReply,
    answer: AiAnswer,
    checked: Sequence[CheckedSuggestion],
) -> dict[str, Any]:
    """
    What to store about a finished review.

    :param evidence: What the model read.
    :type evidence: Evidence
    :param reply: Its reply.
    :type reply: LlmReply
    :param answer: The reply, read.
    :type answer: AiAnswer
    :param checked: Its suggestions, checked.
    :type checked: Sequence[CheckedSuggestion]
    :return: Column values.
    :rtype: dict[str, Any]
    """
    return {
        **evidence.record(),
        "status": ReviewStatus.DONE,
        "answered_by": reply.model,
        "summary": answer.summary,
        "explanation": answer.explanation,
        "suggestions": [item.model_dump() for item in checked],
        "check_next": answer.check_next,
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
    }


@dataclass(frozen=True, slots=True)
class ReviewContext:
    """
    What a review needs from the database, read once.

    :param review: The review.
    :type review: AiReview
    :param job: Its job.
    :type job: Job
    :param run_id: The job's run.
    :type run_id: uuid.UUID
    :param task: The job's task, from its run's own release.
    :type task: TaskDefinition
    :param catalog: That release's catalog.
    :type catalog: Catalog
    :param parents: The jobs before this one.
    :type parents: list[Job]
    :param key: The key that pays.
    :type key: AiKey
    """

    review: AiReview
    job: Job
    run_id: uuid.UUID
    task: TaskDefinition
    catalog: Catalog
    parents: list[Job]
    key: AiKey


class ReviewRunner:
    """
    Runs one review from start to finish, and records how it ended.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        catalogs: ReleaseCatalogs,
        collector: EvidenceCollector,
        store: ArtifactStore,
        vault: KeyVault,
        make_client: Callable[[AiVendor, str], LlmClient],
    ) -> None:
        """
        :param session_factory: Creates short-lived sessions.
        :type session_factory: async_sessionmaker
        :param catalogs: Catalogs per release.
        :type catalogs: ReleaseCatalogs
        :param collector: Gathers what a step left.
        :type collector: EvidenceCollector
        :param store: Keeps the text that was sent.
        :type store: ArtifactStore
        :param vault: Reads the person's key.
        :type vault: KeyVault
        :param make_client: Makes a vendor's client from a key.
        :type make_client: Callable[[AiVendor, str], LlmClient]
        """
        self.session_factory = session_factory
        self.catalogs = catalogs
        self.collector = collector
        self.store = store
        self.vault = vault
        self.make_client = make_client

    async def load(self, review_id: uuid.UUID) -> ReviewContext | None:
        """
        Read what a review needs, then let the connection go.

        :param review_id: The review.
        :type review_id: uuid.UUID
        :return: The context; None if the run was deleted meanwhile.
        :rtype: ReviewContext | None
        :raises LlmError: If the key or the task has gone.
        """
        async with self.session_factory() as db:
            review = await db.get(AiReview, review_id)
            if review is None:
                return None
            job = await db.get(Job, review.job_id)
            run = await db.get(Run, job.run_id)
            payer = review.requested_by
            key = await db.get(AiKey, payer) if payer else None
            catalog = await self.catalogs.of_release(db, run.release_id)
            parents = await self.parents_of(db, job)
        if key is None:
            raise LlmError(KEY_GONE)
        task = task_of(catalog, job)
        return ReviewContext(review, job, run.id, task, catalog, parents, key)

    @staticmethod
    async def parents_of(db: AsyncSession, job: Job) -> list[Job]:
        """
        The jobs a job follows.

        :param db: Asynchronous database session.
        :type db: AsyncSession
        :param job: The job.
        :type job: Job
        :return: Its parents.
        :rtype: list[Job]
        """
        query = (
            select(Job)
            .join(JobDependency, JobDependency.upstream_id == Job.id)
            .where(JobDependency.downstream_id == job.id)
            .order_by(Job.node_key)
        )
        return list((await db.execute(query)).scalars())

    async def ask_model(
        self, context: ReviewContext, question: Question
    ) -> LlmReply:
        """
        Make the one call a click pays for.

        :param context: The review's context.
        :type context: ReviewContext
        :param question: What the model is asked.
        :type question: Question
        :return: Its reply.
        :rtype: LlmReply
        :raises LlmError: If the call fails or the key can't be read.
        """
        try:
            secret = self.vault.reveal(context.key.sealed_key)
        except KeyUnreadableError:
            raise LlmError(SECRET_CHANGED) from None
        vendor = AiVendor(context.review.vendor)
        async with self.make_client(vendor, secret) as llm:
            return await llm.ask(question)

    async def keep_sent_text(
        self, context: ReviewContext, question: Question
    ) -> None:
        """
        Keep the exact text the model gets, its instructions included, for
        "See what was sent".

        :param context: The review's context.
        :type context: ReviewContext
        :param question: What the model is asked.
        :type question: Question
        """
        key = ai_sent_key(context.run_id, context.review.id)
        text = f"{question.system}\n{question.user}"
        await self.store.write(key, text.encode(ENCODING))

    async def gather(self, context: ReviewContext) -> Evidence:
        """
        Gather what the step left.

        :param context: The review's context.
        :type context: ReviewContext
        :return: The evidence.
        :rtype: Evidence
        :raises LlmError: If there is nothing to read, so nothing is paid.
        """
        evidence = await self.collector.collect(
            context.job,
            context.task,
            context.catalog.pages_for(context.task.id),
            context.parents,
            ReviewKind(context.review.kind),
        )
        if not evidence.parts and not context.job.error_message:
            raise LlmError(NOTHING_TO_READ)
        return evidence

    async def produce(self, context: ReviewContext) -> dict[str, Any]:
        """
        Gather, ask, and check.

        :param context: The review's context.
        :type context: ReviewContext
        :return: Column values for the finished review.
        :rtype: dict[str, Any]
        :raises LlmError: If anything prevents an answer.
        """
        evidence = await self.gather(context)
        job, task = context.job, context.task
        kind = ReviewKind(context.review.kind)
        sent_text = render_evidence(job, task, evidence)
        question = build_question(kind, context.review.model, sent_text)
        await self.keep_sent_text(context, question)
        answer_reply = await self.ask_model(context, question)
        answer = read_answer(answer_reply)
        values = setting_values(job, task)
        checked = check_suggestions(
            answer.suggestions, context.catalog, task.id, values
        )
        return finished_fields(evidence, answer_reply, answer, checked)

    async def record(
        self, review_id: uuid.UUID, fields: dict[str, Any]
    ) -> None:
        """
        Record how a review ended. Only a running review changes, so a
        late answer can't overwrite one already marked as lost.

        :param review_id: The review.
        :type review_id: uuid.UUID
        :param fields: Column values.
        :type fields: dict[str, Any]
        """
        statement = (
            update(AiReview)
            .where(
                AiReview.id == review_id,
                AiReview.status == ReviewStatus.RUNNING,
            )
            .values(finished_at=func.now(), **fields)
        )
        async with self.session_factory() as db:
            await db.execute(statement)
            await db.commit()

    async def outcome(self, review_id: uuid.UUID) -> dict[str, Any] | None:
        """
        Run a review, turning what can go wrong into a plain message.

        :param review_id: The review.
        :type review_id: uuid.UUID
        :return: Column values, or None if its run was deleted meanwhile.
        :rtype: dict[str, Any] | None
        """
        try:
            async with asyncio.timeout(CALL_LIMIT_SECONDS):
                context = await self.load(review_id)
                if context is None:
                    return None
                return await self.produce(context)
        except LlmError as error:
            message = str(error)
        except TimeoutError:
            message = TOO_SLOW
        return {"status": ReviewStatus.FAILED, "error": message}

    async def run(self, review_id: uuid.UUID) -> None:
        """
        Run a review to its end. This is the outermost boundary: anything
        unexpected is recorded, so the tab doesn't spin forever, and raised
        again, so it reaches the server's log.

        :param review_id: The review.
        :type review_id: uuid.UUID
        """
        try:
            fields = await self.outcome(review_id)
        except Exception:
            logger.warning("AI review %s failed unexpectedly", review_id)
            failed = {"status": ReviewStatus.FAILED, "error": SOMETHING_WRONG}
            await self.record(review_id, failed)
            raise
        if fields is not None:
            await self.record(review_id, fields)
