"""Shared validation defaults for external API models."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Reject extra fields and coercion, and prevent attribute reassignment."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True, strict=True)
