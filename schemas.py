"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List

class Regulationdoc(BaseModel):
    """
    Technical regulations document that users can import/read.
    Collection name: "regulationdoc"
    """
    title: str = Field(..., description="Document title")
    source_url: str = Field(..., description="Source PDF URL")
    text: str = Field(..., description="Extracted plain text")

class Flashcard(BaseModel):
    """
    Flashcards generated from regulation text.
    Collection name: "flashcard"
    """
    doc_id: Optional[str] = Field(None, description="Related regulation document id")
    question: str = Field(..., description="Question prompt")
    answer: str = Field(..., description="Answer or explanation")
    tag: Optional[str] = Field(None, description="Optional category/tag")

class Inspiration(BaseModel):
    """
    Inspiration analyses about historical race cars (optional persistence).
    Collection name: "inspiration"
    """
    query: str
    car: str
    summary: str
    aero_highlights: List[str] = []
