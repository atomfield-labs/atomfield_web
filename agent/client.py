"""
HTTP client for the agent API.

The wire format is the server's own schemas (``app.agents.schemas``),
so client and server cannot disagree about a field.

Signed links are followed with a second client that carries no token:
a link holds its own permission, and it may point at a cloud store
that must never see the agent's token.
"""

import os
import uuid
from pathlib import Path

import httpx

from app.agents.schemas import (
    BundleReport,
    CompletionRequest,
    CompletionResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    JobAssignment,
    JobReference,
    UploadLinksRequest,
    UploadLinksResponse,
)

NO_JOB = 204
STALE = 409
UPLOAD_CHUNK_BYTES = 1024 * 1024
# Longer than the server's longest long-poll, so a held claim is not
# mistaken for a dead connection.
READ_TIMEOUT_SECONDS = 45.0


class AgentClient:
    """
    Calls the agent API with the agent's bearer token.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        links: httpx.AsyncClient,
    ) -> None:
        """
        Wrap configured HTTP clients.

        :param http: Client with base URL and Authorization header set.
        :type http: httpx.AsyncClient
        :param links: Client for signed links: same base URL, no token.
        :type links: httpx.AsyncClient
        """
        self.http = http
        self.links = links

    @classmethod
    def connect(cls, api_url: str, token: str) -> "AgentClient":
        """
        Create a client for one API with one token.

        :param api_url: Base URL of the API.
        :type api_url: str
        :param token: The agent's bearer token.
        :type token: str
        :return: Ready client.
        :rtype: AgentClient
        """
        http = httpx.AsyncClient(
            base_url=api_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(10.0, read=READ_TIMEOUT_SECONDS),
        )
        links = httpx.AsyncClient(base_url=api_url, timeout=http.timeout)
        return cls(http, links)

    async def claim(
        self, wait_seconds: float, scheduled: bool = False
    ) -> JobAssignment | None:
        """
        Ask for one job, letting the server wait up to ``wait_seconds``.

        :param wait_seconds: Long-poll wait.
        :type wait_seconds: float
        :param scheduled: Jobs go to a scheduler and may queue there.
        :type scheduled: bool
        :return: An assignment, or None if no job arrived.
        :rtype: JobAssignment | None
        :raises httpx.HTTPError: On network or server errors.
        """
        response = await self.http.post(
            "/api/agent/claims",
            json={"wait_seconds": wait_seconds, "scheduled": scheduled},
        )
        if response.status_code == NO_JOB:
            return None
        response.raise_for_status()
        return JobAssignment.model_validate(response.json())

    async def heartbeat(
        self,
        held: list[JobReference],
        started: list[JobReference] | None = None,
    ) -> HeartbeatResponse:
        """
        Report the attempts this agent is running.

        :param held: Attempts in progress.
        :type held: list[JobReference]
        :param started: Those that have begun running.
        :type started: list[JobReference] | None
        :return: Attempts to cancel or abandon.
        :rtype: HeartbeatResponse
        :raises httpx.HTTPError: On network or server errors.
        """
        request = HeartbeatRequest(jobs=held, started=started or [])
        body = request.model_dump(mode="json")
        response = await self.http.post("/api/agent/heartbeat", json=body)
        response.raise_for_status()
        return HeartbeatResponse.model_validate(response.json())

    async def complete(
        self,
        job_id: uuid.UUID,
        report: CompletionRequest,
    ) -> CompletionResponse | None:
        """
        Report how an attempt ended.

        :param job_id: Finished job.
        :type job_id: uuid.UUID
        :param report: Outcome.
        :type report: CompletionRequest
        :return: The recorded outcome (with any runs to zip), or None
            if the server refused a stale report (409).
        :rtype: CompletionResponse | None
        :raises httpx.HTTPError: On network or other server errors.
        """
        response = await self.http.post(
            f"/api/agent/jobs/{job_id}/complete",
            json=report.model_dump(mode="json"),
        )
        if response.status_code == STALE:
            return None
        response.raise_for_status()
        return CompletionResponse.model_validate(response.json())

    async def report_bundle(
        self,
        run_id: uuid.UUID,
        report: BundleReport,
    ) -> bool:
        """
        Report how zipping and uploading a run ended.

        :param run_id: The run.
        :type run_id: uuid.UUID
        :param report: Outcome.
        :type report: BundleReport
        :return: False if the server was not expecting it (409).
        :rtype: bool
        :raises httpx.HTTPError: On network or other server errors.
        """
        response = await self.http.post(
            f"/api/agent/runs/{run_id}/bundle",
            json=report.model_dump(mode="json"),
        )
        if response.status_code == STALE:
            return False
        response.raise_for_status()
        return True

    async def upload_file(self, url: str, source: Path) -> None:
        """
        Stream a file to a signed upload link, chunk by chunk.

        :param url: Signed upload link.
        :type url: str
        :param source: File to send.
        :type source: Path
        :raises httpx.HTTPError: On network errors or a refused link.
        """

        async def chunks():
            with source.open("rb") as stream:
                while chunk := stream.read(UPLOAD_CHUNK_BYTES):
                    yield chunk

        headers = {"Content-Length": str(source.stat().st_size)}
        response = await self.links.put(url, content=chunks(), headers=headers)
        response.raise_for_status()

    async def download(self, url: str, destination: Path) -> None:
        """
        Save what a signed link serves, appearing all at once.

        :param url: Signed download link (relative to the API, or a
            full URL of another store).
        :type url: str
        :param destination: File to create.
        :type destination: Path
        :raises httpx.HTTPError: On network errors or a refused link.
        """
        partial = destination.with_name(f".{destination.name}.part")
        try:
            async with self.links.stream("GET", url) as response:
                response.raise_for_status()
                with partial.open("wb") as stream:
                    async for chunk in response.aiter_bytes():
                        stream.write(chunk)
            os.replace(partial, destination)
        finally:
            partial.unlink(missing_ok=True)

    async def upload_links(
        self,
        job_id: uuid.UUID,
        attempt: int,
        names: list[str],
    ) -> UploadLinksResponse | None:
        """
        Ask where to upload a finishing attempt's small files.

        :param job_id: The job.
        :type job_id: uuid.UUID
        :param attempt: Its attempt.
        :type attempt: int
        :param names: File names.
        :type names: list[str]
        :return: The links, or None if the attempt is stale (409).
        :rtype: UploadLinksResponse | None
        :raises httpx.HTTPError: On network or other server errors.
        """
        body = UploadLinksRequest(attempt=attempt, names=names)
        response = await self.http.post(
            f"/api/agent/jobs/{job_id}/uploads",
            json=body.model_dump(mode="json"),
        )
        if response.status_code == STALE:
            return None
        response.raise_for_status()
        return UploadLinksResponse.model_validate(response.json())

    async def upload(self, url: str, content: bytes) -> None:
        """
        Send bytes to a signed upload link.

        :param url: Signed upload link.
        :type url: str
        :param content: What to store.
        :type content: bytes
        :raises httpx.HTTPError: On network errors or a refused link.
        """
        response = await self.links.put(url, content=content)
        response.raise_for_status()

    async def close(self) -> None:
        """
        Close the underlying connections.
        """
        await self.http.aclose()
        await self.links.aclose()
