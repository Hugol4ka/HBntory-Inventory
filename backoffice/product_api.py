import os
import requests

BASE_URL = os.getenv("HBN_BACKOFFICE_API_URL", "http://localhost:5001")


class ProductAPIError(Exception):
    """Raised when the external Product API is unreachable or returns an error."""
    pass

class ProductNotFoundError(Exception):
    """Raised when a product is not found in the external Product API."""
    pass


def list_products():
    """Fetch the product catalog from the external Product API."""
    url = f"{BASE_URL.rstrip('/')}/api/v1/products?limit=1000"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise ProductAPIError(f"Product API unavailable: {e}")


def get_product_details(product_id):
    """Fetch details for one product."""
    url = f"{BASE_URL.rstrip('/')}/api/v1/products/{product_id}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 404:
            raise ProductNotFoundError(f"Product with ID {product_id} not found.")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise ProductAPIError(f"Product API unavailable: {e}") 
