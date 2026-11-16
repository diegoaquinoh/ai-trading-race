import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { fiApi } from './client';
import type { PageParams } from './client';
import { httpStatus } from '../lib/errors';
import type { JsonObject, ResearchNoteQuery, StartRunRequest } from './types';

/** Do not retry client errors (404 for endpoints still being added, 401/403, 422). */
function retry(failureCount: number, error: unknown): boolean {
    const status = httpStatus(error);
    if (status !== undefined && status >= 400 && status < 500) return false;
    return failureCount < 1;
}

const base = { retry, placeholderData: keepPreviousData } as const;

// ─── Experiments & runs ─────────────────────────────────────────────────────

export function useExperiments(page = 1, pageSize = 50) {
    return useQuery({ ...base, queryKey: ['fi', 'experiments', page, pageSize], queryFn: () => fiApi.listExperiments({ page, pageSize }) });
}

export function useExperimentComparison(experimentId: string | undefined) {
    return useQuery({
        retry,
        queryKey: ['fi', 'experiment-comparison', experimentId],
        queryFn: () => fiApi.getExperimentComparison(experimentId!),
        enabled: !!experimentId,
    });
}

export function useRuns(filter: PageParams & { experimentId?: string; jobState?: string; dataMode?: string; runType?: string }) {
    return useQuery({ ...base, queryKey: ['fi', 'runs', filter], queryFn: () => fiApi.listRuns(filter), refetchInterval: 30_000 });
}

export function useRun(runId: string | undefined) {
    return useQuery({ retry, queryKey: ['fi', 'run', runId], queryFn: () => fiApi.getRun(runId!), enabled: !!runId });
}

export function useRunDetails(runIds: string[]) {
    return useQueries({
        queries: runIds.map(runId => ({
            queryKey: ['fi', 'run', runId],
            queryFn: () => fiApi.getRun(runId),
            retry,
            staleTime: 60_000,
        })),
    });
}

export function useRunComparison(runId: string | undefined) {
    return useQuery({ retry, queryKey: ['fi', 'run-comparison', runId], queryFn: () => fiApi.getRunComparison(runId!), enabled: !!runId });
}

export function useRunCycles(runId: string | undefined, page: number, pageSize = 200) {
    return useQuery({
        ...base,
        queryKey: ['fi', 'run-cycles', runId, page, pageSize],
        queryFn: () => fiApi.getRunCycles(runId!, { page, pageSize }),
        enabled: !!runId,
    });
}

export function useCycleDecisions(runId: string | undefined, cycleId: string | undefined) {
    return useQuery({
        retry,
        queryKey: ['fi', 'run-decisions', runId, cycleId],
        queryFn: () => fiApi.getRunDecisions(runId!, { cycleId, pageSize: 200 }),
        enabled: !!runId && !!cycleId,
    });
}

export function useRunDecisions(runId: string | undefined, filter: PageParams & { strategyId?: string; outcome?: string }) {
    return useQuery({
        ...base,
        queryKey: ['fi', 'run-decisions-list', runId, filter],
        queryFn: () => fiApi.getRunDecisions(runId!, filter),
        enabled: !!runId,
    });
}

// ─── Decisions & portfolios ─────────────────────────────────────────────────

export function useDecision(decisionId: string | undefined) {
    return useQuery({ retry, queryKey: ['fi', 'decision', decisionId], queryFn: () => fiApi.getDecision(decisionId!), enabled: !!decisionId });
}

export function usePortfolio(portfolioId: string | undefined) {
    return useQuery({ retry, queryKey: ['fi', 'portfolio', portfolioId], queryFn: () => fiApi.getPortfolio(portfolioId!), enabled: !!portfolioId });
}

export function usePortfolios(portfolioIds: string[]) {
    return useQueries({
        queries: portfolioIds.map(id => ({
            queryKey: ['fi', 'portfolio', id],
            queryFn: () => fiApi.getPortfolio(id),
            retry,
            staleTime: 60_000,
        })),
    });
}

export function useValuations(portfolioId: string | undefined, page: number, pageSize = 50) {
    return useQuery({
        ...base,
        queryKey: ['fi', 'valuations', portfolioId, page, pageSize],
        queryFn: () => fiApi.getValuations(portfolioId!, { page, pageSize }),
        enabled: !!portfolioId,
    });
}

/** Valuation series for several portfolios (equity curves); first 200 points each. */
export function useValuationSeries(portfolioIds: string[]) {
    return useQueries({
        queries: portfolioIds.map(id => ({
            queryKey: ['fi', 'valuations', id, 1, 200],
            queryFn: () => fiApi.getValuations(id, { page: 1, pageSize: 200 }),
            retry,
            staleTime: 60_000,
        })),
    });
}

