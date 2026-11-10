// Tolerant readers for research-engine passthrough JSON whose exact envelope is
// owned by another workstream. They never compute values; they only locate them.

import type { JsonValue } from '../api/types';

export type Loose = Record<string, unknown>;

export function asObject(value: unknown): Loose | null {
    return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Loose) : null;
}

export function asArray<T = unknown>(value: unknown): T[] {
    return Array.isArray(value) ? (value as T[]) : [];
}

/** First defined value among the dotted paths. */
export function pick(source: unknown, ...paths: string[]): unknown {
    for (const path of paths) {
        let current: unknown = source;
        for (const key of path.split('.')) {
            const obj = asObject(current);
            current = obj ? obj[key] : undefined;
            if (current === undefined) break;
        }
        if (current !== undefined && current !== null) return current;
    }
    return undefined;
}

export function pickStr(source: unknown, ...paths: string[]): string | undefined {
    const value = pick(source, ...paths);
    if (typeof value === 'string') return value;
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    return undefined;
}

export function pickBool(source: unknown, ...paths: string[]): boolean | undefined {
    const value = pick(source, ...paths);
    return typeof value === 'boolean' ? value : undefined;
}

export function stringList(value: unknown): string[] {
    return asArray(value).map(v => (typeof v === 'string' ? v : JSON.stringify(v)));
}

export function isJsonValue(value: unknown): value is JsonValue {
    return value === null || ['string', 'number', 'boolean', 'object'].includes(typeof value);
}
