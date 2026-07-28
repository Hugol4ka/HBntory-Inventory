from mcp_instance import mcp
import httpx
import os


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
    """Get details for a specific product by its numeric ID (e.g. "1") or its SKU (e.g. "HB-LAP-1001"). Always pass the value as a string."""
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
