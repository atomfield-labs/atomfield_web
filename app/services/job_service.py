"""
app/services/job_service.py — Business Logic Layer

📚 LESSON: The Service Layer Pattern (why not put logic in routes?)

    Routes should be THIN — they handle HTTP concerns:
    • Parse request → call service → return response
    • They know about Request, Response, status codes.

    Services handle BUSINESS LOGIC:
    • Create a job, validate it, save it.
    • Fetch a job, handle not-found.
    • They know about Jobs, databases, business rules.

    Why separate?
    1. TESTABILITY: You can unit-test create_job() with a mock DB session
       without spinning up FastAPI or HTTP. Routes need integration tests.

    2. REUSABILITY: The ARQ worker also needs to update job status.
       If that logic is in a route handler, the worker can't reuse it.
       Services are callable from routes, workers, CLI scripts, anywhere.

    3. SINGLE RESPONSIBILITY: Routes handle HTTP. Services handle business.
       When you add "retry logic" or "notification on failure", it goes in
       the service — the route stays untouched.

📚 LESSON: "Raise HTTPException in a service? Isn't that an HTTP concern?"
    Technically yes. In a purist DDD architecture, the service would raise
    a domain exception (e.g., JobNotFoundError), and the route would catch it
    and convert to HTTPException. For a project this size, the pragmatic
    approach is acceptable — but as AtomField grows, consider refactoring
    to domain exceptions with a global exception handler middleware.
"""

import uuid as _uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from fastapi import HTTPException

from app.models.job import Job, JobDependency
from app.schemas.job import JobSubmitRequest, PipelineSubmitRequest



