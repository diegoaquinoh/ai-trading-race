import './EmptyState.css';

interface EmptyStateProps {
    icon?: string;
    title: string;
    message: string;
    action?: {
        label: string;
        onClick: () => void;
    };
}

export function EmptyState({ 
    icon = '📭',
    title,
    message,
    action
}: EmptyStateProps) {
    return (
        <div className="empty-state">
            <div className="empty-icon">{icon}</div>
            <h3 className="empty-title">{title}</h3>
            <p className="empty-message">{message}</p>
            {action && (
                <button onClick={action.onClick} className="empty-action">
                    {action.label}
                </button>
            )}
        </div>
    );
}
