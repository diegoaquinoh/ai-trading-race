import { NavLink, Route, Routes } from 'react-router-dom';
import { EmptyState } from '../components/common';
import { CurveView } from './pages/CurveView';
import { DecisionPage } from './pages/DecisionPage';
import { EvidenceExplorer } from './pages/EvidenceExplorer';
import { ExperimentsOverview } from './pages/ExperimentsOverview';
import { HealthPage } from './pages/HealthPage';
import { InstrumentDetail } from './pages/InstrumentDetail';
import { InstrumentList } from './pages/InstrumentList';
import { PortfolioPage } from './pages/PortfolioPage';
import { ResearchPage } from './pages/ResearchPage';
import { RunDetail } from './pages/RunDetail';
import './fi.css';

const TABS = [
    { to: '/fi', label: 'Experiments', icon: 'fa-flask', end: true },
    { to: '/fi/instruments', label: 'Instruments', icon: 'fa-file-contract', end: false },
    { to: '/fi/evidence', label: 'Evidence', icon: 'fa-search', end: false },
    { to: '/fi/research', label: 'Research question', icon: 'fa-question-circle', end: false },
    { to: '/fi/health', label: 'Health', icon: 'fa-heartbeat', end: false },
];

/** Fixed income research lab: nested routes under /fi. */
export function FiApp() {
    return (
        <div className="fi-root">
            <nav className="fi-subnav" aria-label="Fixed income research lab">
                <span className="fi-subnav-title"><i className="fas fa-university"></i> Fixed income lab</span>
                {TABS.map(t => (
                    <NavLink key={t.to} to={t.to} end={t.end} className={({ isActive }) => `fi-subnav-link ${isActive ? 'active' : ''}`}>
                        <i className={`fas ${t.icon}`}></i> {t.label}
                    </NavLink>
                ))}
            </nav>
            <Routes>
                <Route index element={<ExperimentsOverview />} />
                <Route path="runs/:runId" element={<RunDetail />} />
                <Route path="instruments" element={<InstrumentList />} />
                <Route path="instruments/:securityId" element={<InstrumentDetail />} />
                <Route path="curves/:snapshotId" element={<CurveView />} />
                <Route path="portfolios/:portfolioId" element={<PortfolioPage />} />
                <Route path="decisions/:decisionId" element={<DecisionPage />} />
                <Route path="evidence" element={<EvidenceExplorer />} />
                <Route path="evidence/:bundleId" element={<EvidenceExplorer />} />
                <Route path="research" element={<ResearchPage />} />
                <Route path="health" element={<HealthPage />} />
                <Route path="*" element={<EmptyState icon="fa-map-signs" title="Page not found" message="This fixed income page does not exist." />} />
            </Routes>
        </div>
    );
}
