from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import config


class ProductMCPClient:
    """Client for interacting with the Product MCP Server."""

    def __init__(self):
        self.client_session = None
        self.exit_stack = AsyncExitStack()
        self.tools = []

    async def connect(self):
        """Connect to the product MCP server using stdio."""
        stdio_params = StdioServerParameters(
            command=config.MCP_SERVER_COMMAND,
            args=config.MCP_SERVER_ARGS,
        )

        read, write = await self.exit_stack.enter_async_context(stdio_client(stdio_params))
        self.client_session = await self.exit_stack.enter_async_context(ClientSession(read, write))

        await self.client_session.initialize()
        self.tools = await self.client_session.list_tools()

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
