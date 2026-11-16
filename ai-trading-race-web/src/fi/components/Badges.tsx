import type { ReactNode } from 'react';
import { humanize } from '../lib/format';
import { kindMeta, outcomeMeta } from '../lib/domain';

export function DataModeBadge({ mode, label }: { mode: string; label?: string }) {
    const synthetic = mode === 'synthetic_curve';
    return (
        <span
            className={`fi-badge ${synthetic ? 'fi-badge-synthetic' : 'fi-badge-observed'}`}
            title={label ?? (synthetic ? 'Synthetic curve simulation: model prices, not market quotes' : 'Observed-security paper trading')}
        >
            <i className={`fas ${synthetic ? 'fa-flask' : 'fa-eye'}`}></i>
            {synthetic ? 'Synthetic curve' : mode === 'observed_security' ? 'Observed security' : humanize(mode)}
        </span>
    );
}

/** Persistent label for hypothetical instruments; never removed or hidden. */
export function SyntheticBadge({ large = false }: { large?: boolean }) {
    return (
        <span className={`fi-badge fi-badge-synthetic fi-badge-strong ${large ? 'fi-badge-lg' : ''}`}
            title="Hypothetical instrument with internal identifier; it does not represent an actual security.">
            <i className="fas fa-flask"></i> SYNTHETIC
        </span>
    );
}

export function OutcomeBadge({ outcome, compact = false }: { outcome: string; compact?: boolean }) {
    const meta = outcomeMeta(outcome);
    return (
        <span className={`fi-outcome fi-outcome-${outcome}`} title={`${outcome}: ${meta.financial}`}>
            <i className={`fas ${meta.icon}`}></i>
            {!compact && <span>{meta.label}</span>}
        </span>
    );
}

export function JobStateBadge({ state }: { state: string }) {
    const icons: Record<string, string> = {
        queued: 'fa-clock',
        running: 'fa-spinner fa-spin',
        completed: 'fa-check',
        failed: 'fa-times',
        cancelled: 'fa-ban',
    };
    return (
        <span className={`fi-job fi-job-${state}`} title={`Job lifecycle state (separate from strategy outcomes): ${state}`}>
            <i className={`fas ${icons[state] ?? 'fa-circle'}`}></i> {state}
        </span>
    );
}

export function ResponseModeBadge({ mode }: { mode: string }) {
    const recorded = mode === 'recorded_replay';
    return (
        <span className={`fi-badge ${recorded ? 'fi-badge-recorded' : 'fi-badge-fresh'}`}
            title={recorded ? 'Recorded responses replayed; no new model calls' : 'Fresh model inference'}>
            <i className={`fas ${recorded ? 'fa-compact-disc' : 'fa-bolt'}`}></i>
            {recorded ? 'Recorded replay' : mode === 'fresh_inference' ? 'Fresh inference' : humanize(mode)}
        </span>
    );
}

export function ChannelBadge({ channel }: { channel: string }) {
    const icons: Record<string, string> = { lexical: 'fa-font', vector: 'fa-vector-square', graph: 'fa-project-diagram' };
    return (
        <span className={`fi-channel fi-channel-${channel}`} title={`Retrieved through the ${channel} channel`}>
            <i className={`fas ${icons[channel] ?? 'fa-search'}`}></i> {channel}
        </span>
    );
}

export function KindBadge({ kind }: { kind: string | null | undefined }) {
    return <span className={`fi-kind fi-kind-${kind ?? 'unknown'}`}>{kindMeta(kind).label}</span>;
}

/**
 * Labels the provenance of a number. A curve-model price is never shown without
 * this tag, so it cannot be mistaken for a market quote.
 */
export function ValueKindTag({ kind }: { kind: 'model' | 'quote' | 'calculated' | 'graph' }) {
    const text: Record<string, [string, string, string]> = {
        model: ['Curve model', 'fa-calculator', 'Computed from a curve and pricing model; not a market quote'],
        quote: ['Observed quote', 'fa-eye', 'Admitted security quote with type and timestamp'],
        calculated: ['Calculated, not a graph fact', 'fa-calculator', 'Joined from the valuation engine; not stored in the knowledge graph'],
        graph: ['Graph fact', 'fa-project-diagram', 'Assertion stored in the knowledge graph with supporting spans'],
    };
    const [label, icon, title] = text[kind];
    return (
        <span className={`fi-valuekind fi-valuekind-${kind}`} title={title}>
            <i className={`fas ${icon}`}></i> {label}
        </span>
    );
}

export function PassFail({ passed, label }: { passed: boolean | null | undefined; label?: string }) {
    if (passed === null || passed === undefined) {
        return <span className="fi-passfail fi-passfail-na"><i className="fas fa-minus"></i> {label ?? 'n/a'}</span>;
    }
    return (
        <span className={`fi-passfail ${passed ? 'fi-passfail-pass' : 'fi-passfail-fail'}`}>
            <i className={`fas ${passed ? 'fa-check' : 'fa-times'}`}></i> {label ?? (passed ? 'pass' : 'fail')}
        </span>
    );
}

export function Tag({ children, tone = 'neutral', title }: { children: ReactNode; tone?: 'neutral' | 'warn' | 'fail' | 'ok' | 'muted'; title?: string }) {
    return <span className={`fi-tag fi-tag-${tone}`} title={title}>{children}</span>;
}
