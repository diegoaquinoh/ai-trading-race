"""Helpers shared by the internal routers."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional, TypeVar

from fastapi import Response
from starlette.concurrency import run_in_threadpool

from research_engine.contracts.portfolio import PortfolioState

from .errors import conflict, not_found, unprocessable
from .wire import check_version, dumps, parse_model

T = TypeVar("T")

JSON_MEDIA = "application/json"


def json_response(payload: Any, status: int = 200, headers: Optional[dict] = None) -> Response:
    return Response(
        content=dumps(payload), status_code=status, media_type=JSON_MEDIA, headers=headers
    )


def raw_response(body: bytes, status: int = 200) -> Response:
    return Response(content=body, status_code=status, media_type=JSON_MEDIA)


async def in_threadpool(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Synchronous numerical work runs off the event loop. QuantLib settings are
    serialized inside the engine (``research_engine.pricing.quantlib_env``)."""
    return await run_in_threadpool(func, *args, **kwargs)


def verified_state(
    raw: Any, expected_hash: str, *, field: str = "portfolioState"
) -> PortfolioState:
    """Parse an inline portfolio state and bind it to the caller's hash (409 on mismatch)."""
    if not isinstance(raw, dict):
        raise unprocessable("invalid_request", f"{field} must be a JSON object")
    check_version(raw.get("schemaVersion"), f"{field}.schemaVersion")
    state = parse_model(PortfolioState, raw)
    actual = state.compute_hash()
    if actual != expected_hash:
        raise conflict(
            "state_hash_mismatch",
            f"{field} hash {actual} does not match the supplied hash {expected_hash}",
            extra={"computedHash": actual},
        )
    return state


def curve_or_404(market: Any, curve_snapshot_id: str) -> Any:
    try:
        return market.get_curve_snapshot(curve_snapshot_id)
    except KeyError as exc:
        raise not_found(
            "unknown_curve_snapshot", f"curve snapshot {curve_snapshot_id!r} does not exist"
        ) from exc


def require_ready_curve(snapshot: Any) -> None:
    if snapshot.status.value != "READY":
        raise conflict(
            "curve_not_ready",
            f"curve snapshot {snapshot.curve_snapshot_id} is {snapshot.status.value}: "
            + "; ".join(snapshot.failure_reasons),
        )


def universe_matches(market: Any, version: Optional[str]) -> bool:
    if version is None:
        return True
    contract = market.universe_contract
    return version in (contract.version, contract.universe_id)


def iso(day: Optional[date]) -> Optional[str]:
    return day.isoformat() if day else None


def page_bounds(page: int, page_size: int, max_size: int = 200) -> tuple[int, int]:
    if page < 1:
        raise unprocessable("invalid_request", "page must be >= 1")
    if not 1 <= page_size <= max_size:
        raise unprocessable("invalid_request", f"pageSize must be between 1 and {max_size}")
    start = (page - 1) * page_size
    return start, start + page_size
