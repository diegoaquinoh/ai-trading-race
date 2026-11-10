import type { RunDetail } from '../api/types';
import { asArray, pickStr } from './read';

export interface StrategyMeta {
    strategyId: string;
    repetition: number;
    label: string | null;
    configId: string;
    provider?: string;
    modelId?: string;
    retrievalMode?: string;
    family: string;
}

/**
 * Strategy configuration and model versions for a run, from the strategy
 * instances and (when present) the run manifest's strategies section.
 */
export function strategyMetaFor(detail: RunDetail | undefined): Map<string, StrategyMeta> {
    const map = new Map<string, StrategyMeta>();
    if (!detail) return map;
    const manifestStrategies = asArray(pickStrategies(detail.manifest));
    for (const s of detail.strategies) {
        const m = manifestStrategies.find(x => pickStr(x, 'strategyId') === s.strategyId);
        const observed = s.observedModels?.[0];
        const provider = pickStr(m, 'provider') ?? (observed?.includes('/') ? observed.split('/')[0] : undefined);
        const modelId = pickStr(m, 'modelId', 'model') ?? (observed ? observed.split('/').slice(-1)[0] : undefined);
        const retrievalMode = pickStr(m, 'retrievalMode');
        const family = provider ?? modelId ?? (s.strategyKind === 'cash_reference' || s.strategyKind === 'quant_policy' ? 'deterministic' : 'unspecified');
        map.set(`${s.strategyId}#${s.repetition}`, {
            strategyId: s.strategyId,
            repetition: s.repetition,
            label: s.label,
            configId: s.strategyConfigId,
            provider,
            modelId,
            retrievalMode,
            family,
        });
    }
    return map;
}

function pickStrategies(manifest: unknown): unknown {
    if (manifest && typeof manifest === 'object' && !Array.isArray(manifest)) {
        return (manifest as Record<string, unknown>).strategies;
    }
    return undefined;
}

export function manifestValue(detail: RunDetail | undefined, ...paths: string[]): string | undefined {
    return detail ? pickStr(detail.manifest, ...paths) : undefined;
}
