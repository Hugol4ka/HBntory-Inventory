from mcp_instance import mcp
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from database import engine
from models import Branch, Stock


@mcp.tool()
async def list_branches():
    """List all available branches in the inventory."""
    try:
        with Session(engine) as session:
            branches = session.query(Branch).all()
            return [{"id": b.id, "name": b.name} for b in branches]
    except SQLAlchemyError as e:
        return {
            "error": "Impossible to communicate with the database",
            "details": str(e),
        }

@mcp.tool()
async def get_stock_by_product(sku: str):
    """Given a product SKU, list every branch that stocks it, with quantities.
    Answers "where can I find product X?". Example: sku="HB-LAP-1001"."""
    try:
        with Session(engine) as session:
            results = (
                session.query(Stock, Branch)
                .join(Branch, Stock.id_branch == Branch.id)
                .filter(Stock.id_product == sku)
                .all()
            )

            stock_list = [
                {"branch_id": branch.id, "branch_name": branch.name, "quantity": stock.quantity}
                for stock, branch in results
            ]
        return {"sku": sku, "stock": stock_list}

    except SQLAlchemyError as e:
        return {
            "error": "Impossible to communicate with the database",
            "details": str(e),
        }

@mcp.tool()
async def get_stock_by_branch(branch_id: int):
    """Given a branch ID, list every product stocked in that branch, with quantities.
    Answers "what is available at branch X?". Example: branch_id=1."""
    try:
        with Session(engine) as session:
            results = (
                session.query(Stock)
                .filter(Stock.id_branch == branch_id)
                .all()
            )

            stock_list = [
                {"sku": stock.id_product, "quantity": stock.quantity}
                for stock in results
            ]
        return {"branch_id": branch_id, "stock": stock_list}

    except SQLAlchemyError as e:
        return {
            "error": "Impossible to communicate with the database",
            "details": str(e),
        }

def _has_enough_stock(session, branch_id, sku, quantity_needed):
    """Check if a branch has enough stock for a specific product SKU."""
    stock = (
        session.query(Stock)
        .filter(Stock.id_branch == branch_id, Stock.id_product == sku)
        .first()
    )
    if stock is None:
        return (f"Product {sku} is not available at branch {branch_id}.", False)

    if stock.quantity < quantity_needed:
        return (
            f"Product {sku} has only {stock.quantity} in stock at branch {branch_id}, but {quantity_needed} were requested.",
            False,
        )

    return (None, True)

@mcp.tool()
async def check_shopping_list(items: list[dict]):
    """Check which branches can fully satisfy a shopping list.
    Each item must have a 'sku' key (string, e.g. "HB-LAP-1001") and a 'quantity' key (integer).
    Example: items=[{"sku": "HB-LAP-1001", "quantity": 5}]."""
    try:
        with Session(engine) as session:
            branches = session.query(Branch).all()

            feasible_branches = []
            details = {}

            for branch in branches:
                issues = []

                for item in items:
                    sku = item.get("sku") or item.get("product_id")
                    if sku is None:
                        issues.append("An item is missing a 'sku' field.")
                        continue

                    message, is_sufficient = _has_enough_stock(
                        session, branch.id, sku, item["quantity"]
                    )
                    if not is_sufficient:
                        issues.append(message)

                branch_ok = (len(issues) == 0)
                details[branch.name] = {"ok": branch_ok, "issues": issues}
                if branch_ok:
                    feasible_branches.append(branch.name)

        return {"feasible_branches": feasible_branches, "details": details}

    except SQLAlchemyError as e:
        return {
            "error": "Impossible to communicate with the database",
            "details": str(e),
        }
