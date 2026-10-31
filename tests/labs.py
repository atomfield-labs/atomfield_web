"""
Putting people in a lab straight in the database, as its admin would on
the lab page: most tests have no need to go through that.
"""

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.lab import Lab, LabWorkflow, UserWorkflow
from app.models.user import User

TEST_LAB = "Test lab"
# Every workflow of the catalogs tests run against: the real one, and
# the fixture's.
EVERY_WORKFLOW = (
    "nanoreactor",
    "quantum_espresso",
    "wannier90",
    "toy_chain",
    "toy_other",
)


async def shared_lab_id(session: AsyncSession) -> uuid.UUID:
    """
    The lab most tests' people are in, made the first time, holding
    every workflow.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :return: The lab's id.
    :rtype: uuid.UUID
    """
    made = (
        insert(Lab)
        .values(name=TEST_LAB)
        .on_conflict_do_update(
            index_elements=[Lab.name], set_={"name": TEST_LAB}
        )
        .returning(Lab.id)
    )
    lab_id = (await session.execute(made)).scalar_one()
    given = [{"lab_id": lab_id, "workflow_id": name} for name in EVERY_WORKFLOW]
    await session.execute(
        insert(LabWorkflow).values(given).on_conflict_do_nothing()
    )
    return lab_id


async def give_every_workflow(
    session: AsyncSession, user_id: uuid.UUID
) -> None:
    """
    Tick every workflow for a person.

    :param session: Open database session; the caller commits.
    :type session: AsyncSession
    :param user_id: The person.
    :type user_id: uuid.UUID
    """
    given = [
        {"user_id": user_id, "workflow_id": name} for name in EVERY_WORKFLOW
    ]
    await session.execute(
        insert(UserWorkflow).values(given).on_conflict_do_nothing()
    )


async def add_to_lab(make_session: async_sessionmaker, email: str) -> None:
    """
    List an account in the shared lab with every workflow, so it can
    sign in.

    :param make_session: Session factory on the test database.
    :type make_session: async_sessionmaker
    :param email: The account's address.
    :type email: str
    """
    async with make_session() as session:
        lab_id = await shared_lab_id(session)
        listed = (
            insert(User)
            .values(email=email, lab_id=lab_id)
            .on_conflict_do_update(
                index_elements=[User.email], set_={"lab_id": lab_id}
            )
            .returning(User.id)
        )
        user_id = (await session.execute(listed)).scalar_one()
        await give_every_workflow(session, user_id)
        await session.commit()
