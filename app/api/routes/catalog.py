"""
HTTP routes serving the catalog to the UI, as the person asking sees it:
their workflows, the tasks in them, and the ready-made pipelines.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_my_catalog
from app.catalog.models import PipelineTemplate, TaskDefinition, Workflow
from app.releases.catalogs import CurrentCatalog

router = APIRouter(tags=["Catalog"])


@router.get("/workflows", response_model=list[Workflow])
async def list_workflows(
    current: CurrentCatalog = Depends(get_my_catalog),
) -> list[Workflow]:
    """
    List the workflows the caller may use.

    :param current: The newest release, limited to the caller.
    :type current: CurrentCatalog
    :return: Workflows in catalog order.
    :rtype: list[Workflow]
    """
    return list(current.catalog.workflows.values())


@router.get("/task-definitions", response_model=list[TaskDefinition])
async def list_task_definitions(
    current: CurrentCatalog = Depends(get_my_catalog),
) -> list[TaskDefinition]:
    """
    List every task the caller can use in a new run, with its
    parameters: those of the newest scripts release.

    :param current: The newest release, limited to the caller.
    :type current: CurrentCatalog
    :return: Task definitions in catalog order.
    :rtype: list[TaskDefinition]
    """
    return list(current.catalog.tasks.values())


@router.get("/pipeline-templates", response_model=list[PipelineTemplate])
async def list_pipeline_templates(
    current: CurrentCatalog = Depends(get_my_catalog),
) -> list[PipelineTemplate]:
    """
    List the ready-made pipelines the caller can use, of the newest
    scripts release. They ship with the scripts they call, so a template
    always matches the tasks a new run gets.

    :param current: The newest release, limited to the caller.
    :type current: CurrentCatalog
    :return: Templates in catalog order.
    :rtype: list[PipelineTemplate]
    """
    return list(current.catalog.templates.values())
