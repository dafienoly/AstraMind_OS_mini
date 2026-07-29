"""Read-only account, authorization, and quote preflight for the Paper canary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from astramind_mini.config import Settings
from astramind_mini.paper_runtime_composition import fresh_startup, quote_reader
from astramind_mini.trading_execution.adapters.miniqmt_account import MiniQMTAccountError
from astramind_mini.trading_execution.adapters.miniqmt_canary_quote import (
    CanaryQuote,
    MiniQMTCanaryQuoteReader,
)
from astramind_mini.trading_execution.adapters.paper_runtime_store import PaperRuntimeStore
from astramind_mini.trading_execution.application.paper_startup import PaperStartupPublication

_MAX_QUOTE_AGE_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class PaperCanaryPreflightResult:
    authorization_id: str
    account_baseline_id: str
    instrument_id: str
    window_state: str
    quote_market_time: datetime
    quote_received_at: datetime
    quote_age_seconds: float
    broker_write_attempts: int = 0
    proposal_count_delta: int = 0
    order_intent_count_delta: int = 0


class PaperCanaryPreflight:
    def __init__(
        self,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
        startup: Callable[[Settings], Awaitable[PaperStartupPublication]] = fresh_startup,
        quotes: Callable[[Settings], MiniQMTCanaryQuoteReader] = quote_reader,
    ) -> None:
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(UTC))
        self._startup = startup
        self._quotes = quotes
        self._runtime = PaperRuntimeStore(settings.shadow_db_path)

    async def run(self) -> PaperCanaryPreflightResult:
        authorization = self._runtime.authorization()
        now = self._clock()
        if now > authorization.submission_window_end:
            raise MiniQMTAccountError("paper_authorization_expired")
        publication = await self._startup(self._settings)
        baseline = publication.account_baseline
        if baseline.open_order_fingerprints:
            raise MiniQMTAccountError("unexpected_open_orders")
        quote = await self._quotes(self._settings).read(authorization.instrument_id)
        self._validate_quote(quote)
        window_state = (
            "open"
            if authorization.submission_window_start <= now <= authorization.submission_window_end
            else "upcoming"
        )
        return PaperCanaryPreflightResult(
            authorization_id=authorization.authorization_id,
            account_baseline_id=baseline.baseline_id,
            instrument_id=authorization.instrument_id,
            window_state=window_state,
            quote_market_time=quote.market_time,
            quote_received_at=quote.received_at,
            quote_age_seconds=(quote.received_at - quote.market_time).total_seconds(),
        )

    @staticmethod
    def _validate_quote(quote: CanaryQuote) -> None:
        age = (quote.received_at - quote.market_time).total_seconds()
        if age < 0 or age > _MAX_QUOTE_AGE_SECONDS:
            raise MiniQMTAccountError("canary_quote_stale")
        if not quote.tradable:
            raise MiniQMTAccountError("canary_instrument_not_tradable")


__all__ = ["PaperCanaryPreflight", "PaperCanaryPreflightResult"]
