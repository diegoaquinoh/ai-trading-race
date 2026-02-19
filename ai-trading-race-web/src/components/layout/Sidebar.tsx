import { Link, useLocation } from 'react-router-dom';
import './Sidebar.css';

interface SidebarProps {
    isOpen: boolean;
    onClose?: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
    const location = useLocation();

    const navItems = [
        { path: '/', icon: 'fas fa-chart-bar', label: 'Dashboard' },
        { path: '/agents', icon: 'fas fa-robot', label: 'Agents' },
        { path: '/about', icon: 'fas fa-info-circle', label: 'About' },
    ];

    return (
        <>
            {/* Backdrop for mobile */}
            {isOpen && <div className="sidebar-backdrop" onClick={onClose} />}
            
            <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
                <nav className="sidebar-nav">
                    <div className="nav-section">
                        <span className="nav-section-title">Menu</span>
                        {navItems.map(item => (
                            <Link
                                key={item.path}
                                to={item.path}
                                className={`sidebar-link ${location.pathname === item.path ? 'active' : ''}`}
                                onClick={onClose}
                            >
                                <span className="sidebar-link-icon"><i className={item.icon}></i></span>
                                <span className="sidebar-link-label">{item.label}</span>
                            </Link>
                        ))}
                    </div>

                    <div className="nav-section">
                        <span className="nav-section-title">Quick Stats</span>
                        <div className="sidebar-stats">
                            <div className="stat-item">
                                <span className="stat-label">Active Agents</span>
                                <span className="stat-value">3</span>
                            </div>
                            <div className="stat-item">
                                <span className="stat-label">Total Trades</span>
                                <span className="stat-value">142</span>
                            </div>
                        </div>
                    </div>
                </nav>

                <div className="sidebar-footer">
                    <div className="sidebar-version">
                        <span>v2.0.3</span>
                        <span className="version-env">Development</span>
                    </div>
                </div>
            </aside>
        </>
    );
}
