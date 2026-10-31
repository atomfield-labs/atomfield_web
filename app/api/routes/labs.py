"""
HTTP routes for labs: the owner makes them and gives them workflows; a
lab's admin adds its people and ticks workflows for each. All of it
happens in the web app, signed in: a leaked key can change nothing here.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_browser_user,
    get_current_catalog,
    get_managed_lab,
    require_browser_owner,
)
from app.api.errors import forbidden
from app.db.session import get_db
from app.labs.service import (
    UNKNOWN_WORKFLOWS,
    add_people,
    check_names,
    clean_emails,
    give_lab_workflows,
    lab_detail,
    lab_summaries,
    make_admin,
    make_lab,
    person_in_lab,
    remove_person,
    rename_lab,
    tick_for_person,
)
from app.models.lab import Lab
from app.models.user import Role, User
from app.releases.catalogs import CurrentCatalog
from app.schemas.labs import (
    LabChange,
    LabCreate,
    LabDetail,
    LabSummary,
    PeopleAdd,
    PersonChange,
)

router = APIRouter(prefix="/labs", tags=["Labs"])
OWNER_SETS_ROLES = "Only the platform's owner changes roles."
OWNER_REMOVES_ADMINS = "Only the platform's owner removes an admin."


@router.get("", response_model=list[LabSummary])
async def list_labs(
    _owner: User = Depends(require_browser_owner),
    db: AsyncSession = Depends(get_db),
    current: CurrentCatalog = Depends(get_current_catalog),
) -> list[LabSummary]:
    """
    Every lab.

    :param _owner: The owner.
    :type _owner: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param current: The current catalog, for workflows' titles.
    :type current: CurrentCatalog
    :return: The labs.
    :rtype: list[LabSummary]
    """
    return await lab_summaries(db, current.catalog)


@router.post("", response_model=LabDetail, status_code=201)
async def add_lab(
    payload: LabCreate,
    owner: User = Depends(require_browser_owner),
    db: AsyncSession = Depends(get_db),
    current: CurrentCatalog = Depends(get_current_catalog),
) -> LabDetail:
    """
    Make a lab, and name the person who will run it. They can sign in
    from now on.

    :param payload: Its name, and its admin's email.
    :type payload: LabCreate
    :param owner: The owner.
    :type owner: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param current: The current catalog, for workflows' titles.
    :type current: CurrentCatalog
    :return: The new lab.
    :rtype: LabDetail
    """
    emails = clean_emails([payload.admin_email])
    lab = await make_lab(db, payload.name.strip())
    await add_people(db, lab.id, emails)
    await make_admin(db, lab.id, emails[0])
    await db.commit()
    return await lab_detail(db, lab, current.catalog, owner)


@router.get("/{lab_id}", response_model=LabDetail)
async def get_lab(
    lab: Lab = Depends(get_managed_lab),
    user: User = Depends(get_browser_user),
    db: AsyncSession = Depends(get_db),
    current: CurrentCatalog = Depends(get_current_catalog),
) -> LabDetail:
    """
    One lab, with its people.

    :param lab: The lab.
    :type lab: Lab
    :param user: Who is asking.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param current: The current catalog, for workflows' titles.
    :type current: CurrentCatalog
    :return: The lab.
    :rtype: LabDetail
    """
    return await lab_detail(db, lab, current.catalog, user)


@router.patch("/{lab_id}", response_model=LabDetail)
async def change_lab(
    payload: LabChange,
    lab: Lab = Depends(get_managed_lab),
    owner: User = Depends(require_browser_owner),
    db: AsyncSession = Depends(get_db),
    current: CurrentCatalog = Depends(get_current_catalog),
) -> LabDetail:
    """
    Rename a lab, or change which workflows it has.

    :param payload: What changes.
    :type payload: LabChange
    :param lab: The lab.
    :type lab: Lab
    :param owner: The owner.
    :type owner: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param current: The current catalog, which the workflows must be in.
    :type current: CurrentCatalog
    :return: The lab as it now stands.
    :rtype: LabDetail
    """
    if payload.name is not None:
        await rename_lab(db, lab, payload.name.strip())
    if payload.workflows is not None:
        known = current.catalog.workflows
        check_names(payload.workflows, known, UNKNOWN_WORKFLOWS)
        await give_lab_workflows(db, lab.id, payload.workflows)
    await db.commit()
    return await lab_detail(db, lab, current.catalog, owner)


@router.post("/{lab_id}/people", response_model=LabDetail)
async def add_lab_people(
    payload: PeopleAdd,
    lab: Lab = Depends(get_managed_lab),
    user: User = Depends(get_browser_user),
    db: AsyncSession = Depends(get_db),
    current: CurrentCatalog = Depends(get_current_catalog),
) -> LabDetail:
    """
    Add people to a lab by email. They can sign in from now on, with
    nothing ticked for them yet.

    :param payload: Their emails.
    :type payload: PeopleAdd
    :param lab: The lab.
    :type lab: Lab
    :param user: Who is asking.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param current: The current catalog, for workflows' titles.
    :type current: CurrentCatalog
    :return: The lab as it now stands.
    :rtype: LabDetail
    """
    await add_people(db, lab.id, clean_emails(payload.emails))
    await db.commit()
    return await lab_detail(db, lab, current.catalog, user)


@router.patch("/{lab_id}/people/{person_id}", response_model=LabDetail)
async def change_lab_person(
    person_id: UUID,
    payload: PersonChange,
    lab: Lab = Depends(get_managed_lab),
    user: User = Depends(get_browser_user),
    db: AsyncSession = Depends(get_db),
    current: CurrentCatalog = Depends(get_current_catalog),
) -> LabDetail:
    """
    Tick workflows for someone in the lab; the owner can also change
    whether they are its admin.

    :param person_id: The person.
    :type person_id: UUID
    :param payload: What changes.
    :type payload: PersonChange
    :param lab: The lab.
    :type lab: Lab
    :param user: Who is asking.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param current: The current catalog, for workflows' titles.
    :type current: CurrentCatalog
    :return: The lab as it now stands.
    :rtype: LabDetail
    :raises HTTPException: 403 for an admin changing a role.
    """
    person = await person_in_lab(db, lab.id, person_id)
    if payload.role is not None:
        if not user.is_owner:
            raise forbidden(OWNER_SETS_ROLES)
        person.role = Role(payload.role)
    if payload.workflows is not None:
        await tick_for_person(db, person, payload.workflows)
    await db.commit()
    return await lab_detail(db, lab, current.catalog, user)


@router.delete("/{lab_id}/people/{person_id}", response_model=LabDetail)
async def remove_lab_person(
    person_id: UUID,
    lab: Lab = Depends(get_managed_lab),
    user: User = Depends(get_browser_user),
    db: AsyncSession = Depends(get_db),
    current: CurrentCatalog = Depends(get_current_catalog),
) -> LabDetail:
    """
    Take someone out of the lab. Their runs stay.

    :param person_id: The person.
    :type person_id: UUID
    :param lab: The lab.
    :type lab: Lab
    :param user: Who is asking.
    :type user: User
    :param db: Asynchronous database session.
    :type db: AsyncSession
    :param current: The current catalog, for workflows' titles.
    :type current: CurrentCatalog
    :return: The lab as it now stands.
    :rtype: LabDetail
    :raises HTTPException: 403 for an admin removing an admin.
    """
    person = await person_in_lab(db, lab.id, person_id)
    if person.role == Role.ADMIN and not user.is_owner:
        raise forbidden(OWNER_REMOVES_ADMINS)
    await remove_person(db, person)
    await db.commit()
    return await lab_detail(db, lab, current.catalog, user)
