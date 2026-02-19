"""Feature engineering for trading ML model.

Creates technical indicators from OHLCV candle data.
"""

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import BollingerBands


# Feature columns used by the model
FEATURE_COLUMNS = [
    "sma_7",
    "sma_21",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_diff",
    "bb_width",
    "returns_1",
    "returns_7",
    "volatility_7",
    "volume_ratio",
]


def engineer_features(candles_df: pd.DataFrame) -> pd.DataFrame:
    """
    Create technical indicators from OHLCV data.

    Args:
        candles_df: DataFrame with columns: open, high, low, close, volume

    Returns:
        DataFrame with additional feature columns (NaN rows dropped)
    """
    df = candles_df.copy()
    close = df["close"]
    n = len(df)

    # Moving averages
    df["sma_7"] = SMAIndicator(close, window=min(7, n)).sma_indicator()
    df["sma_21"] = SMAIndicator(close, window=min(21, n)).sma_indicator()

    # RSI (Relative Strength Index)
    df["rsi_14"] = RSIIndicator(close, window=min(14, max(2, n - 1))).rsi()

    # MACD (Moving Average Convergence Divergence)
    macd = MACD(close)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_diff"] = macd.macd_diff()

    # Bollinger Bands
    bb = BollingerBands(close)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / close

    # Price momentum (returns)
    df["returns_1"] = close.pct_change(1)
    df["returns_7"] = close.pct_change(min(7, n - 1)) if n > 1 else close.pct_change(1)

    # Volatility (rolling std of returns)
    df["volatility_7"] = df["returns_1"].rolling(min(7, n), min_periods=2).std()

    # Volume momentum
    df["volume_sma_7"] = df["volume"].rolling(min(7, n), min_periods=1).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma_7"]

    # Fill remaining NaNs with neutral defaults so we don't lose all rows
    df["rsi_14"] = df["rsi_14"].fillna(50.0)
    df["macd"] = df["macd"].fillna(0.0)
    df["macd_signal"] = df["macd_signal"].fillna(0.0)
    df["macd_diff"] = df["macd_diff"].fillna(0.0)
    df["bb_width"] = df["bb_width"].fillna(0.0)

    return df.dropna()


def prepare_inference_features(candles_df: pd.DataFrame) -> np.ndarray:
    """
    Prepare features for model inference (latest row only).

    Args:
        candles_df: DataFrame with OHLCV data

    Returns:
        numpy array of shape (1, n_features) for the latest candle
    """
    df = engineer_features(candles_df)
    if df.empty:
        raise ValueError("Not enough data to compute features")
    return df[FEATURE_COLUMNS].iloc[-1:].values


def get_feature_values(candles_df: pd.DataFrame) -> dict[str, float]:
    """
    Get the latest feature values as a dictionary.

    Useful for generating ExplanationSignals.

    Args:
        candles_df: DataFrame with OHLCV data

    Returns:
        Dictionary mapping feature name to value
    """
    df = engineer_features(candles_df)
    if df.empty:
        return {}
    latest = df[FEATURE_COLUMNS].iloc[-1]
    return latest.to_dict()
