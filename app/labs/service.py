"""
What can be done with a lab: making one, giving it workflows, and
adding, ticking and removing its people. Who may ask for each is the
routes' business (``app.api.routes.labs``). Nothing here commits: a
request's changes stand or fall together.
"""

import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import conflict, not_found, unprocessable
from app.catalog.catalog import Catalog
from app.models.api_key import ApiKey
from app.models.browser_session import BrowserSession
from app.models.lab import Lab, LabWorkflow, UserWorkflow
from app.models.user import Role, User
from app.schemas.labs import LabDetail, LabPerson, LabSummary, WorkflowName

PERSON_KIND = "Person"
EMAIL_LENGTH = 320
EMAIL = re.compile(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+")
NOT_AN_EMAIL = "Not an email address: {emails}"
NAME_TAKEN = "There is already a lab called {name}."
CANNOT_ADD = "Already in another lab, or an owner: {emails}"
UNKNOWN_WORKFLOWS = "No such workflows: {names}"
NOT_THE_LABS = "This lab does not have: {names}"


def clean_emails(raw: Iterable[str]) -> list[str]:
    """
    Emails as they are stored: trimmed, lower case, each one once.

    :param raw: The addresses as typed.
    :type raw: Iterable[str]
    :return: The clean addresses, in the order given.
    :rtype: list[str]
    :raises HTTPException: 422 naming any that are not addresses.
    """
    emails = list(dict.fromkeys(item.strip().lower() for item in raw))
    bad = [
        email
        for email in emails
        if len(email) > EMAIL_LENGTH or not EMAIL.fullmatch(email)
    ]
    if bad:
        raise unprocessable(NOT_AN_EMAIL.format(emails=", ".join(bad)))
    return emails


def check_names(
    names: Iterable[str], known: Collection[str], message: str
) -> None:
    """
    Refuse workflow ids outside the ones that may be used here.

    :param names: The ids asked for.
    :type names: Iterable[str]
    :param known: The ids that may be used.
    :type known: Collection[str]
    :param message: What to say, with ``{names}`` for those refused.
    :type message: str
    :raises HTTPException: 422 naming those outside.
    """
    outside = sorted(set(names) - set(known))
    if outside:
        raise unprocessable(message.format(names=", ".join(outside)))


async def make_lab(db: AsyncSession, name: str) -> Lab:
    """
    A new lab.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param name: Its name.
    :type name: str
    :return: The lab.
    :rtype: Lab
    :raises HTTPException: 409 if the name is taken.
    """
    made = (
        insert(Lab)
        .values(name=name)
        .on_conflict_do_nothing(index_elements=[Lab.name])
        .returning(Lab)
    )
    lab = await db.scalar(made)
    if lab is None:
        raise conflict(NAME_TAKEN.format(name=name))
    return lab


async def rename_lab(db: AsyncSession, lab: Lab, name: str) -> None:
    """
    Give a lab a new name.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param lab: The lab.
    :type lab: Lab
    :param name: Its new name.
    :type name: str
    :raises HTTPException: 409 if another lab has that name.
    """
    taken = exists().where(Lab.name == name, Lab.id != lab.id)
    if await db.scalar(select(taken)):
        raise conflict(NAME_TAKEN.format(name=name))
    lab.name = name


async def give_lab_workflows(
    db: AsyncSession, lab_id: uuid.UUID, workflows: Collection[str]
) -> None:
    """
    Make these the workflows a lab has.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param lab_id: The lab.
    :type lab_id: uuid.UUID
    :param workflows: Workflow ids.
    :type workflows: Collection[str]
    """
    await db.execute(delete(LabWorkflow).where(LabWorkflow.lab_id == lab_id))
    db.add_all(
        LabWorkflow(lab_id=lab_id, workflow_id=name) for name in set(workflows)
    )


async def add_people(
    db: AsyncSession, lab_id: uuid.UUID, emails: list[str]
) -> None:
    """
    Put people in a lab by their email, making those new here. Anyone
    already in it stays as they are. An address in another lab, or an
    owner's, refuses the whole request.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param lab_id: The lab.
    :type lab_id: uuid.UUID
    :param emails: Clean addresses (``clean_emails``).
    :type emails: list[str]
    :raises HTTPException: 409 naming the addresses refused.
    """
    new = [{"email": email, "lab_id": lab_id} for email in emails]
    made = insert(User).values(new)
    await db.execute(made.on_conflict_do_nothing(index_elements=[User.email]))
    listed = User.email.in_(emails)
    free = update(User).where(
        listed, User.lab_id.is_(None), User.role != Role.OWNER
    )
    await db.execute(free.values(lab_id=lab_id))
    elsewhere = or_(User.role == Role.OWNER, User.lab_id != lab_id)
    query = select(User.email).where(listed, elsewhere)
    taken = (await db.scalars(query)).all()
    if taken:
        raise conflict(CANNOT_ADD.format(emails=", ".join(sorted(taken))))


async def make_admin(db: AsyncSession, lab_id: uuid.UUID, email: str) -> None:
    """
    Make someone in a lab its admin.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param lab_id: The lab.
    :type lab_id: uuid.UUID
    :param email: Their clean address.
    :type email: str
    """
    theirs = update(User).where(User.email == email, User.lab_id == lab_id)
    await db.execute(theirs.values(role=Role.ADMIN))


async def person_in_lab(
    db: AsyncSession, lab_id: uuid.UUID, person_id: uuid.UUID
) -> User:
    """
    Someone in this lab.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param lab_id: The lab.
    :type lab_id: uuid.UUID
    :param person_id: The person.
    :type person_id: uuid.UUID
    :return: The person.
    :rtype: User
    :raises HTTPException: 404 if they are not in it.
    """
    person = await db.get(User, person_id)
    if person is None or person.lab_id != lab_id:
        raise not_found(PERSON_KIND, person_id)
    return person


async def workflows_of_lab(db: AsyncSession, lab_id: uuid.UUID) -> set[str]:
    """
    The workflows a lab has.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param lab_id: The lab.
    :type lab_id: uuid.UUID
    :return: Workflow ids.
    :rtype: set[str]
    """
    query = select(LabWorkflow.workflow_id).where(LabWorkflow.lab_id == lab_id)
    return set((await db.scalars(query)).all())


async def tick_for_person(
    db: AsyncSession, person: User, workflows: Collection[str]
) -> None:
    """
    Make these the workflows ticked for a person; each must be one
    their lab has.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param person: The person, in a lab.
    :type person: User
    :param workflows: Workflow ids.
    :type workflows: Collection[str]
    :raises HTTPException: 422 naming those their lab does not have.
    """
    check_names(
        workflows, await workflows_of_lab(db, person.lab_id), NOT_THE_LABS
    )
    theirs = UserWorkflow.user_id == person.id
    await db.execute(delete(UserWorkflow).where(theirs))
    db.add_all(
        UserWorkflow(user_id=person.id, workflow_id=name)
        for name in set(workflows)
    )


async def remove_person(db: AsyncSession, person: User) -> None:
    """
    Take someone out of their lab: they lose their ticks, are signed
    out everywhere, and their keys stop working, so nothing of theirs
    outlives the decision. Their runs stay.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param person: The person.
    :type person: User
    """
    person.lab_id = None
    person.role = Role.USER
    await db.execute(
        delete(UserWorkflow).where(UserWorkflow.user_id == person.id)
    )
    await db.execute(
        delete(BrowserSession).where(BrowserSession.user_id == person.id)
    )
    keys = update(ApiKey).where(ApiKey.user_id == person.id)
    await db.execute(keys.values(is_active=False))


def named(catalog: Catalog, workflows: Collection[str]) -> list[WorkflowName]:
    """
    Workflows with their titles, in catalog order. An id the catalog no
    longer has is left out.

    :param catalog: The current catalog.
    :type catalog: Catalog
    :param workflows: Workflow ids.
    :type workflows: Collection[str]
    :return: The names.
    :rtype: list[WorkflowName]
    """
    return [
        WorkflowName(id=workflow.id, title=workflow.title)
        for workflow in catalog.workflows.values()
        if workflow.id in workflows
    ]


async def lab_summaries(db: AsyncSession, catalog: Catalog) -> list[LabSummary]:
    """
    Every lab, by name, with its workflows and how many people it has.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param catalog: The current catalog.
    :type catalog: Catalog
    :return: The labs.
    :rtype: list[LabSummary]
    """
    given: defaultdict[uuid.UUID, set[str]] = defaultdict(set)
    ticks = select(LabWorkflow.lab_id, LabWorkflow.workflow_id)
    for lab_id, name in await db.execute(ticks):
        given[lab_id].add(name)
    counted = select(User.lab_id, func.count()).group_by(User.lab_id)
    people = Counter(dict((await db.execute(counted)).all()))
    labs = (await db.scalars(select(Lab).order_by(Lab.name))).all()
    return [
        LabSummary(
            id=lab.id,
            name=lab.name,
            workflows=named(catalog, given[lab.id]),
            people=people[lab.id],
        )
        for lab in labs
    ]


async def people_of_lab(db: AsyncSession, lab_id: uuid.UUID) -> list[LabPerson]:
    """
    A lab's people, admins first, with what is ticked for each.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param lab_id: The lab.
    :type lab_id: uuid.UUID
    :return: The people.
    :rtype: list[LabPerson]
    """
    query = (
        select(User)
        .where(User.lab_id == lab_id)
        .order_by(User.role, User.email)
    )
    people = (await db.scalars(query)).all()
    ticks = select(UserWorkflow.user_id, UserWorkflow.workflow_id).where(
        UserWorkflow.user_id.in_([person.id for person in people])
    )
    ticked: defaultdict[uuid.UUID, list[str]] = defaultdict(list)
    for person_id, name in await db.execute(ticks):
        ticked[person_id].append(name)
    return [
        LabPerson(
            id=person.id,
            email=person.email,
            name=person.name,
            role=person.role,
            workflows=sorted(ticked[person.id]),
            last_seen_at=person.last_seen_at,
        )
        for person in people
    ]


async def lab_detail(
    db: AsyncSession, lab: Lab, catalog: Catalog, asking: User
) -> LabDetail:
    """
    A lab as those who run it see it: the owner can give it any
    workflow, its admin only reads what it has.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param lab: The lab.
    :type lab: Lab
    :param catalog: The current catalog.
    :type catalog: Catalog
    :param asking: Who is asking.
    :type asking: User
    :return: The lab.
    :rtype: LabDetail
    """
    has = await workflows_of_lab(db, lab.id)
    return LabDetail(
        id=lab.id,
        name=lab.name,
        workflows=named(catalog, has),
        available=named(catalog, catalog.workflows if asking.is_owner else has),
        people=await people_of_lab(db, lab.id),
    )
