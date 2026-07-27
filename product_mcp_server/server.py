from mcp_instance import mcp
import tools.catalog
import tools.stock
import os

MCP_PORT = int(os.getenv("HBN_MCP_PORT", "5003"))

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=MCP_PORT,
        show_banner=False,
    )