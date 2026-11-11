import axios from 'axios';
import { apiClient } from '../../services/api';
import type {
    Cycle,
    CurveSnapshot,
    DecisionDetail,
    DecisionSummary,
    EvidenceBundle,
    EvidenceChunkDetail,
    EvidenceGraph,
    ExperimentComparison,
    ExperimentDefinition,
    FixedIncomeHealth,
    IndexBuildCommand,
    IngestionCommand,
    InstrumentList,
    Journal,
    JsonObject,
    JsonValue,
    Order,
    Paged,
    PaperCycleCommand,
    Portfolio,
    ResearchNoteQuery,
    ResearchNoteResponse,
    RunAccepted,
    RunComparison,
    RunDetail,
    RunSummary,
    SecurityTerms,
    StartRunRequest,
    Valuation,
} from './types';

// Reuses the base URL configured for the legacy API client (VITE_API_URL).
// A separate instance keeps the optional bearer token scoped to /api/v1 calls.
export const fiClient = axios.create({
    baseURL: apiClient.defaults.baseURL,
    headers: { 'Content-Type': 'application/json' },
});

const TOKEN_KEY = 'fi.accessToken';

export function getAccessToken(): string | null {
    try {
        return window.sessionStorage.getItem(TOKEN_KEY);
    } catch {
        return null;
    }
}

export function setAccessToken(token: string | null): void {
    try {
        if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
        else window.sessionStorage.removeItem(TOKEN_KEY);
    } catch {
        // storage unavailable (private mode): requests continue unauthenticated
    }
}

fiClient.interceptors.request.use(config => {
    const token = getAccessToken();
    if (token) {
        config.headers.set('Authorization', `Bearer ${token}`);
    }
    return config;
});

const V1 = '/api/v1';
const enc = encodeURIComponent;

export interface PageParams {
    page?: number;
    pageSize?: number;
}

function clean<T extends object>(params: T): Partial<T> {
    const out: Partial<T> = {};
    for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null && value !== '') {
            (out as Record<string, unknown>)[key] = value;
        }
    }
    return out;
}

async function get<T>(url: string, params?: object): Promise<T> {
    const response = await fiClient.get<T>(url, { params: params ? clean(params) : undefined });
    return response.data;
}

async function post<T>(url: string, body?: unknown): Promise<T> {
    const response = await fiClient.post<T>(url, body ?? {});
    return response.data;
}

