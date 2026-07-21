from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer
from sqlalchemy import UniqueConstraint
from sqlalchemy import ForeignKey

class Base(DeclarativeBase):
    pass

class Stock(Base):
    __tablename__ = "stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_product: Mapped[int] = mapped_column(Integer, unique=False, nullable=False)
    id_branch: Mapped[int] = mapped_column(ForeignKey('branches.id'), unique=False, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('id_product', 'id_branch', name='unique_product_branch'),
    )