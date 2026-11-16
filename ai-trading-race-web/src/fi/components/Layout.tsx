import { useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { DASH } from '../lib/format';

export function PageHeader({ title, icon, subtitle, children, breadcrumbs }: {
    title: ReactNode;
    icon: string;
    subtitle?: ReactNode;
    children?: ReactNode;
    breadcrumbs?: { to: string; label: string }[];
}) {
    return (
        <header className="fi-page-header">
            {breadcrumbs && breadcrumbs.length > 0 && (
                <nav className="fi-breadcrumbs" aria-label="Breadcrumb">
                    {breadcrumbs.map((b, i) => (
                        <span key={b.to}>
                            {i > 0 && <i className="fas fa-chevron-right"></i>}
                            <Link to={b.to}>{b.label}</Link>
                        </span>
                    ))}
                </nav>
            )}
            <div className="fi-page-header-row">
                <h1><i className={`fas ${icon}`}></i> {title}</h1>
                {children && <div className="fi-page-header-actions">{children}</div>}
            </div>
            {subtitle && <p className="fi-subtitle">{subtitle}</p>}
        </header>
    );
}

export function Panel({ title, icon, children, actions, id, className = '' }: {
    title: ReactNode;
    icon?: string;
    children: ReactNode;
    actions?: ReactNode;
    id?: string;
    className?: string;
}) {
    return (
        <section className={`fi-panel ${className}`} id={id}>
            <div className="fi-panel-header">
                <h2>{icon && <i className={`fas ${icon}`}></i>}{title}</h2>
                {actions && <div className="fi-panel-actions">{actions}</div>}
            </div>
            {children}
        </section>
    );
}

export interface KV {
    label: ReactNode;
    value: ReactNode;
    hint?: string;
}

export function KeyValueGrid({ items, columns = 3 }: { items: KV[]; columns?: 2 | 3 | 4 }) {
    return (
        <dl className={`fi-kv fi-kv-${columns}`}>
            {items.map((item, i) => (
                <div className="fi-kv-item" key={i} title={item.hint}>
                    <dt>{item.label}</dt>
                    <dd>{item.value === null || item.value === undefined || item.value === '' ? DASH : item.value}</dd>
                </div>
            ))}
        </dl>
    );
}

export function Notice({ tone = 'info', icon, children }: { tone?: 'info' | 'warn' | 'fail'; icon?: string; children: ReactNode }) {
    const defaultIcon = tone === 'info' ? 'fa-info-circle' : 'fa-exclamation-triangle';
    return (
        <div className={`fi-notice fi-notice-${tone}`} role={tone === 'info' ? 'note' : 'alert'}>
            <i className={`fas ${icon ?? defaultIcon}`}></i>
            <div>{children}</div>
        </div>
    );
}

/** Collapsible raw JSON for audit; closed by default. */
export function JsonDetails({ value, summary = 'Raw JSON', open = false }: { value: unknown; summary?: string; open?: boolean }) {
    const [isOpen, setOpen] = useState(open);
    if (value === undefined || value === null) return null;
    return (
        <details className="fi-json" open={isOpen} onToggle={e => setOpen((e.target as HTMLDetailsElement).open)}>
            <summary>{summary}</summary>
            {isOpen && <pre>{JSON.stringify(value, null, 2)}</pre>}
        </details>
    );
}

export function Mono({ children, title }: { children: ReactNode; title?: string }) {
    return <span className="mono fi-id" title={title}>{children}</span>;
}

export function IdList({ ids, empty = 'none' }: { ids: string[] | null | undefined; empty?: string }) {
    if (!ids || ids.length === 0) return <span className="fi-muted">{empty}</span>;
    return (
        <span className="fi-idlist">
            {ids.map(id => <code key={id} className="fi-code">{id}</code>)}
        </span>
    );
}

export function StringList({ items, empty = 'None recorded.' }: { items: string[] | null | undefined; empty?: string }) {
    if (!items || items.length === 0) return <p className="fi-muted-note">{empty}</p>;
    return (
        <ul className="fi-list">
            {items.map((item, i) => <li key={i}>{item}</li>)}
        </ul>
    );
}
