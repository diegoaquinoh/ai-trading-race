"""Generate synthetic training data for the trading ML model.

Since we don't have real historical data yet, this script generates
realistic OHLCV data with known patterns for training.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def generate_ohlcv_data(
    n_samples: int = 5000,
    base_price: float = 42000,
    volatility: float = 0.02,
    seed: int = 42
) -> pd.DataFrame:
    """
    Generate realistic OHLCV price data with trends and patterns.
    
    Args:
        n_samples: Number of candles to generate
        base_price: Starting price
        volatility: Price volatility (0.02 = 2%)
        seed: Random seed for reproducibility
    
    Returns:
        DataFrame with OHLCV data
    """
    np.random.seed(seed)
    
    prices = [base_price]
    
    # Generate price with trends and mean reversion
    trend = 0
    for i in range(n_samples - 1):
        # Occasionally change trend
        if np.random.random() < 0.05:
            trend = np.random.uniform(-0.001, 0.001)
        
        # Random walk with trend
        change = np.random.normal(trend, volatility)
        new_price = prices[-1] * (1 + change)
        
        # Mean reversion
        if new_price > base_price * 1.5:
            new_price *= 0.995
        elif new_price < base_price * 0.5:
            new_price *= 1.005
        
        prices.append(max(new_price, base_price * 0.1))
    
    # Create OHLCV data
    data = []
    start_time = datetime(2024, 1, 1)
    
    for i, close in enumerate(prices):
        # Generate high/low/open relative to close
        high_offset = abs(np.random.normal(0, volatility * 0.5))
        low_offset = abs(np.random.normal(0, volatility * 0.5))
        open_offset = np.random.normal(0, volatility * 0.3)
        
        open_price = close * (1 + open_offset)
        high_price = max(close, open_price) * (1 + high_offset)
        low_price = min(close, open_price) * (1 - low_offset)
        volume = np.random.lognormal(10, 0.5)
        
        data.append({
            'timestamp': start_time + timedelta(hours=i),
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close,
            'volume': volume
        })
    
    return pd.DataFrame(data)


def create_labels(df: pd.DataFrame, threshold: float = 0.01) -> pd.Series:
    """
    Create labels based on future price movement.
    
    Labels:
    - 0: SELL (price drops > threshold)
    - 1: HOLD (price stable)
    - 2: BUY (price rises > threshold)
    
    Args:
        df: DataFrame with 'close' column
        threshold: Minimum % change to trigger BUY/SELL
    
    Returns:
        Series of labels
    """
    # Calculate future return (5 periods ahead)
    future_return = df['close'].shift(-5) / df['close'] - 1
    
    labels = pd.Series(1, index=df.index)  # Default: HOLD
    labels[future_return > threshold] = 2   # BUY
    labels[future_return < -threshold] = 0  # SELL
    
    return labels


def generate_training_dataset(
    n_samples: int = 5000,
    seed: int = 42
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Generate complete training dataset with features and labels.
    
    Returns:
        Tuple of (features DataFrame, labels Series)
    """
    # Generate OHLCV data
    df = generate_ohlcv_data(n_samples=n_samples, seed=seed)
    
    # Import feature engineering
    import sys
    sys.path.insert(0, '.')
    from app.ml.features import engineer_features, FEATURE_COLUMNS
    
    # Create features
    df_features = engineer_features(df)
    
    # Create labels
    labels = create_labels(df_features)
    
    # Remove last 5 rows (no future data for labels)
    df_features = df_features.iloc[:-5]
    labels = labels.iloc[:-5]
    
    # Select only feature columns
    X = df_features[FEATURE_COLUMNS]
    y = labels
    
    # Drop any remaining NaN
    mask = ~(X.isna().any(axis=1) | y.isna())
    X = X[mask]
    y = y[mask]
    
    return X, y


if __name__ == "__main__":
    print("Generating training data...")
    X, y = generate_training_dataset(n_samples=5000)
    
    print(f"Features shape: {X.shape}")
    print(f"Labels distribution:")
    print(y.value_counts().sort_index())
    print("\nSample features:")
    print(X.head())
