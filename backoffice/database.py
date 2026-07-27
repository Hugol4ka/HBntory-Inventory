from sqlalchemy import create_engine
import os
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://devuser:devpassword@localhost:5432/inventory")
engine = create_engine(DATABASE_URL)