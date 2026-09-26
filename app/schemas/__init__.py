"""Pydantic schemas, one module per resource."""

from app.schemas.common import (
    ErrorDetail,
    MessageResponse,
    ORMModel,
    Page,
    PageParams,
)

__all__ = ["ErrorDetail", "MessageResponse", "ORMModel", "Page", "PageParams"]
