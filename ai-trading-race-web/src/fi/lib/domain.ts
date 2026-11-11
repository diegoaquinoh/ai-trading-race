// Domain vocabulary for display: decision outcomes (spec 15.2), strategy kinds
// (spec 10.1) and job states. Every outcome has a distinct style and icon so that
// identity never depends on color alone.

export interface OutcomeMeta {
    label: string;
    icon: string;
    tone: 'ok' | 'neutral' | 'warn' | 'fail' | 'muted';
    financial: string;
}

export const OUTCOMES: Record<string, OutcomeMeta> = {
    completed_hold: {
        label: 'Hold',
        icon: 'fa-pause-circle',
        tone: 'neutral',
        financial: 'Intentional no adjustment; normal financial processing continues.',
    },
    completed_proposal: {
        label: 'Proposal',
        icon: 'fa-check-circle',
        tone: 'ok',
        financial: 'Validated and potentially turned into authorized order intents.',
    },
    abstained_insufficient_evidence: {
        label: 'Abstained: insufficient evidence',
        icon: 'fa-question-circle',
        tone: 'warn',
        financial: 'No new evidence-dependent risk; the explicit abstention is retained.',
    },
    review_required: {
        label: 'Review required',
        icon: 'fa-user-shield',
        tone: 'warn',
        financial: 'No autonomous new trade for the flagged proposal.',
    },
    failed_invalid_output: {
        label: 'Failed: invalid output',
        icon: 'fa-file-excel',
        tone: 'fail',
        financial: 'No order; attempts and diagnostics are preserved.',
    },
    failed_dependency: {
        label: 'Failed: dependency',
        icon: 'fa-unlink',
        tone: 'fail',
        financial: 'No affected new order; the dependent failure is preserved.',
    },
    failed_budget: {
        label: 'Failed: budget',
        icon: 'fa-hourglass-end',
        tone: 'fail',
        financial: 'Generation and tools stopped; consumed resources are recorded.',
    },
    skipped_stale_data: {
        label: 'Skipped: stale data',
        icon: 'fa-history',
        tone: 'muted',
        financial: 'Matched discretionary cycle or affected execution skipped under policy.',
    },
    cancelled: {
        label: 'Cancelled',
        icon: 'fa-ban',
        tone: 'muted',
        financial: 'Uncommitted work cancelled; committed events remain authoritative.',
    },
};

export const OUTCOME_ORDER = Object.keys(OUTCOMES);

export function outcomeMeta(outcome: string): OutcomeMeta {
    return OUTCOMES[outcome] ?? { label: outcome, icon: 'fa-circle', tone: 'muted', financial: 'Unknown outcome.' };
}

export const FAILURE_OUTCOMES = ['failed_invalid_output', 'failed_dependency', 'failed_budget'];
export const EVIDENCE_OUTCOMES = ['abstained_insufficient_evidence', 'review_required', 'failed_dependency'];

export interface KindMeta {
    label: string;
    plural: string;
    description: string;
}

export const STRATEGY_KINDS: Record<string, KindMeta> = {
    cash_reference: {
        label: 'Cash reference',
        plural: 'Cash references',
        description: 'Holds cash under the cash-return assumption; a reference, not a competitor.',
    },
    quant_policy: {
        label: 'Quantitative policy',
        plural: 'Quantitative policies',
        description: 'Deterministic rule-based allocation.',
    },
    single_agent: {
        label: 'Single agent',
        plural: 'Single agents',
        description: 'One model-backed agent per portfolio (market-only, RAG or Graph RAG).',
    },
    specialist_team: {
        label: 'Specialist team',
        plural: 'Specialist teams (one portfolio each)',
        description: 'A lead agent delegating bounded tasks to specialists; one portfolio per team.',
    },
};

export const STRATEGY_KIND_ORDER = ['cash_reference', 'quant_policy', 'single_agent', 'specialist_team'];

export function kindMeta(kind: string | null | undefined): KindMeta {
    return (kind && STRATEGY_KINDS[kind]) || { label: kind ?? 'Unknown', plural: kind ?? 'Unknown', description: '' };
}

export const JOB_STATES = ['queued', 'running', 'completed', 'failed', 'cancelled'];

export function isTerminalJob(state: string): boolean {
    return state === 'completed' || state === 'failed' || state === 'cancelled';
}

export const ORDER_STATUSES = ['ACCEPTED', 'FILLED', 'EXPIRED', 'CANCELLED', 'REJECTED'];

export const SERIES_COLORS = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'];

/** Strategy display key, stable across filters (color follows the entity). */
export function strategyKey(strategyId: string, repetition: number, runId?: string): string {
    return `${runId ? `${runId}/` : ''}${strategyId}#${repetition}`;
}
