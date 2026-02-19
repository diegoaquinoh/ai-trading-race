"""Decision service that orchestrates ML predictions.

Converts market data to features, runs prediction, and generates trading decisions.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pandas as pd

from app.config import settings
from app.ml.features import get_feature_values, prepare_inference_features
from app.ml.predictor import PredictedAction, TradingPredictor
from app.models.enums import TradeSide
from app.models.schemas import (
    AgentContextRequest,
    AgentDecisionResponse,
    CandleData,
    ExplanationSignal,
    TradeOrderResponse,
)


class DecisionService:
    """Orchestrates the ML prediction pipeline."""

    def __init__(self, predictor: TradingPredictor):
        """Initialize with a predictor instance.

        Args:
            predictor: The ML predictor to use for decisions
        """
        self.predictor = predictor

    def generate_decision(self, context: AgentContextRequest) -> AgentDecisionResponse:
        """
        Generate a trading decision from the agent context.

        Args:
            context: Request with portfolio state and market candles

        Returns:
            AgentDecisionResponse with orders and explanation signals
        """
        orders: list[TradeOrderResponse] = []
        all_signals: list[ExplanationSignal] = []
        reasoning_parts: list[str] = []

        # Process each asset (BTC, ETH)
        for symbol in ["BTC", "ETH"]:
            symbol_candles = [c for c in context.candles if c.symbol == symbol]

            if len(symbol_candles) < 7:
                # Not enough data for basic indicators
                continue

            # Convert to DataFrame
            df = self._candles_to_dataframe(symbol_candles)

            try:
                # Get features
                features = prepare_inference_features(df)
                feature_values = get_feature_values(df)
            except ValueError:
                # Skip if feature computation fails
                continue

            # Run prediction
            result = self.predictor.predict(features, feature_values)

            # Convert signals to schema objects
            signals = [
                ExplanationSignal(
                    feature=s["feature"],
                    value=s["value"],
                    rule=s["rule"],
                    fired=s["fired"],
                    contribution=s["contribution"],
                )
                for s in result.signals
            ]
            all_signals.extend(signals)

            # Generate order if not HOLD
            if result.action != PredictedAction.HOLD:
                order = self._create_order(result.action, result.confidence, symbol, context)
                if order:
                    orders.append(order)
                    reasoning_parts.append(
                        f"{symbol}: {result.action.name} (confidence: {result.confidence:.0%})"
                    )

        # Build response
        return AgentDecisionResponse(
            request_id=context.request_id,
            agent_id=context.agent_id,
            created_at=datetime.now(timezone.utc),
            orders=orders,
            signals=all_signals,
            reasoning="; ".join(reasoning_parts) if reasoning_parts else "No trading signals",
        )

    def _candles_to_dataframe(self, candles: list[CandleData]) -> pd.DataFrame:
        """Convert candle data to pandas DataFrame."""
        data = [
            {
                "timestamp": c.timestamp,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            }
            for c in candles
        ]
        return pd.DataFrame(data).sort_values("timestamp")

    def _create_order(
        self,
        action: PredictedAction,
        confidence: float,
        symbol: str,
        context: AgentContextRequest,
    ) -> Optional[TradeOrderResponse]:
        """Create a trade order based on prediction."""
        # Calculate position size based on confidence
        base_size = Decimal("0.1")  # 10% of portfolio
        size_multiplier = Decimal(str(min(confidence, 0.9)))

        portfolio_value = context.portfolio.total_value
        trade_value = portfolio_value * base_size * size_multiplier

        # Get current price from latest candle
        latest_candle = next(
            (c for c in reversed(context.candles) if c.symbol == symbol),
            None,
        )
        if not latest_candle:
            return None

        current_price = latest_candle.close
        if current_price <= 0:
            return None

        quantity = trade_value / current_price

        # Ensure minimum quantity
        if quantity < Decimal("0.00001"):
            return None

        return TradeOrderResponse(
            asset_symbol=symbol,
            side=TradeSide.BUY if action == PredictedAction.BUY else TradeSide.SELL,
            quantity=quantity.quantize(Decimal("0.00000001")),
            limit_price=None,
        )
