import asyncio
import logging
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

import config


class ProductMCPClient:
    """Client for interacting with the Product MCP Server."""

    def __init__(self):
        self.client_session = None
        self.exit_stack = AsyncExitStack()
        self.tools = []

    async def connect(self, max_attempts=10, delay_seconds=2):
        """Connect to the product MCP server over streamable HTTP, retrying if it is not ready yet."""
        for attempt in range(1, max_attempts + 1):
            try:
                read, write, _ = await self.exit_stack.enter_async_context(
                    streamablehttp_client(config.MCP_SERVER_URL)
                )
                self.client_session = await self.exit_stack.enter_async_context(
                    ClientSession(read, write)
                )
                await self.client_session.initialize()
                listed = await self.client_session.list_tools()
                break
            except BaseException:
                try:
                    await self.exit_stack.aclose()
                except BaseException:
                    pass
                self.exit_stack = AsyncExitStack()
                self.client_session = None
                if attempt == max_attempts:
                    raise
                await asyncio.sleep(delay_seconds)

        converted_tools = []
        for tool in listed.tools:
            converted_tool = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            converted_tools.append(converted_tool)
        self.tools = converted_tools

    async def call_tool(self, name, arguments):
        """Call a tool exposed by the product MCP server and return its result as text.
        Reconnects once if the MCP session has been terminated (e.g. server restart)."""
        try:
            result = await self.client_session.call_tool(name, arguments)
        except Exception:
            logging.warning("MCP session lost, reconnecting...")
            try:
                await self.exit_stack.aclose()
            except BaseException:
                pass
            self.exit_stack = AsyncExitStack()
            self.client_session = None
            await self.connect()
            result = await self.client_session.call_tool(name, arguments)

        text_parts = []
        for content in result.content:
            if content.type == "text":
                text_parts.append(content.text)
        return "\n".join(text_parts)

    async def close(self):
        await self.exit_stack.aclose()
