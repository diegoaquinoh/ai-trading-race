import './Footer.css';

export function Footer() {
    const currentYear = new Date().getFullYear();

    return (
        <footer className="footer">
            <div className="footer-content">
                <div className="footer-left">
                    <span className="footer-brand">AI Trading Race</span>
                    <span className="footer-separator">•</span>
                    <span className="footer-copyright">© {currentYear} Academic Project</span>
                </div>
                <div className="footer-right">
                    <span className="footer-status">
                        <span className="status-dot"></span>
                        All systems operational
                    </span>
                </div>
            </div>
        </footer>
    );
}
