"""Enums for the ML service API."""

from enum import Enum


class TradeSide(str, Enum):
    """Side of a trade order."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class SignalContribution(str, Enum):
    """Direction of a signal's contribution to the decision."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
