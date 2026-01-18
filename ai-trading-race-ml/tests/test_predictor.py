"""Tests for ML predictor and feature engineering."""

import numpy as np
import pandas as pd
import pytest

from app.ml.features import FEATURE_COLUMNS, engineer_features, get_feature_values
from app.ml.predictor import PredictedAction, TradingPredictor
from pathlib import Path


def create_sample_candles(n: int = 50) -> pd.DataFrame:
    """
    Create sample OHLCV data for testing.
    
    Uses daily frequency and enough rows to compute all technical indicators
    (need at least 21 for SMA_21, plus buffer for NaN dropping).
    """
    np.random.seed(42)
    base_price = 42000
    
    data = {
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="D"),
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
    }
    
    price = base_price
    for i in range(n):
        # Create realistic price movements
        change = np.random.uniform(-0.02, 0.02)
        open_price = price
        close_price = price * (1 + change)
        high_price = max(open_price, close_price) * (1 + np.random.uniform(0, 0.01))
        low_price = min(open_price, close_price) * (1 - np.random.uniform(0, 0.01))
        
        data["open"].append(open_price)
        data["high"].append(high_price)
        data["low"].append(low_price)
        data["close"].append(close_price)
        data["volume"].append(np.random.uniform(100, 1000))
        
        price = close_price
    
    return pd.DataFrame(data)


class TestFeatureEngineering:
    """Tests for feature engineering functions."""

    def test_engineer_features_returns_dataframe(self):
        """Test that engineer_features returns a DataFrame."""
        df = create_sample_candles()
        result = engineer_features(df)
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0

    def test_engineer_features_has_all_columns(self):
        """Test that all expected feature columns are present."""
        df = create_sample_candles()
        result = engineer_features(df)
        
        for col in FEATURE_COLUMNS:
            assert col in result.columns, f"Missing column: {col}"

    def test_engineer_features_drops_na(self):
        """Test that NaN values are dropped."""
        df = create_sample_candles()
        result = engineer_features(df)
        
        assert not result[FEATURE_COLUMNS].isna().any().any()

    def test_get_feature_values_returns_dict(self):
        """Test that get_feature_values returns a dictionary."""
        df = create_sample_candles()
        values = get_feature_values(df)
        
        assert isinstance(values, dict)
        assert "rsi_14" in values
        assert "macd" in values


class TestPredictor:
    """Tests for the TradingPredictor."""

    def test_predictor_without_model(self):
        """Test predictor falls back to rule-based when no model exists."""
        predictor = TradingPredictor(Path("/nonexistent/model.pkl"))
        
        assert not predictor.is_loaded

    def test_predict_returns_result(self):
        """Test that predict returns a valid result."""
        predictor = TradingPredictor(Path("/nonexistent/model.pkl"))
        
        df = create_sample_candles()
        from app.ml.features import prepare_inference_features
        features = prepare_inference_features(df)
        feature_values = get_feature_values(df)
        
        result = predictor.predict(features, feature_values)
        
        assert result.action in list(PredictedAction)
        assert 0 <= result.confidence <= 1
        assert isinstance(result.signals, list)

    def test_predict_generates_signals(self):
        """Test that predict generates explanation signals."""
        predictor = TradingPredictor(Path("/nonexistent/model.pkl"))
        
        df = create_sample_candles()
        from app.ml.features import prepare_inference_features
        features = prepare_inference_features(df)
        feature_values = get_feature_values(df)
        
        result = predictor.predict(features, feature_values)
        
        assert len(result.signals) > 0
        # Check signal structure
        signal = result.signals[0]
        assert "feature" in signal
        assert "value" in signal
        assert "rule" in signal
        assert "fired" in signal
        assert "contribution" in signal
