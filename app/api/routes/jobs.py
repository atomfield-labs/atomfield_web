"""
app/api/routes/jobs.py — Job HTTP Endpoints (Thin Controller Layer)

📚 LESSON: The Thin Controller Pattern

    Routes are "controllers" — they translate HTTP into service calls:
    1. Parse + validate the request (FastAPI + Pydantic do this for free)
    2. Call the service layer (business logic)
    3. Return the response (Pydantic serializes it)

    No business logic lives here. If you're writing `if job.status == ...`
    inside a route, it belongs in the service layer.

📚 LESSON: APIRouter (modular routing)
    Instead of @app.post(...), we use @router.post(...).
    This decouples routes from the app object — you can:
    • Add multiple route modules (jobs, users, pipelines)
    • Prefix them independently (/jobs, /users, /pipelines)
    • Test them in isolation
    • Lazy-load them for startup performance
"""

import uuid as _uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from arq import ArqRedis

from app.db.session import get_db
from app.api.dependencies import get_redis
from app.schemas.job import JobSubmitRequest, JobResponse, JobListResponse, PipelineSubmitRequest, PipelineSubmitResponse
from app.services import job_service


router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post("/submit", response_model=JobResponse, status_code=202)
async def submit_job(
    job_req: JobSubmitRequest,
    db: AsyncSession = Depends(get_db),
    redis: ArqRedis = Depends(get_redis),
):
    """
    Submit a new simulation job.

    Returns 202 Accepted — the job is queued, not yet executed.

    📚 LESSON: Dependency Injection > request.app.state
        Instead of `request.app.state.redis`, we inject `redis: ArqRedis`
        via Depends(get_redis). Benefits:
        • Route signature documents its dependencies explicitly
        • Testable — override get_redis with a mock in tests
        • No hidden coupling to the app object
    """
    # 1. Service layer handles DB persistence
    job = await job_service.create_job(db=db, request=job_req)

    # 2. Enqueue into Redis for the ARQ worker
    await redis.enqueue_job(
        "execute_script",
        str(job.id),
        job_req.script_name,
        job_req.parameters,
    )

    return job


@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(
    job_id: _uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Poll a job's current status and output.

    📚 LESSON: Type-safe path params
        `job_id: uuid.UUID` makes FastAPI:
        • Validate it's a real UUID (automatic 422 if not)
        • Convert to Python UUID (asyncpg handles natively — no CAST)
        • Document it correctly in OpenAPI/Swagger
    """
    return await job_service.get_job_by_id(db=db, job_id=job_id)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """
    List all jobs with optional status filter and pagination.

    📚 LESSON: GET /jobs vs GET /jobs/{id}
        Both use GET (read-only). The first returns a list, the second
        returns a single resource. RESTful convention:
        • Collection: GET /jobs?status=Running&limit=10
        • Resource:   GET /jobs/{uuid}
    """
    jobs, total = await job_service.list_jobs(
        db=db, status=status, limit=limit, offset=offset
    )
    return JobListResponse(jobs=jobs, total=total)

@router.post("/pipeline/submit", response_model=PipelineSubmitResponse, status_code=202)
async def submit_pipeline(
    pipeline_req: PipelineSubmitRequest,
    db: AsyncSession = Depends(get_db),
    redis: ArqRedis = Depends(get_redis),
):
    """
    Submit a DAG pipeline of simulation jobs.

    Returns 202 Accepted — root jobs are queued, downstream jobs are Blocked.
    """
    return await job_service.submit_pipeline(
        db=db, 
        request=pipeline_req, 
        redis_queue=redis
    )
