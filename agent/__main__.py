"""
Entry point: ``python -m agent``.

Needs ``ATOMFIELD_API_URL`` and ``ATOMFIELD_AGENT_TOKEN``; see
``agent.config`` for the optional settings.
"""

import asyncio
import logging
import signal

from agent.agent import Agent
from agent.client import AgentClient
from agent.config import AgentConfig
from agent.runner import ProcessRunner
from agent.state import StateFile


async def serve(config: AgentConfig) -> None:
    """
    Run an agent until SIGTERM or SIGINT.

    :param config: Agent settings.
    :type config: AgentConfig
    """
    client = AgentClient.connect(config.api_url, config.token)
    agent = Agent(config, client, ProcessRunner(), StateFile(config.state_file))
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signal_number, agent.request_stop)
    try:
        await agent.run()
    finally:
        await client.close()


def main() -> None:
    """
    Configure logging and run the agent.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(serve(AgentConfig.from_environment()))


if __name__ == "__main__":
    main()
