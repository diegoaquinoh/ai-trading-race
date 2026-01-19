import './RefreshIndicator.css';

interface RefreshIndicatorProps {
    lastUpdate: Date | null;
    isRefreshing?: boolean;
    nextRefreshIn?: number; // seconds
}

export function RefreshIndicator({ lastUpdate, isRefreshing, nextRefreshIn }: RefreshIndicatorProps) {
    const formatLastUpdate = (date: Date | null) => {
        if (!date) return 'Never';
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    };

    return (
        <div className={`refresh-indicator ${isRefreshing ? 'refreshing' : ''}`}>
            <div className="refresh-status">
                <span className={`refresh-dot ${isRefreshing ? 'pulse' : ''}`}></span>
                <span className="refresh-label">
                    {isRefreshing ? 'Updating...' : 'Live'}
                </span>
            </div>
            <div className="refresh-details">
                <span className="refresh-time">
                    Last update: {formatLastUpdate(lastUpdate)}
                </span>
                {nextRefreshIn !== undefined && !isRefreshing && (
                    <span className="refresh-countdown">
                        Next in {nextRefreshIn}s
                    </span>
                )}
            </div>
        </div>
    );
}