async def create_job(db: AsyncSession, request: JobSubmitRequest) -> Job:
    """
    Create a new Job entity and persist it to the database.

    Returns the refreshed Job with its server-generated UUID and timestamps.
    """
    new_job = Job(
        script_name=request.script_name,
        parameters=request.parameters,
        status="Pending",
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    return new_job


async def get_job_by_id(db: AsyncSession, job_id: _uuid.UUID) -> Job:
    """
    Fetch a single job by UUID.

    📚 LESSON: Type-safe queries
        job_id is typed as uuid.UUID, not str.
        asyncpg can send a native UUID to PostgreSQL without CAST overhead.
        If someone passes "not-a-uuid", FastAPI rejects it at the route layer
        before it ever reaches this function.
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


async def list_jobs(
    db: AsyncSession,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Job], int]:
    """
    List jobs with optional status filter and pagination.

    📚 LESSON: Pagination is non-negotiable for production APIs.
        Without limit/offset, a GET /jobs query on 1M rows will:
        • OOM the server trying to serialize all rows
        • Slam PostgreSQL with a full table scan
        • Send a 200MB JSON response to the client

        Always default to a sane limit (50) and let clients page through.

    Returns: (jobs, total_count) tuple for pagination metadata.
    """
    query = select(Job).order_by(Job.created_at.desc())
    count_query = select(func.count(Job.id))

    if status:
        query = query.where(Job.status == status)
        count_query = count_query.where(Job.status == status)

    # Get total count for pagination
    total = (await db.execute(count_query)).scalar() or 0

    # Get the page
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    jobs = list(result.scalars().all())

    return jobs, total


async def mark_job_running(job_id: str, session: AsyncSession) -> None:
    """Mark a job as Running (called by the worker)."""
    await session.execute(
        update(Job).where(Job.id == job_id).values(status="Running")
    )
    await session.commit()


async def mark_job_success(
    job_id: str, output_data: dict, session: AsyncSession
) -> None:
    """Mark a job as Success with its output data (called by the worker)."""
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status="Success", output_data=output_data)
    )
    await session.commit()


async def mark_job_failed(
    job_id: str, error_message: str, session: AsyncSession
) -> None:
    """Mark a job as Failed with its error message (called by the worker)."""
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status="Failed", error_message=error_message)
    )
    await session.commit()

# -----------------------------------------------------------------------
# Phase 4: DAG Pipeline Orchestration
# -----------------------------------------------------------------------

async def submit_pipeline(
    db: AsyncSession, 
    request: PipelineSubmitRequest, 
    redis_queue=None
) -> dict:
    """
    Submits a full DAG pipeline of jobs.
    """
    ui_to_db_map = {}
    db_jobs = []
    in_degrees = {node.ui_id: 0 for node in request.nodes}

    # Generate a unique ID for this entire DAG execution
    pipeline_id = f"pipeline_{_uuid.uuid4().hex[:8]}"

    # 1. Create all jobs as Blocked initially
    for node in request.nodes:
        # Inject the pipeline ID so the worker knows which folder to mount
        params = node.parameters or {}
        params["pipeline_id"] = pipeline_id
        
        new_job = Job(
            script_name=node.script_name,
            parameters=params,
            status="Blocked"
        )
        db.add(new_job)
        db_jobs.append((node.ui_id, new_job))
    
    # 📚 LESSON: Transaction Safety
    # flush() sends the INSERT statements to Postgres and retrieves the auto-generated
    # UUIDs, but does NOT commit the transaction yet. This allows us to use the UUIDs
    # for dependencies, keeping the entire pipeline creation atomic.
    await db.flush() 

    for ui_id, job in db_jobs:
        ui_to_db_map[ui_id] = job.id

    # 2. Map dependencies
    for edge in request.edges:
        upstream_uuid = ui_to_db_map[edge.upstream_ui_id]
        downstream_uuid = ui_to_db_map[edge.downstream_ui_id]
        
        dependency = JobDependency(
            upstream_id=upstream_uuid, 
            downstream_id=downstream_uuid
        )
        db.add(dependency)
        in_degrees[edge.downstream_ui_id] += 1

    # 3. Find root nodes (in_degree == 0) and enqueue them
    enqueued_count = 0
    for ui_id, job in db_jobs:
        if in_degrees[ui_id] == 0:
            job.status = "Pending"
            enqueued_count += 1
            if redis_queue:
                await redis_queue.enqueue_job("execute_script", str(job.id), job.script_name, job.parameters)

    # 4. Final atomic commit
    await db.commit()
    
    return {
        "status": "success", 
        "total_nodes": len(request.nodes), 
        "roots_started": enqueued_count
    }


async def evaluate_downstream_dependencies(db: AsyncSession, completed_job_id: str, redis_queue):
    """
    Evaluates downstream jobs for a completed node.
    If a downstream job has ALL its upstream parents marked 'Success',
    it is unblocked and enqueued.
    """
    if isinstance(completed_job_id, str):
        completed_job_id = _uuid.UUID(completed_job_id)

    # 1. Find all downstream children
    stmt = select(JobDependency.downstream_id).where(JobDependency.upstream_id == completed_job_id)
    result = await db.execute(stmt)
    downstream_ids = result.scalars().all()

    for d_id in downstream_ids:
        # 📚 LESSON: Prevent Fan-In Race Conditions
        # If Job C depends on A and B, and A & B finish concurrently, two workers will 
        # attempt to unblock C. `with_for_update()` places a row-level lock on Job C.
        lock_stmt = select(Job).where(Job.id == d_id).with_for_update()
        d_job = await db.scalar(lock_stmt)
        
        # If another worker already unblocked it, skip
        if not d_job or d_job.status != "Blocked":
            continue

        # Fetch all parents of this specific downstream job
        parent_stmt = select(Job).join(
            JobDependency, Job.id == JobDependency.upstream_id
        ).where(
            JobDependency.downstream_id == d_id
        )
        parent_result = await db.execute(parent_stmt)
        parents = parent_result.scalars().all()

        # Check if any parent failed
        if any(p.status == "Failed" for p in parents):
            d_job.status = "Failed"
            d_job.error_message = "Upstream dependency failed"
            continue

        # Check if all parents are successful
        if all(p.status == "Success" for p in parents):
            # 📚 Industry Standard: Passing XCom data from upstream to downstream
            from sqlalchemy.orm.attributes import flag_modified
            import copy
            
            injected_payload = copy.deepcopy(d_job.parameters) if d_job.parameters else {}
            injected_payload["upstream_results"] = {}
            
            for p in parents:
                injected_payload["upstream_results"][str(p.id)] = p.output_data

            d_job.parameters = injected_payload
            flag_modified(d_job, "parameters")
            d_job.status = "Pending"

            
            # Enqueue the newly unblocked job
            if redis_queue:
                await redis_queue.enqueue_job(
                    "execute_script", 
                    str(d_job.id), 
                    d_job.script_name, 
                    d_job.parameters
                )
    
    # We commit here so that all the status changes to the downstream nodes persist.
    await db.commit()
