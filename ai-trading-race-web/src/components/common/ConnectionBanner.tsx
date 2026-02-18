import { isNetworkError, getErrorMessage } from '../../services/errorUtils';
import './ConnectionBanner.css';

interface ConnectionBannerProps {
    /** The error object from react-query (or null if no error) */
    error: Error | null | undefined;
    /** Callback to retry fetching */
    onRetry?: () => void;
    /** Whether a refetch is currently in progress */
    isRetrying?: boolean;
}

/**
 * Non-blocking inline banner shown when the API is unreachable or returns an error.
 * Renders nothing when there is no error.
 */
export function ConnectionBanner({ error, onRetry, isRetrying }: ConnectionBannerProps) {
    if (!error) return null;

    const networkErr = isNetworkError(error);
    const message = getErrorMessage(error);

    return (
        <div className={`connection-banner ${networkErr ? 'network' : 'api'}`} role="alert">
            <div className="connection-banner-content">
                <span className="connection-banner-icon">
                    <i className={`fas ${networkErr ? 'fa-plug' : 'fa-exclamation-triangle'}`}></i>
                </span>
                <span className="connection-banner-text">
                    {message}
                    {networkErr && (
                        <span className="connection-banner-hint"> — showing placeholder data</span>
                    )}
                </span>
            </div>
            {onRetry && (
                <button 
                    className="connection-banner-retry" 
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
