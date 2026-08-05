from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SupportCategory = Literal["question", "bug", "data", "feature", "other"]
SupportStatus = Literal["open", "in_progress", "resolved"]


class SupportReplyCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class SupportTicketUpdate(BaseModel):
    status: SupportStatus


class SupportReplyOut(BaseModel):
    id: int
    author_id: int
    author_name: str | None
    author_email: str
    author_role: str
    body: str
    created_at: datetime


class SupportTicketOut(BaseModel):
    id: int
    created_by: int
    creator_name: str | None
    creator_email: str
    creator_role: str
    category: SupportCategory
    subject: str
    description: str
    status: SupportStatus
    screenshot_name: str | None
    has_screenshot: bool
    created_at: datetime
    updated_at: datetime
    replies: list[SupportReplyOut] = []
