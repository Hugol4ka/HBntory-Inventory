from fastmcp import FastMCP
import httpx

mcp = FastMCP("HBntory-Iventory")

@mcp.tool()
async def list_products():
    """
    List all products
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://external-products-api:5000")
            response.raise_for_status() # Error if statut code are 4xx or 5xx
            return response.json()
    except httpx.RequestError as e:
        return {
            "error": "Impossible to communicate with the external products API",
            "details": str(e)
            }

@mcp.tool()
async def get_product(product_id: str):
    """
    Get details for a specific product by its ID
    """
    try:
        async with httpx.AsyncClient() as client:

            response = await client.get(f"http://external-products-api:5000/products/{product_id}")

            if response.status_code == 404:
                return {"error": f"Product with ID '{product_id}' not found"}

            response.raise_for_status()
            return response.json()

    except httpx.HTTPError as e:
        return {
            "error": "Impossible to communicate with the external products API",
            "details": str(e)
        }

if __name__ == "__main__":
    mcp.run()
