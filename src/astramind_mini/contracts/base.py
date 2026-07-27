"""Shared validation primitives for thin-waist contracts."""

from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints

Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]
ContentHash = Annotated[
    str,
    StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$"),
]
Version = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]


class ContractModel(BaseModel):
    """Immutable strict base for public contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


__all__ = [
    "AwareDatetime",
    "ContentHash",
    "ContractModel",
    "Identifier",
    "Version",
]
