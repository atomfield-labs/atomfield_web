"""
HTTP client for the agent API.

The wire format is the server's own schemas (``app.agents.schemas``),
so client and server cannot disagree about a field.
"""

import uuid

import httpx

from app.agents.schemas import (
    CompletionRequest,
    HeartbeatRequest,
    HeartbeatResponse,
    JobAssignment,
    JobReference,
)

NO_JOB = 204
STALE = 409
# Longer than the server's longest long-poll, so a held claim is not
# mistaken for a dead connection.
READ_TIMEOUT_SECONDS = 45.0


class AgentClient:
    """
    Calls the agent API with the agent's bearer token.
    """

    def __init__(self, http: httpx.AsyncClient) -> None:
        """
        Wrap a configured HTTP client.

        :param http: Client with base URL and Authorization header set.
        :type http: httpx.AsyncClient
        """
        self.http = http

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
        return cls(http)

    async def claim(self, wait_seconds: float) -> JobAssignment | None:
        """
        Ask for one job, letting the server wait up to ``wait_seconds``.

        :param wait_seconds: Long-poll wait.
        :type wait_seconds: float
        :return: An assignment, or None if no job arrived.
        :rtype: JobAssignment | None
        :raises httpx.HTTPError: On network or server errors.
        """
        response = await self.http.post(
            "/api/agent/claims", json={"wait_seconds": wait_seconds}
        )
        if response.status_code == NO_JOB:
            return None
        response.raise_for_status()
        return JobAssignment.model_validate(response.json())

    async def heartbeat(self, held: list[JobReference]) -> HeartbeatResponse:
        """
        Report the attempts this agent is running.

        :param held: Attempts in progress.
        :type held: list[JobReference]
        :return: Attempts to cancel or abandon.
        :rtype: HeartbeatResponse
        :raises httpx.HTTPError: On network or server errors.
        """
        body = HeartbeatRequest(jobs=held).model_dump(mode="json")
        response = await self.http.post("/api/agent/heartbeat", json=body)
        response.raise_for_status()
        return HeartbeatResponse.model_validate(response.json())

    async def complete(
        self,
        job_id: uuid.UUID,
        report: CompletionRequest,
    ) -> bool:
        """
        Report how an attempt ended.

        :param job_id: Finished job.
        :type job_id: uuid.UUID
        :param report: Attempt number and outcome.
        :type report: CompletionRequest
        :return: False if the server refused it as stale (409).
        :rtype: bool
        :raises httpx.HTTPError: On network or other server errors.
        """
        response = await self.http.post(
            f"/api/agent/jobs/{job_id}/complete",
            json=report.model_dump(mode="json"),
        )
        if response.status_code == STALE:
            return False
        response.raise_for_status()
        return True

    async def close(self) -> None:
        """
        Close the underlying connections.
        """
        await self.http.aclose()
