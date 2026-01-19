import type { Position } from '../types';
import './PositionCard.css';

interface PositionCardProps {
    position: Position;
    currentPrice?: number;
}

export function PositionCard({ position, currentPrice }: PositionCardProps) {
    const marketValue = currentPrice 
        ? position.quantity * currentPrice 
        : position.quantity * position.averagePrice;
    
    const costBasis = position.quantity * position.averagePrice;
    const unrealizedPnL = currentPrice 
        ? marketValue - costBasis 
        : 0;
    const pnlPercent = costBasis > 0 
        ? ((unrealizedPnL / costBasis) * 100) 
        : 0;

    return (
        <div className="position-card">
            <div className="position-header">
                <span className="position-asset">{position.asset}</span>
                <span className={`position-pnl ${unrealizedPnL >= 0 ? 'positive' : 'negative'}`}>
                    {unrealizedPnL >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
                </span>
            </div>

            <div className="position-body">
                <div className="position-stat">
                    <span className="stat-label">Quantity</span>
                    <span className="stat-value">{position.quantity.toFixed(6)}</span>
                </div>
                <div className="position-stat">
                    <span className="stat-label">Avg Entry</span>
                    <span className="stat-value">
                        ${position.averagePrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </span>
                </div>
                {currentPrice && (
                    <div className="position-stat">
                        <span className="stat-label">Current</span>
                        <span className="stat-value">
                            ${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </span>
                    </div>
                )}
            </div>

            <div className="position-footer">
                <div className="position-values">
                    <div className="value-item">
                        <span className="value-label">Cost Basis</span>
                        <span className="value-amount">
                            ${costBasis.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </span>
                    </div>
                    <div className="value-item">
                        <span className="value-label">Market Value</span>
                        <span className="value-amount market">
                            ${marketValue.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </span>
                    </div>
                </div>
                {unrealizedPnL !== 0 && (
                    <div className={`pnl-badge ${unrealizedPnL >= 0 ? 'positive' : 'negative'}`}>
                        {unrealizedPnL >= 0 ? '+' : ''}${unrealizedPnL.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </div>
                )}
            </div>
        </div>
    );
}
