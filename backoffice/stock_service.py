from models import Stock

def remove_stock(session, stock_item, quantity_to_remove):
    """
    Remove a specified quantity from a stock item.

    Args:
        session: The SQLAlchemy session to use for database operations.
        stock_item: The Stock object from which to remove the quantity.
        quantity_to_remove: The quantity to remove from the stock item.
    """
    if not isinstance(quantity_to_remove, int) or quantity_to_remove <= 0:
        raise ValueError("Quantity to remove must be a positive integer.")
    if stock_item.quantity < quantity_to_remove:
        raise ValueError(f"Cannot remove {quantity_to_remove} from stock item with only {stock_item.quantity} available.")
    stock_item.quantity -= quantity_to_remove
    session.commit()


def add_stock(session, stock_item, quantity_to_add):
    """
    Add a specified quantity to a stock item.

    Args:
        session: The SQLAlchemy session to use for database operations.
        stock_item: The Stock object to which to add the quantity.
        quantity_to_add: The quantity to add to the stock item.
    """
    if not isinstance(quantity_to_add, int) or quantity_to_add <= 0:
        raise ValueError("Quantity to add must be a positive integer.")
    stock_item.quantity += quantity_to_add
    session.commit()


def get_quantity_of_product_in_branch(session, id_product, id_branch):
    """
    Get the quantity of a specific product in a specific branch.

    Args:
        session: The SQLAlchemy session to use for database operations.
        id_product: The ID of the product to check.
        id_branch: The ID of the branch to check.
    """
    stock_item = session.query(Stock).filter_by(id_product=id_product, id_branch=id_branch).first()
    return stock_item.quantity if stock_item else 0
