"""Frozen runtime dependency identity for production training requests and manifests."""

from __future__ import annotations

from importlib.metadata import version

from ..contracts import DependencyVersion

_PACKAGES = ("duckdb", "numpy", "scikit-learn", "skops")


def production_dependencies() -> tuple[DependencyVersion, ...]:
    return tuple(
        DependencyVersion(package=package, version=version(package)) for package in _PACKAGES
    )


def production_dependency_identity() -> tuple[tuple[str, str], ...]:
    return tuple(
        (dependency.package, dependency.version) for dependency in production_dependencies()
    )


__all__ = ["production_dependencies", "production_dependency_identity"]