export function useJournal(portfolioId: string | undefined, filter: PageParams & { account?: string; eventType?: string }) {
    return useQuery({
        ...base,
        queryKey: ['fi', 'journal', portfolioId, filter],
        queryFn: () => fiApi.getJournal(portfolioId!, filter),
        enabled: !!portfolioId,
    });
}

export function useOrders(portfolioId: string | undefined, filter: PageParams & { status?: string; decisionId?: string }) {
    return useQuery({
        ...base,
        queryKey: ['fi', 'orders', portfolioId, filter],
        queryFn: () => fiApi.getOrders(portfolioId!, filter),
        enabled: !!portfolioId,
    });
}

// ─── Instruments, curves, evidence ──────────────────────────────────────────

export function useInstruments(filter: PageParams & { asOf?: string; universeVersion?: string; securityId?: string }) {
    return useQuery({ ...base, queryKey: ['fi', 'instruments', filter], queryFn: () => fiApi.listInstruments(filter) });
}

export function useInstrumentValuation(securityId: string | undefined, date?: string) {
    return useQuery({
        retry,
        queryKey: ['fi', 'instrument-valuation', securityId, date ?? ''],
        queryFn: () => fiApi.getInstrumentValuation(securityId!, date || undefined),
        enabled: !!securityId,
    });
}

export function useInstrumentValuations(securityIds: string[]) {
    return useQueries({
        queries: securityIds.map(id => ({
            queryKey: ['fi', 'instrument-valuation', id, ''],
            queryFn: () => fiApi.getInstrumentValuation(id),
            retry,
            staleTime: 5 * 60_000,
        })),
    });
}

export function useCurve(snapshotId: string | undefined) {
    return useQuery({ retry, queryKey: ['fi', 'curve', snapshotId], queryFn: () => fiApi.getCurve(snapshotId!), enabled: !!snapshotId });
}

export function useEvidenceBundle(bundleId: string | undefined, page = 1, pageSize = 50) {
    return useQuery({
        ...base,
        queryKey: ['fi', 'evidence', bundleId, page, pageSize],
        queryFn: () => fiApi.getEvidenceBundle(bundleId!, { page, pageSize }),
        enabled: !!bundleId,
    });
}

export function useEvidenceChunk(chunkId: string | undefined) {
    return useQuery({
        retry,
        queryKey: ['fi', 'evidence-chunk', chunkId],
        queryFn: () => fiApi.getEvidenceChunk(chunkId!),
        enabled: !!chunkId,
        staleTime: 10 * 60_000,
    });
}

export function useEvidenceGraph(bundleId: string | undefined) {
    return useQuery({
        retry,
        queryKey: ['fi', 'evidence-graph', bundleId],
        queryFn: () => fiApi.getEvidenceGraph(bundleId!),
        enabled: !!bundleId,
    });
}

// ─── Health, admin, research ────────────────────────────────────────────────

export function useHealth() {
    return useQuery({ retry, queryKey: ['fi', 'health'], queryFn: fiApi.getHealth, refetchInterval: 30_000 });
}

export function useFailedRuns() {
    return useQuery({ retry, queryKey: ['fi', 'runs', 'failed'], queryFn: () => fiApi.listRuns({ jobState: 'failed', pageSize: 20 }) });
}

export function useAdminJob(jobId: string | undefined) {
    return useQuery({
        retry,
        queryKey: ['fi', 'admin-job', jobId],
        queryFn: () => fiApi.getAdminJob(jobId!),
        enabled: !!jobId,
        refetchInterval: query => {
            const state = (query.state.data as JsonObject | undefined)?.state ?? (query.state.data as JsonObject | undefined)?.status;
            return typeof state === 'string' && ['completed', 'failed', 'cancelled'].includes(state) ? false : 5_000;
        },
    });
}

export function useResearchNote() {
    return useMutation({ mutationFn: (query: ResearchNoteQuery) => fiApi.createResearchNote(query) });
}

export function useStartRun() {
    const client = useQueryClient();
    return useMutation({
        mutationFn: (args: { experimentId: string; request: StartRunRequest }) => fiApi.startRun(args.experimentId, args.request),
        onSuccess: () => client.invalidateQueries({ queryKey: ['fi', 'runs'] }),
    });
}

export function useCreateExperiment() {
    const client = useQueryClient();
    return useMutation({
        mutationFn: (definition: JsonObject) => fiApi.createExperiment(definition),
        onSuccess: () => client.invalidateQueries({ queryKey: ['fi', 'experiments'] }),
    });
}

export function useCancelRun(runId: string) {
    const client = useQueryClient();
    return useMutation({
        mutationFn: () => fiApi.cancelRun(runId),
        onSuccess: () => client.invalidateQueries({ queryKey: ['fi', 'run', runId] }),
    });
}
