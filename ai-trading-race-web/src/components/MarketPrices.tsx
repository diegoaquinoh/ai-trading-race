import type { MarketPrice } from '../types';
import './MarketPrices.css';

interface MarketPricesProps {
    prices: MarketPrice[];
    isLoading?: boolean;
}

export function MarketPrices({ prices, isLoading }: MarketPricesProps) {
    if (isLoading) {
        return (
            <div className="market-prices">
                <div className="market-price-item skeleton">
                    <span className="skeleton-text"></span>
                </div>
                <div className="market-price-item skeleton">
                    <span className="skeleton-text"></span>
                </div>
            </div>
        );
    }

    return (
        <div className="market-prices">
            {prices.map(price => (
                <div key={price.symbol} className="market-price-item">
                    <div className="market-price-header">
                        <span className="market-price-symbol">{price.symbol}</span>
                        <span className="market-price-name">{price.name}</span>
                    </div>
                    <div className="market-price-value">
                        ${price.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div className={`market-price-change ${price.changePercent24h >= 0 ? 'positive' : 'negative'}`}>
                        {price.changePercent24h >= 0 ? '▲' : '▼'} {Math.abs(price.changePercent24h).toFixed(2)}%
                    </div>
                </div>
            ))}
            {prices.length === 0 && (
                <div className="market-prices-empty">
                    No price data
                </div>
            )}
        </div>
    );
}
