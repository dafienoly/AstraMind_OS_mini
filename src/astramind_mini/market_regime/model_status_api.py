"""FastAPI registration for read-only market-model status."""

from pathlib import Path

from fastapi import FastAPI

from astramind_mini.strategy_research.public import (
    MarketModelIntegrityVerifier,
    ModelActivationStore,
)

from .adapters.model_status import MarketModelStatusReader
from .contracts.model_status import MarketModelStatusProjection


def register_market_model_status_route(app: FastAPI, root: Path) -> None:
    verifier = MarketModelIntegrityVerifier(root)
    reader = MarketModelStatusReader(
        ModelActivationStore(root / "activations"),
        integrity_check=verifier.verify,
    )

    @app.get(
        "/api/market/model-status",
        response_model=MarketModelStatusProjection,
    )
    def market_model_status() -> MarketModelStatusProjection:
        return reader.current()


__all__ = ["register_market_model_status_route"]
