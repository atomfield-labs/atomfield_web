"""
HTTP route serving the task catalog to the UI.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_catalog
from app.catalog.catalog import Catalog
from app.catalog.models import TaskDefinition

router = APIRouter(prefix="/task-definitions", tags=["Catalog"])


@router.get("", response_model=list[TaskDefinition])
async def list_task_definitions(
    catalog: Catalog = Depends(get_catalog),
) -> list[TaskDefinition]:
    """
    List every task the platform can run, with its parameters.

    Public on purpose: the UI shows the menu before anyone has a key.

    :param catalog: Loaded task catalog.
    :type catalog: Catalog
    :return: Task definitions in catalog order.
    :rtype: list[TaskDefinition]
    """
    return list(catalog.tasks.values())
