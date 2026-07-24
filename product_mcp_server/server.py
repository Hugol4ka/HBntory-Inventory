import os
import httpx
from fastmcp import FastMCP

mcp = FastMCP("HBntory-Inventory")

BASE_URL = os.getenv("HBN_MCP_API_URL", "http://localhost:5001")


@mcp.tool()
async def list_products():
    """List all available products in the inventory."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/api/v1/products")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        return {
            "error": "Impossible to communicate with the external products API",
            "details": str(e),
        }


@mcp.tool()
async def get_product(product_id: str):
    """Get details for a specific product by its ID."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/api/v1/products/{product_id}"
            )

            if response.status_code == 404:
                return {"error": f"Product with ID '{product_id}' not found"}

            response.raise_for_status()
            return response.json()

    except httpx.HTTPError as e:
        return {
            "error": "Impossible to communicate with the external products API",
            "details": str(e),
        }


@mcp.tool()
async def get_quantity(product_id: str, branch: str | None = None):
    """Get the quantity of a specific product by its ID, optionally filtered by branch."""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{BASE_URL}/api/v1/products/{product_id}/quantity"
            params = {"branch": branch} if branch else {}

            response = await client.get(url, params=params)

            if response.status_code == 404:
                return {"error": f"Product with ID '{product_id}' not found"}

            response.raise_for_status()
            return response.json()

    except httpx.HTTPError as e:
        return {
            "error": "Impossible to communicate with the external products API",
            "details": str(e),
        }


if __name__ == "__main__":
    mcp.run(show_banner=False, log_level="ERROR")
