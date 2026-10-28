"""
HTTP route serving the task catalog to the UI.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_catalog
from app.catalog.models import TaskDefinition
from app.releases.catalogs import CurrentCatalog

router = APIRouter(prefix="/task-definitions", tags=["Catalog"])


@router.get("", response_model=list[TaskDefinition])
async def list_task_definitions(
    current: CurrentCatalog = Depends(get_current_catalog),
) -> list[TaskDefinition]:
    """
    List every task a new run can use, with its parameters: those of
    the newest scripts release.

    Public on purpose: the UI shows the menu before anyone has a key.

    :param current: The current release and its catalog.
    :type current: CurrentCatalog
    :return: Task definitions in catalog order.
    :rtype: list[TaskDefinition]
    """
    return list(current.catalog.tasks.values())
