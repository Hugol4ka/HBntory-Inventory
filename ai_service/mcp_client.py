from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

import config


class ProductMCPClient:
    """Client for interacting with the Product MCP Server."""

    def __init__(self):
        self.client_session = None
        self.exit_stack = AsyncExitStack()
        self.tools = []

    async def connect(self):
        """Connect to the product MCP server over streamable HTTP."""
        read, write, _ = await self.exit_stack.enter_async_context(
            streamablehttp_client(config.MCP_SERVER_URL)
        )
        self.client_session = await self.exit_stack.enter_async_context(ClientSession(read, write))

        await self.client_session.initialize()
        listed = await self.client_session.list_tools()

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
        """Call a tool exposed by the product MCP server and return its result as text."""
        result = await self.client_session.call_tool(name, arguments)

        text_parts = []
        for content in result.content:
            if content.type == "text":
                text_parts.append(content.text)
        return "\n".join(text_parts)

    async def close(self):
        await self.exit_stack.aclose()
