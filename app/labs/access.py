"""
Which workflows a person may use, read from what was ticked for them.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lab import LabWorkflow, UserWorkflow
from app.models.user import Role, User


async def allowed_workflows(db: AsyncSession, user: User) -> frozenset[str]:
    """
    The workflows a person may use, an owner aside (they may use all).
    A lab's admin has all their lab's; a user has those ticked for them
    that their lab still has, so taking one from a lab takes it from
    everyone at once, and giving it back restores them. Nobody without
    a lab has any.

    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param user: The person.
    :type user: User
    :return: Workflow ids.
    :rtype: frozenset[str]
    """
    query = select(LabWorkflow.workflow_id).where(
        LabWorkflow.lab_id == user.lab_id
    )
    if user.role != Role.ADMIN:
        ticked = select(UserWorkflow.workflow_id).where(
            UserWorkflow.user_id == user.id
        )
        query = query.where(LabWorkflow.workflow_id.in_(ticked))
    return frozenset((await db.scalars(query)).all())
