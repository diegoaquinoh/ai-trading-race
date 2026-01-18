import './StatCard.css';

interface StatCardProps {
    title: string;
    value: string | number;
    subtitle?: string;
    trend?: 'up' | 'down' | 'neutral';
    trendValue?: string;
    icon?: string;
}

export function StatCard({ title, value, subtitle, trend, trendValue, icon }: StatCardProps) {
    return (
        <div className="stat-card">
            <div className="stat-card-header">
                {icon && <span className="stat-card-icon">{icon}</span>}
                <span className="stat-card-title">{title}</span>
            </div>
            <div className="stat-card-value">{value}</div>
            {(trend || subtitle) && (
                <div className="stat-card-footer">
                    {trend && trendValue && (
                        <span className={`stat-card-trend ${trend}`}>
                            {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '•'} {trendValue}
                        </span>
                    )}
                    {subtitle && <span className="stat-card-subtitle">{subtitle}</span>}
                </div>
            )}
        </div>
    );
}
