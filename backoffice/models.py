from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer
from sqlalchemy import UniqueConstraint
from sqlalchemy import ForeignKey
from datetime import datetime
from sqlalchemy import DateTime


class Base(DeclarativeBase):
    pass

class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(100), unique=False, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    branch_id: Mapped[int] = mapped_column(ForeignKey('branches.id'), unique=False, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class Stock(Base):
    __tablename__ = "stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_product: Mapped[int] = mapped_column(Integer, unique=False, nullable=False)
    id_branch: Mapped[int] = mapped_column(ForeignKey('branches.id'), unique=False, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('id_product', 'id_branch', name='unique_product_branch'),
    )
