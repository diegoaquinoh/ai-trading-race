// Display formatting only. Decimal strings from the API are parsed to numbers solely
// to render them; no financial arithmetic is performed in the UI.

export const DASH = '—';

function toNumber(value: string | number | null | undefined): number | null {
    if (value === null || value === undefined || value === '') return null;
    const n = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(n) ? n : null;
}

export function fmtNumber(value: string | number | null | undefined, digits = 2): string {
    const n = toNumber(value);
    if (n === null) return DASH;
    return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtUsd(value: string | number | null | undefined, digits = 2): string {
    const n = toNumber(value);
    if (n === null) return DASH;
    return n.toLocaleString('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    });
}

/** Face amounts (USD face) without a currency symbol, to avoid reading them as cash. */
export function fmtFace(value: string | number | null | undefined): string {
    const n = toNumber(value);
    if (n === null) return DASH;
    return `${n.toLocaleString('en-US', { maximumFractionDigits: 2 })} face`;
}

/** Ratio or decimal rate (0.045) rendered as a percentage via Intl percent style. */
export function fmtPct(value: string | number | null | undefined, digits = 2): string {
    const n = toNumber(value);
    if (n === null) return DASH;
    return n.toLocaleString('en-US', { style: 'percent', minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Price per 100 face. */
export function fmtPrice(value: string | number | null | undefined, digits = 4): string {
    const n = toNumber(value);
    if (n === null) return DASH;
    return n.toFixed(digits);
}

export function fmtInt(value: number | null | undefined): string {
    if (value === null || value === undefined) return DASH;
    return value.toLocaleString('en-US');
}

export function fmtMs(ms: number | null | undefined): string {
    if (ms === null || ms === undefined) return DASH;
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
}

/** Signed class for gain/loss coloring, using the sign of the provided value only. */
export function signClass(value: string | number | null | undefined): string {
    const n = toNumber(value);
    if (n === null || n === 0) return '';
    return n > 0 ? 'positive' : 'negative';
}

export function humanize(value: string | null | undefined): string {
    if (!value) return DASH;
    return value.replace(/_/g, ' ');
}

export function shortHash(value: string | null | undefined, keep = 12): string {
    if (!value) return DASH;
    const body = value.startsWith('sha256:') ? value.slice(7) : value;
    return body.length > keep ? `${value.startsWith('sha256:') ? 'sha256:' : ''}${body.slice(0, keep)}…` : value;
}

// ─── Time ───────────────────────────────────────────────────────────────────

export const ZONE_UTC = 'UTC';
export const ZONE_MARKET = 'America/New_York';
export const ZONE_LOCAL = 'Europe/Madrid';

const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(timeZone: string): Intl.DateTimeFormat {
    let f = formatters.get(timeZone);
    if (!f) {
        f = new Intl.DateTimeFormat('en-CA', {
            timeZone,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
            timeZoneName: 'short',
        });
        formatters.set(timeZone, f);
    }
    return f;
}

/** Formats a UTC instant in an IANA zone as "YYYY-MM-DD HH:mm TZ". */
export function fmtInstantIn(value: string | null | undefined, timeZone: string): string {
    if (!value) return DASH;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    const parts = formatter(timeZone).formatToParts(date);
    const get = (type: string) => parts.find(p => p.type === type)?.value ?? '';
    const hour = get('hour') === '24' ? '00' : get('hour');
    return `${get('year')}-${get('month')}-${get('day')} ${hour}:${get('minute')} ${get('timeZoneName')}`;
}

export function fmtDate(value: string | null | undefined): string {
    if (!value) return DASH;
    return value.slice(0, 10);
}
