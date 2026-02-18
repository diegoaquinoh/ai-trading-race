import './ServerUnavailable.css';

interface ServerUnavailableProps {
    /** Custom title (default: "Server Unavailable") */
    title?: string;
    /** Custom message */
    message?: string;
    /** Retry callback */
    onRetry?: () => void;
    /** Whether a retry is currently in progress */
    isRetrying?: boolean;
}

/**
 * Full-section error state shown in production when the backend is unreachable.
 * In dev mode, placeholder data is rendered instead — this component should only
 * be used in production builds.
 */
export function ServerUnavailable({
    title = 'Server Unavailable',
    message = 'We couldn\'t reach the server. Please try again in a moment.',
    onRetry,
    isRetrying,
}: ServerUnavailableProps) {
    return (
        <div className="server-unavailable" role="alert">
            <div className="server-unavailable-icon">
                <i className="fas fa-server"></i>
            </div>
            <h2 className="server-unavailable-title">{title}</h2>
            <p className="server-unavailable-message">{message}</p>
            {onRetry && (
                <button
                    className="server-unavailable-retry"
                    onClick={onRetry}
                    disabled={isRetrying}
                >
                    {isRetrying ? (
                        <><i className="fas fa-spinner fa-spin"></i> Retrying…</>
                    ) : (
                        <><i className="fas fa-redo"></i> Retry</>
                    )}
                </button>
            )}
        </div>
    );
}
