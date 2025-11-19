"""
Database Helper Functions

MongoDB helper functions ready to use in your backend code.
Import and use these functions in your API endpoints for database operations.
"""

from datetime import datetime, timezone
import os
from dotenv import load_dotenv
from typing import Union, Optional
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()

_client = None
db = None  # type: Optional[object]

# Lazy/defensive import of pymongo to avoid hard crashes if bson conflicts exist
try:
    from pymongo import MongoClient  # type: ignore
except Exception:
    MongoClient = None  # type: ignore


database_url = os.getenv("DATABASE_URL")
database_name = os.getenv("DATABASE_NAME")

try:
    if database_url and database_name and MongoClient is not None:
        _client = MongoClient(database_url)
        db = _client[database_name]
except Exception:
    # If anything goes wrong (e.g., bson conflict), leave db as None so the app can still boot
    db = None

# Helper functions for common database operations

def _ensure_db():
    if db is None:
        raise Exception("Database not available. Check DATABASE_URL/DATABASE_NAME or resolve MongoDB driver install.")


def create_document(collection_name: str, data: Union[BaseModel, dict]):
    """Insert a single document with timestamp"""
    _ensure_db()

    # Convert Pydantic model to dict if needed
    if isinstance(data, BaseModel):
        data_dict = data.model_dump()
    else:
        data_dict = data.copy()

    data_dict['created_at'] = datetime.now(timezone.utc)
    data_dict['updated_at'] = datetime.now(timezone.utc)

    result = db[collection_name].insert_one(data_dict)  # type: ignore
    return str(result.inserted_id)


def get_documents(collection_name: str, filter_dict: dict = None, limit: int = None):
    """Get documents from collection"""
    _ensure_db()
    cursor = db[collection_name].find((filter_dict or {}))  # type: ignore
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)
