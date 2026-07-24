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
async def get_stock_by_product(product_id: int):
    """Get stock quantities for a specific product across all branches."""
    try:
        with Session(engine) as session: 
            results = (
                session.query(Stock, Branch)
                .join(Branch, Stock.id_branch == Branch.id)
                .filter(Stock.id_product == product_id)
                .all()
            )

            stock_list = [
                {"branch_id": branch.id, "branch_name": branch.name, "quantity": stock.quantity}
                for stock, branch in results
            ]
        return {"product_id": product_id, "stock": stock_list}
    
    except SQLAlchemyError as e:
        return {
            "error": "Impossible to communicate with the database",
            "details": str(e),
        }

@mcp.tool()
async def get_stock_by_branch(branch_id: int):
    """Get stock quantities for all products in a specific branch."""
    try:
        with Session(engine) as session:
            results = (
                session.query(Stock)
                .filter(Stock.id_branch == branch_id)
                .all()
            )

            stock_list = [
                {"product_id": stock.id_product, "quantity": stock.quantity}
                for stock in results
            ]
        return {"branch_id": branch_id, "stock": stock_list}

    except SQLAlchemyError as e:
        return {
            "error": "Impossible to communicate with the database",
            "details": str(e),
        }

def _has_enough_stock(session, branch_id, product_id, quantity_needed):
    """Check if a branch has enough stock for a specific product."""
    stock = (
        session.query(Stock)
        .filter(Stock.id_branch == branch_id, Stock.id_product == product_id)
        .first()
    )
    if stock is None:
        return (f"Product {product_id} is not available at branch {branch_id}.", False)

    if stock.quantity < quantity_needed:
        return (
            f"Product {product_id} has only {stock.quantity} in stock at branch {branch_id}, but {quantity_needed} were requested.",
            False,
        )

    return (None, True)

@mcp.tool()
async def check_shopping_list(items: list[dict]):
    """Check which branches can fully satisfy a list of desired products and quantities.
    Each item must have 'product_id' and 'quantity' keys."""
    try:
        with Session(engine) as session:
            branches = session.query(Branch).all()

            feasible_branches = []
            details = {}

            for branch in branches:
                issues = []

                for item in items:
                    message, is_sufficient = _has_enough_stock(session, branch.id, item["product_id"], item["quantity"])
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