function isObject(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** The instrument list is research-engine passthrough; accept the plausible envelopes. */
export function normalizeInstrumentList(body: unknown): InstrumentList {
    if (Array.isArray(body)) return { items: body as SecurityTerms[] };
    if (!isObject(body)) return { items: [] };
    const items = (body.items ?? body.securities ?? body.instruments ?? []) as SecurityTerms[];
    return {
        items: Array.isArray(items) ? items : [],
        page: typeof body.page === 'number' ? body.page : undefined,
        pageSize: typeof body.pageSize === 'number' ? body.pageSize : undefined,
        totalCount: typeof body.totalCount === 'number' ? body.totalCount : undefined,
        universeId: typeof body.universeId === 'string' ? body.universeId : undefined,
        universeVersion: typeof body.universeVersion === 'string' ? body.universeVersion
            : typeof body.version === 'string' ? body.version : undefined,
        classification: typeof body.classification === 'string' ? body.classification : undefined,
        description: typeof body.description === 'string' ? body.description : undefined,
        hypotheticalNotice: typeof body.hypotheticalNotice === 'string' ? body.hypotheticalNotice : undefined,
    };
}

/** Evidence bundles may arrive bare or wrapped with pagination; chunks may be called items. */
export function normalizeBundle(body: unknown): EvidenceBundle {
    const raw = isObject(body) && isObject(body.bundle) ? { ...body.bundle, ...body } : body;
    const obj = (isObject(raw) ? raw : {}) as Record<string, unknown>;
    const chunks = (obj.chunks ?? obj.items ?? []) as EvidenceBundle['chunks'];
    return { ...(obj as unknown as EvidenceBundle), chunks: Array.isArray(chunks) ? chunks : [] };
}

export const fiApi = {
    // Experiments
    listExperiments: (p: PageParams = {}) => get<Paged<ExperimentDefinition>>(`${V1}/experiments`, p),
    getExperiment: (id: string, version?: number) =>
        get<ExperimentDefinition>(`${V1}/experiments/${enc(id)}`, { version }),
    createExperiment: (definition: JsonObject) => post<ExperimentDefinition>(`${V1}/experiments`, definition),
    startRun: (experimentId: string, request: StartRunRequest) =>
        post<RunAccepted>(`${V1}/experiments/${enc(experimentId)}/runs`, request),
    getExperimentComparison: (id: string) => get<ExperimentComparison>(`${V1}/experiments/${enc(id)}/comparison`),

    // Runs
    listRuns: (filter: PageParams & { experimentId?: string; jobState?: string; dataMode?: string; runType?: string } = {}) =>
        get<Paged<RunSummary>>(`${V1}/runs`, filter),
    getRun: (runId: string) => get<RunDetail>(`${V1}/runs/${enc(runId)}`),
    getRunComparison: (runId: string) => get<RunComparison>(`${V1}/runs/${enc(runId)}/comparison`),
    getRunCycles: (runId: string, p: PageParams = {}) => get<Paged<Cycle>>(`${V1}/runs/${enc(runId)}/cycles`, p),
    getRunDecisions: (runId: string, filter: PageParams & { cycleId?: string; strategyId?: string; outcome?: string } = {}) =>
        get<Paged<DecisionSummary>>(`${V1}/runs/${enc(runId)}/decisions`, filter),
    cancelRun: (runId: string) => post<{ runId: string; jobState: string }>(`${V1}/runs/${enc(runId)}/cancel`),

    // Decisions
    getDecision: (decisionId: string) => get<DecisionDetail>(`${V1}/decisions/${enc(decisionId)}`),

    // Portfolios
    getPortfolio: (id: string) => get<Portfolio>(`${V1}/portfolios/${enc(id)}`),
    getValuations: (id: string, p: PageParams & { completeOnly?: boolean } = {}) =>
        get<Paged<Valuation>>(`${V1}/portfolios/${enc(id)}/valuations`, p),
    getJournal: (id: string, filter: PageParams & { account?: string; eventType?: string; fromVersion?: number; toVersion?: number } = {}) =>
        get<Paged<Journal>>(`${V1}/portfolios/${enc(id)}/journal`, filter),
    getOrders: (id: string, filter: PageParams & { status?: string; securityId?: string; decisionId?: string } = {}) =>
        get<Paged<Order>>(`${V1}/portfolios/${enc(id)}/orders`, filter),

    // Instruments and curves (research-engine passthrough)
    listInstruments: async (filter: PageParams & { asOf?: string; universeVersion?: string; securityId?: string } = {}) =>
        normalizeInstrumentList(await get<unknown>(`${V1}/instruments`, filter)),
    getInstrumentValuation: (securityId: string, date?: string) =>
        get<JsonObject>(`${V1}/instruments/${enc(securityId)}/valuation`, { date }),
    getCurve: (snapshotId: string) => get<CurveSnapshot>(`${V1}/curves/${enc(snapshotId)}`),

    // Evidence
    getEvidenceBundle: async (bundleId: string, p: PageParams = {}) =>
        normalizeBundle(await get<unknown>(`${V1}/evidence/${enc(bundleId)}`, p)),
    getEvidenceChunk: (chunkId: string) => get<EvidenceChunkDetail>(`${V1}/evidence/chunks/${enc(chunkId)}`),
    getEvidenceGraph: (bundleId: string) => get<EvidenceGraph>(`${V1}/evidence/${enc(bundleId)}/graph`),

    // Research notes (informational, no order authority)
    createResearchNote: (query: ResearchNoteQuery) => post<ResearchNoteResponse>(`${V1}/research-notes`, query),

    // Operator actions
    startIngestion: (command: IngestionCommand) => post<JsonValue>(`${V1}/admin/ingestions`, command),
    startIndexBuild: (command: IndexBuildCommand) => post<JsonValue>(`${V1}/admin/index-builds`, command),
    triggerPaperCycle: (command: PaperCycleCommand) => post<RunAccepted>(`${V1}/admin/paper-cycles`, command),
    getAdminJob: (jobId: string) => get<JsonObject>(`${V1}/admin/jobs/${enc(jobId)}`),

    // Health: a 503 still carries the report body.
    getHealth: async (): Promise<FixedIncomeHealth> => {
        const response = await fiClient.get<FixedIncomeHealth>(`${V1}/health/fixed-income`, {
            validateStatus: status => status === 200 || status === 503,
        });
        return response.data;
    },
};
