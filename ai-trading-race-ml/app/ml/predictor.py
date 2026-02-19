"""ML Predictor with structured signal output for explainability.

Loads a trained model and generates predictions with explanations.
"""

from enum import IntEnum
from pathlib import Path
from typing import NamedTuple

import joblib
import numpy as np

from app.ml.features import FEATURE_COLUMNS
from app.models.enums import SignalContribution


class PredictedAction(IntEnum):
    """Model output classes."""

    SELL = 0
    HOLD = 1
    BUY = 2


class PredictionResult(NamedTuple):
    """Result of a prediction with explanation signals."""

    action: PredictedAction
    confidence: float
    signals: list[dict]  # List of signal dicts for ExplanationSignal


# Trading rules for signal generation
TRADING_RULES = {
    "rsi_14": [
        {"threshold": 40, "operator": "<", "contribution": SignalContribution.BULLISH, "rule": "<40 = oversold zone"},
        {"threshold": 60, "operator": ">", "contribution": SignalContribution.BEARISH, "rule": ">60 = overbought zone"},
    ],
    "macd_diff": [
        {"threshold": 0, "operator": ">", "contribution": SignalContribution.BULLISH, "rule": ">0 = bullish crossover"},
        {"threshold": 0, "operator": "<", "contribution": SignalContribution.BEARISH, "rule": "<0 = bearish crossover"},
    ],
    "returns_7": [
        {"threshold": 0.02, "operator": ">", "contribution": SignalContribution.BULLISH, "rule": ">2% = uptrend"},
        {"threshold": -0.02, "operator": "<", "contribution": SignalContribution.BEARISH, "rule": "<-2% = downtrend"},
    ],
    "bb_width": [
        {"threshold": 0.1, "operator": ">", "contribution": SignalContribution.NEUTRAL, "rule": ">10% = high volatility"},
    ],
    "returns_1": [
        {"threshold": 0.005, "operator": ">", "contribution": SignalContribution.BULLISH, "rule": ">0.5% = short-term momentum up"},
        {"threshold": -0.005, "operator": "<", "contribution": SignalContribution.BEARISH, "rule": "<-0.5% = short-term momentum down"},
    ],
}


class TradingPredictor:
    """Loads a trained model and generates predictions with explanations."""

    def __init__(self, model_path: Path):
        """Initialize the predictor.

        Args:
            model_path: Path to the saved model file (.pkl)
        """
        self.model = None
        self.model_path = model_path
        self._load_model()

    def _load_model(self) -> None:
        """Load the model from disk, or use rule-based fallback."""
        if self.model_path.exists():
            self.model = joblib.load(self.model_path)
        else:
            # Fallback to rule-based for development
            self.model = None

    def predict(self, features: np.ndarray, feature_values: dict[str, float]) -> PredictionResult:
        """
        Generate a prediction with explanation signals.

        Args:
            features: Feature array of shape (1, n_features)
            feature_values: Dictionary of feature name -> value for explanations

        Returns:
            PredictionResult with action, confidence, and explanation signals
        """
        # Generate explanation signals first (used by both paths)
        signals = self._generate_signals(feature_values)

        if self.model is None:
            # Rule-based fallback
            return self._rule_based_predict(feature_values, signals)

        # ML model prediction
        probas = self.model.predict_proba(features)[0]
        action = PredictedAction(int(np.argmax(probas)))
        confidence = float(np.max(probas))

        return PredictionResult(action=action, confidence=confidence, signals=signals)

    def _rule_based_predict(
        self, feature_values: dict[str, float], signals: list[dict]
    ) -> PredictionResult:
        """RSI + MACD based strategy as fallback."""
        rsi = feature_values.get("rsi_14", 50)
        macd_diff = feature_values.get("macd_diff", 0)

        # Count bullish/bearish signals
        bullish_count = sum(1 for s in signals if s["contribution"] == SignalContribution.BULLISH and s["fired"])
        bearish_count = sum(1 for s in signals if s["contribution"] == SignalContribution.BEARISH and s["fired"])

        # Strong signals: RSI extreme OR MACD crossover with confirming RSI direction
        if rsi < 35 or (rsi < 45 and macd_diff > 0):
            return PredictionResult(action=PredictedAction.BUY, confidence=0.7, signals=signals)
        elif rsi > 65 or (rsi > 55 and macd_diff < 0):
            return PredictionResult(action=PredictedAction.SELL, confidence=0.7, signals=signals)
        elif bullish_count > bearish_count:
            return PredictionResult(action=PredictedAction.BUY, confidence=0.55, signals=signals)
        elif bearish_count > bullish_count:
            return PredictionResult(action=PredictedAction.SELL, confidence=0.55, signals=signals)
        else:
            return PredictionResult(action=PredictedAction.HOLD, confidence=0.5, signals=signals)

    def _generate_signals(self, feature_values: dict[str, float]) -> list[dict]:
        """Generate explanation signals based on trading rules."""
        signals = []

        for feature, rules in TRADING_RULES.items():
            value = feature_values.get(feature)
            if value is None:
                continue

            for rule_def in rules:
                fired = self._check_rule(value, rule_def["threshold"], rule_def["operator"])
                signals.append({
                    "feature": feature,
                    "value": round(float(value), 4),
                    "rule": rule_def["rule"],
                    "fired": fired,
                    "contribution": rule_def["contribution"],
                })

        return signals

    def _check_rule(self, value: float, threshold: float, operator: str) -> bool:
        """Check if a rule condition is met."""
        if operator == ">":
            return value > threshold
        elif operator == "<":
            return value < threshold
        elif operator == ">=":
            return value >= threshold
        elif operator == "<=":
            return value <= threshold
        elif operator == "==":
            return value == threshold
        return False

    @property
    def is_loaded(self) -> bool:
        """Check if a trained model is loaded."""
        return self.model is not None
