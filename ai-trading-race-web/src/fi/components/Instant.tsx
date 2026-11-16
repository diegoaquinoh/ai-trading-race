import { DASH, ZONE_LOCAL, ZONE_MARKET, ZONE_UTC, fmtInstantIn } from '../lib/format';

type Context = 'market' | 'operational';

interface InstantProps {
    value: string | null | undefined;
    /**
     * market: U.S. market / simulation events keep the America/New_York label.
     * operational: platform processing time, shown with the user's Europe/Madrid time.
     */
    context?: Context;
    inline?: boolean;
}

/** UTC instant with an explicitly labelled secondary zone. */
export function Instant({ value, context = 'operational', inline = false }: InstantProps) {
    if (!value) return <span className="fi-muted">{DASH}</span>;
    const utc = fmtInstantIn(value, ZONE_UTC);
    const secondaryZone = context === 'market' ? ZONE_MARKET : ZONE_LOCAL;
    const secondary = fmtInstantIn(value, secondaryZone);
    const secondaryLabel = context === 'market' ? 'New York, US market' : 'Madrid, your local time';
    const title = `${utc}\n${fmtInstantIn(value, ZONE_MARKET)} (New York, US market)\n${fmtInstantIn(value, ZONE_LOCAL)} (Madrid, your local time)\nRaw: ${value}`;
    if (inline) {
        return (
            <span className="fi-instant fi-instant-inline mono" title={title}>
                {utc} <span className="fi-instant-secondary">· {secondary} ({secondaryLabel})</span>
            </span>
        );
    }
    return (
        <span className="fi-instant" title={title}>
            <span className="mono">{utc}</span>
            <span className="fi-instant-secondary mono">{secondary} <em>({secondaryLabel})</em></span>
        </span>
    );
}

/** Date-only contractual or session field: no time zone conversion applies. */
export function SessionDate({ value, label = 'session date' }: { value: string | null | undefined; label?: string }) {
    if (!value) return <span className="fi-muted">{DASH}</span>;
    return <span className="mono" title={`${label} (date only, no time zone)`}>{value.slice(0, 10)}</span>;
}

export function TimeLegend() {
    return (
        <p className="fi-time-legend">
            <i className="fas fa-clock"></i> Instants are stored in UTC. U.S. market and simulation events also show
            America/New_York; operational (platform processing) times also show Europe/Madrid, your local time.
            Date-only fields are shown without conversion.
        </p>
    );
}
