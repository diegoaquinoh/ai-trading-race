import { Link, useLocation } from 'react-router-dom';
import './Header.css';

interface HeaderProps {
    onToggleSidebar?: () => void;
    sidebarOpen?: boolean;
}

export function Header({ onToggleSidebar, sidebarOpen }: HeaderProps) {
    const location = useLocation();

    return (
        <header className="header">
            <div className="header-left">
                {onToggleSidebar && (
                    <button 
                        className="sidebar-toggle"
                        onClick={onToggleSidebar}
                        aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
                    >
                        <span className="hamburger-icon">
                            <span></span>
                            <span></span>
                            <span></span>
                        </span>
                    </button>
                )}
                <Link to="/" className="header-logo">
                    <span className="logo-icon"><i className="fas fa-flag-checkered"></i></span>
                    <span className="logo-text">AI Trading Race</span>
                </Link>
            </div>

            <nav className="header-nav">
                <Link 
                    to="/" 
                    className={`nav-link ${location.pathname === '/' ? 'active' : ''}`}
                >
                    Dashboard
                </Link>
                <Link
                    to="/agents"
                    className={`nav-link ${location.pathname.startsWith('/agents') ? 'active' : ''}`}
                >
                    Agents
                </Link>
                <Link
                    to="/about"
                    className={`nav-link ${location.pathname === '/about' ? 'active' : ''}`}
                >
                    About
                </Link>
            </nav>

            <div className="header-right">
                <div className="header-status">
                    <span className="status-dot"></span>
                    <span className="status-text">Live</span>
                </div>
            </div>
        </header>
    );
}
