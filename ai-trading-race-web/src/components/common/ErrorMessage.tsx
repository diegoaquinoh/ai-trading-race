import { Link } from 'react-router-dom';
import './ErrorMessage.css';

interface ErrorMessageProps {
    title?: string;
    message: string;
    retryAction?: () => void;
    backLink?: string;
    backLinkText?: string;
}

export function ErrorMessage({ 
    title = 'Something went wrong',
    message,
    retryAction,
    backLink,
    backLinkText = '← Go back'
}: ErrorMessageProps) {
    return (
        <div className="error-message">
            <div className="error-icon">⚠️</div>
            <h3 className="error-title">{title}</h3>
            <p className="error-text">{message}</p>
            <div className="error-actions">
                {retryAction && (
                    <button onClick={retryAction} className="error-btn retry">
                        Try Again
                    </button>
                )}
                {backLink && (
                    <Link to={backLink} className="error-btn back">
                        {backLinkText}
                    </Link>
                )}
            </div>
        </div>
    );
}
