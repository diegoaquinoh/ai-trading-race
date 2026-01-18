"""Train the trading ML model and save it.

This script:
1. Generates synthetic training data
2. Trains a RandomForestClassifier
3. Evaluates performance
4. Saves the model to models/trading_model.pkl
"""

import sys
sys.path.insert(0, '.')

import joblib
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix

from scripts.generate_training_data import generate_training_dataset


def train_model(
    n_samples: int = 5000,
    test_size: float = 0.2,
    random_state: int = 42
) -> tuple[RandomForestClassifier, dict]:
    """
    Train a RandomForest classifier for trading decisions.
    
    Args:
        n_samples: Number of training samples to generate
        test_size: Fraction for test set
        random_state: Random seed
    
    Returns:
        Tuple of (trained model, metrics dict)
    """
    print("=" * 60)
    print("Trading ML Model Training")
    print("=" * 60)
    
    # Generate data
    print("\n1. Generating training data...")
    X, y = generate_training_dataset(n_samples=n_samples, seed=random_state)
    print(f"   Features: {X.shape[0]} samples, {X.shape[1]} features")
    print(f"   Label distribution: SELL={sum(y==0)}, HOLD={sum(y==1)}, BUY={sum(y==2)}")
    
    # Split data
    print("\n2. Splitting data...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )
    print(f"   Train: {len(X_train)}, Test: {len(X_test)}")
    
    # Train model
    print("\n3. Training RandomForest classifier...")
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=10,
        min_samples_leaf=5,
        class_weight='balanced',  # Handle class imbalance
        random_state=random_state,
        n_jobs=-1
    )
    model.fit(X_train, y_train)
    print("   Training complete!")
    
    # Evaluate
    print("\n4. Evaluating model...")
    y_pred = model.predict(X_test)
    
    # Cross-validation
    cv_scores = cross_val_score(model, X, y, cv=5, scoring='accuracy')
    
    # Metrics
    metrics = {
        'accuracy': (y_pred == y_test).mean(),
        'cv_mean': cv_scores.mean(),
        'cv_std': cv_scores.std(),
    }
    
    print(f"   Test Accuracy: {metrics['accuracy']:.3f}")
    print(f"   CV Accuracy: {metrics['cv_mean']:.3f} (+/- {metrics['cv_std']:.3f})")
    
    print("\n   Classification Report:")
    print(classification_report(y_test, y_pred, target_names=['SELL', 'HOLD', 'BUY']))
    
    print("   Confusion Matrix:")
    print(confusion_matrix(y_test, y_pred))
    
    # Feature importance
    print("\n5. Feature Importance:")
    importances = list(zip(X.columns, model.feature_importances_))
    importances.sort(key=lambda x: x[1], reverse=True)
    for feat, imp in importances[:5]:
        print(f"   {feat}: {imp:.3f}")
    
    return model, metrics


def save_model(model: RandomForestClassifier, path: str = "models/trading_model.pkl"):
    """Save trained model to disk."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    print(f"\n6. Model saved to: {path}")


if __name__ == "__main__":
    # Train model
    model, metrics = train_model(n_samples=5000)
    
    # Save model
    save_model(model)
    
    print("\n" + "=" * 60)
    print("Training Complete!")
    print("=" * 60)
    print(f"Model ready for use. Test accuracy: {metrics['accuracy']:.1%}")
