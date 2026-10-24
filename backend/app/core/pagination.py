"""Standardized pagination schemas and query parameter dependencies."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int = Field(ge=1, description="Current page number (1-indexed)")
    per_page: int = Field(ge=1, le=100, description="Items per page")
    total: int = Field(ge=0, description="Total number of items")
    total_pages: int = Field(ge=0, description="Total number of pages")


class PaginatedResponse[T](BaseModel):
    data: Sequence[T]
    meta: PaginationMeta


class PageParams:
    """Dependency for extracting page and per_page query parameters."""

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="Page number"),
        per_page: int = Query(default=20, ge=1, le=100, description="Page size"),
    ):
        self.page = page
        self.per_page = per_page

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    def make_response(self, items: Sequence[T], total: int) -> PaginatedResponse[T]:
        total_pages = math.ceil(total / self.per_page) if self.per_page > 0 else 0
        return PaginatedResponse(
            data=items,
            meta=PaginationMeta(
                page=self.page,
                per_page=self.per_page,
                total=total,
                total_pages=total_pages,
            ),
        )
