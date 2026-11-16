import type { Citation } from '../api/types';

export interface LocatedPassage {
    before: string;
    match: string;
    after: string;
    method: 'offsets' | 'offsets_unverified' | 'quote_search' | 'not_found' | 'none';
}

/**
 * Highlights a cited passage inside the stored normalized chunk text. Offsets are
 * relative to the chunk text (contracts/decisions.py Citation). String matching
 * only; nothing is inferred about whether the passage supports a claim.
 */
export function locatePassage(text: string, citation: Pick<Citation, 'quote' | 'startOffset' | 'endOffset'>): LocatedPassage {
    const { quote } = citation;
    const start = citation.startOffset ?? null;
    const end = citation.endOffset ?? null;
    const split = (s: number, e: number, method: LocatedPassage['method']): LocatedPassage => ({
        before: text.slice(0, s),
        match: text.slice(s, e),
        after: text.slice(e),
        method,
    });

    const offsetsValid = start !== null && end !== null && start >= 0 && end <= text.length && start < end;
    if (offsetsValid) {
        const slice = text.slice(start, end);
        if (!quote) return split(start, end, 'offsets_unverified');
        if (slice === quote) return split(start, end, 'offsets');
    }
    if (quote) {
        const index = text.indexOf(quote);
        if (index >= 0) return split(index, index + quote.length, 'quote_search');
        return { before: text, match: '', after: '', method: 'not_found' };
    }
    return { before: text, match: '', after: '', method: 'none' };
}
