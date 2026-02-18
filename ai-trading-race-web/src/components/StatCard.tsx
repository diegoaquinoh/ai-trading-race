import './StatCard.css';

interface StatCardProps {
    title: string;
    value: string | number;
    subtitle?: string;
    trend?: 'up' | 'down' | 'neutral';
    trendValue?: string;
    iconClass?: string;
}

export function StatCard({ title, value, subtitle, trend, trendValue, iconClass }: StatCardProps) {
    return (
        <div className="stat-card">
            <div className="stat-card-header">
                {iconClass && <span className="stat-card-icon"><i className={iconClass}></i></span>}
                <span className="stat-card-title">{title}</span>
            </div>
            <div className="stat-card-value">{value}</div>
            {(trend || subtitle) && (
                <div className="stat-card-footer">
                    {trend && trendValue && (
                        <span className={`stat-card-trend ${trend}`}>
                            <i className={`fas ${trend === 'up' ? 'fa-arrow-up' : trend === 'down' ? 'fa-arrow-down' : 'fa-minus'}`}></i> {trendValue}
                        </span>
                    )}
                    {subtitle && <span className="stat-card-subtitle">{subtitle}</span>}
                </div>
            )}
        </div>
    );
}
