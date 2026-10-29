"""
HTTP routes serving the catalog to the UI: the tasks, and the
ready-made pipelines built from them.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_catalog
from app.catalog.models import PipelineTemplate, TaskDefinition
from app.releases.catalogs import CurrentCatalog

router = APIRouter(tags=["Catalog"])


@router.get("/task-definitions", response_model=list[TaskDefinition])
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


@router.get("/pipeline-templates", response_model=list[PipelineTemplate])
async def list_pipeline_templates(
    current: CurrentCatalog = Depends(get_current_catalog),
) -> list[PipelineTemplate]:
    """
    List the ready-made pipelines of the newest scripts release. They
    ship with the scripts they call, so a template always matches the
    tasks a new run gets.

    Public on purpose, like the task menu.

    :param current: The current release and its catalog.
    :type current: CurrentCatalog
    :return: Templates in catalog order.
    :rtype: list[PipelineTemplate]
    """
    return list(current.catalog.templates.values())
