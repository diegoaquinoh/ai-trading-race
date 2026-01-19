import './LoadingSpinner.css';

interface LoadingSpinnerProps {
    size?: 'sm' | 'md' | 'lg';
    message?: string;
    fullPage?: boolean;
}

export function LoadingSpinner({ size = 'md', message, fullPage = false }: LoadingSpinnerProps) {
    const sizeClass = `spinner-${size}`;
    
    const content = (
        <div className={`loading-spinner ${sizeClass}`}>
            <div className="spinner-ring">
                <div></div>
                <div></div>
                <div></div>
                <div></div>
            </div>
            {message && <p className="spinner-message">{message}</p>}
        </div>
    );

    if (fullPage) {
        return <div className="loading-spinner-fullpage">{content}</div>;
    }

    return content;
}
