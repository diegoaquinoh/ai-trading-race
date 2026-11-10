// Types for the fixed income public API (/api/v1). Mirrors the .NET read models in
// AiTradingRace.Application/FixedIncome/Models and the Python contracts in
// ai-trading-race-ml/research_engine/contracts. JSON is camelCase; money, face,
// prices, rates and weights are decimal strings (parse for display only).

export type DecimalString = string;
/** ISO 8601 instant with offset (UTC from the API). */
export type IsoInstant = string;
/** Date-only contractual or session field (YYYY-MM-DD). */
export type IsoDate = string;

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };

export interface Paged<T> {
    items: T[];
    page: number;
    pageSize: number;
    totalCount: number;
}

export type DataMode = 'synthetic_curve' | 'observed_security';
export type JobState = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type RunType = 'replay' | 'forward';
export type ResponseMode = 'recorded_replay' | 'fresh_inference';
export type StrategyKind = 'cash_reference' | 'quant_policy' | 'single_agent' | 'specialist_team';
export type DecisionOutcome =
    | 'completed_hold'
    | 'completed_proposal'
    | 'abstained_insufficient_evidence'
    | 'review_required'
    | 'failed_invalid_output'
    | 'failed_dependency'
    | 'failed_budget'
    | 'skipped_stale_data'
    | 'cancelled';

// ─── Experiments ────────────────────────────────────────────────────────────

export interface ExperimentDefinition {
    experimentId: string;
    version: number;
    name: string;
    description: string | null;
    dataMode: string;
    riskPolicyId: string;
    executionModelId: string;
    instrumentUniverseVersion: string;
    startDate: IsoDate;
    endDate: IsoDate;
    repetitions: number;
    definitionHash: string;
    definition: JsonValue | null;
    createdAt: IsoInstant;
}

export interface StartRunRequest {
    runId?: string;
    experimentVersion?: number;
    runType: RunType;
    responseMode: ResponseMode;
}

export interface RunAccepted {
    runId: string;
    jobState: string;
    statusUrl: string;
    alreadyExisted: boolean;
}

// ─── Runs ───────────────────────────────────────────────────────────────────

export interface RunSummary {
    runId: string;
    experimentId: string;
    experimentVersion: number;
    runType: string;
    responseMode: string;
    dataMode: string;
    dataModeLabel: string;
    riskPolicyId: string;
    executionModelId: string;
    jobState: string;
    statusReason: string | null;
    completedCycles: number;
    totalCycles: number | null;
    simulatedClock: IsoInstant | null;
    createdAt: IsoInstant;
    startedAt: IsoInstant | null;
    completedAt: IsoInstant | null;
    /** Evaluation window of the experiment definition the run executes. */
    startDate: IsoDate | null;
    endDate: IsoDate | null;
    manifestHash: string | null;
    checkpoint: RunCheckpoint | null;
    errors: RunErrorSummary | null;
}

/** Latest checkpointed cycle (resume starts after it). */
export interface RunCheckpoint {
    cycleId: string;
    sequence: number;
    sessionDate: IsoDate;
    status: string;
    completedAt: IsoInstant | null;
    checkpointedCycles: number;
    totalCycles: number | null;
    lastCheckpointAt: IsoInstant | null;
}

/** Classified error (scope source | strategy | cycle | financial_state). */
export interface ClassifiedError {
    scope: string;
    severity: string;
    code: string;
    message: string;
    strategyId: string | null;
    portfolioId: string | null;
    commandId: string | null;
    decisionId: string | null;
    cycleId: string | null;
    at: string | null;
}

export interface RunErrorSummary {
    runErrors: number;
    cycleErrors: number;
    cycleWarnings: number;
    byScope: Record<string, number>;
    cycleStatusCounts: Record<string, number>;
}

export interface StrategyInstance {
    strategyId: string;
    strategyKind: string;
    strategyConfigId: string;
    repetition: number;
    portfolioId: string;
    label: string | null;
    /** provider/model ids recorded on this strategy's verified decisions (none for deterministic code). */
    observedModels?: string[];
}

export interface RunDetail {
    run: RunSummary;
    manifestHash: string;
    manifest: JsonValue | null;
    engineVersion: string | null;
    strategies: StrategyInstance[];
    outcomeCounts: Record<string, number>;
    runErrors: ClassifiedError[] | null;
}

export interface Cycle {
    cycleId: string;
    sequence: number;
    sessionDate: IsoDate;
    decisionAsOf: IsoInstant;
    status: string;
    skipReason: string | null;
    marketSnapshotId: string | null;
    marketSnapshotHash: string | null;
    curveSnapshotId: string | null;
    startedAt: IsoInstant | null;
    completedAt: IsoInstant | null;
    checkpointed: boolean;
    errorCount: number;
    warningCount: number;
    errors: ClassifiedError[] | null;
    checkpoint: JsonValue | null;
}

/** Compatibility group: runs are only compared within one group and groups are never ranked together. */
export interface ComparisonGroupKey {
    dataMode: string;
    riskPolicyId: string;
    executionModelId: string;
    runType: string | null;
    startDate: IsoDate | null;
    endDate: IsoDate | null;
}

/**
 * metrics-v1 output of research_engine.experiments.metrics (computed by the research engine,
 * passed through by the comparison API). Statistics are floats; money is decimal strings.
 */
export interface PortfolioMetrics {
    metricsVersion?: string;
    valuationCount?: number;
    completeValuationCount?: number;
    incompleteValuationCount?: number;
    observationCount?: number;
    unavailableReason?: string;
    startValuationAt?: string;
    endValuationAt?: string;
    elapsedCalendarDays?: number;
    startEquityUsd?: DecimalString | null;
    endEquityUsd?: DecimalString | null;
    externalFlowsUsd?: DecimalString | null;
    totalPnlUsd?: DecimalString | null;
    netReturn?: number | null;
    grossReturn?: number | null;
    annualizedReturn?: number | null;
    annualizedUnavailableReason?: string | null;
    dailyVolatility?: number | null;
    drawdown?: {
        maxDrawdown?: number | null;
        peakIndex?: number;
        troughIndex?: number;
        recoveryObservations?: number | null;
        recovered?: boolean | null;
    };
    sharpe?: { value?: number | null; unavailableReason?: string | null; annualization?: string };
    turnoverRatio?: number | null;
    tradedConsiderationUsd?: DecimalString | null;
    spreadCostUsd?: DecimalString | null;
    feesUsd?: DecimalString | null;
    decisionCount?: number;
    decisionOutcomes?: Record<string, number>;
    proposalCount?: number;
    policyEvaluations?: number;
    policyRejections?: number;
    ordersCreated?: number;
    fillCount?: number;
    expiryCount?: number;
    rejectedOrderCount?: number;
    cancelledOrderCount?: number;
    averageCashProportion?: number | null;
    averageDv01Usd?: number | null;
    maxDv01Usd?: number | null;
    averageEffectiveDurationYears?: number | null;
    endEffectiveDurationYears?: number | null;
    couponIncomeUsd?: DecimalString | null;
    redemptionsUsd?: DecimalString | null;
    realizedPnlUsd?: DecimalString | null;
    unrealizedPnlUsd?: DecimalString | null;
    interestIncomeUsd?: DecimalString | null;
    attribution?: {
        carryUsd?: DecimalString | null;
        priceUsd?: DecimalString | null;
        costsUsd?: DecimalString | null;
        residualUsd?: DecimalString | null;
        totalUsd?: DecimalString | null;
        reconciles?: boolean;
    };
}

export interface PairedComparison {
    portfolioId: string;
    versusPortfolioId: string;
    available: boolean;
    reason?: string;
    meanDifference?: number;
    ciLow?: number;
    ciHigh?: number;
    observations?: number;
    blockPolicy?: { method: string; blockLength: number; resamples: number; seed: number; confidence: number };
    note?: string;
}

/** Provenance of the run's evaluation metrics. */
export interface ComparisonMetrics {
    status: 'available' | 'unavailable' | string;
    unavailableReason: string | null;
    metricsVersion: string | null;
    engineVersion: string | null;
    conventions: JsonObject | null;
    pairedComparisons: PairedComparison[] | null;
}

export interface ComparisonEntry {
    strategyId: string;
    strategyKind: string;
    repetition: number;
    portfolioId: string;
    initialCapitalUsd: DecimalString;
    latestEquityUsd: DecimalString | null;
    returnRatio: DecimalString | null;
    latestValuationAt: IsoInstant | null;
    latestValuationComplete: boolean | null;
    valuationCount: number;
    incompleteValuationCount: number;
    decisionCount: number;
    outcomeCounts: Record<string, number>;
    ordersCreated: number;
    fills: number;
    feesUsd: DecimalString;
    spreadCostUsd: DecimalString;
    inputTokens: number;
    outputTokens: number;
    estimatedCostUsd: DecimalString | null;
    blockedReason: string | null;
    metrics: PortfolioMetrics | null;
    metricsUnavailableReason: string | null;
}

export interface RunComparison {
    runId: string;
    experimentId: string;
    group: ComparisonGroupKey;
    dataModeLabel: string;
    jobState: string;
    entries: ComparisonEntry[];
    notes: string[];
    metrics: ComparisonMetrics | null;
}

export interface ComparisonGroup {
    group: ComparisonGroupKey;
    dataModeLabel: string;
    runs: RunComparison[];
}

export interface ExperimentComparison {
    experimentId: string;
    groups: ComparisonGroup[];
    notes: string[];
}

// ─── Decisions ──────────────────────────────────────────────────────────────

export interface DecisionSummary {
    decisionId: string;
    runId: string;
    cycleId: string;
    strategyId: string;
    repetition: number;
    strategyKind: string | null;
    outcome: string;
    action: string | null;
    completedAt: IsoInstant;
    integrity: string;
    reasons: string[];
}

export interface DecisionAttempt {
    attemptId: string;
    attemptNumber: number;
    agentRole: string;
    purpose: string;
    provider: string;
    model: string;
    inputTokens: number;
    outputTokens: number;
    startedAt: IsoInstant;
    durationMs: number;
    status: string;
    recordedResponseId: string | null;
    error: string | null;
}

export interface ToolTrace {
    traceId: string;
    agentRole: string;
    toolName: string;
    request: JsonValue | null;
    responseSummary: JsonValue | null;
    outputRef: string | null;
    startedAt: IsoInstant;
    durationMs: number;
    status: string;
    error: string | null;
}

export interface Usage {
    generationCalls: number;
    toolCalls: number;
    evidenceCalls: number;
    uniqueEvidenceChunks: number;
    evidenceTokens: number;
    inputTokens: number;
    outputTokens: number;
    durationMs: number;
    estimatedCostUsd: DecimalString | null;
    priceScheduleId: string | null;
    budgetExhausted: string | null;
}

export interface TargetWeight {
    securityId: string;
    weight: DecimalString;
}

export interface PolicyCheck {
    checkId: string;
    limit: DecimalString | null;
    observed: DecimalString | null;
    unit: string;
    passed: boolean;
    reason: string | null;
}

export interface SizedOrder {
    securityId: string;
    side: string;
    face: DecimalString;
    estimatedDirtyPricePer100: DecimalString;
    estimatedConsiderationUsd: DecimalString;
}

/** portfolio.py PolicyEvaluation (stored JSON). */
export interface PolicyEvaluationDetail {
    policyId?: string;
    decisionId?: string;
    action?: string;
    passed?: boolean;
    breachMode?: boolean;
    bootstrapExemptionApplied?: boolean;
    originalTargets?: TargetWeight[];
    normalizedTargets?: TargetWeight[];
    normalizationNotes?: string[];
    sizedOrders?: SizedOrder[];
    rejectedReasons?: string[];
    checks?: PolicyCheck[];
    postTradeNavUsd?: DecimalString | null;
    postTradeCashRatio?: DecimalString | null;
    postTradeMaxSecurityRatio?: DecimalString | null;
    postTradeParallelDv01Usd?: DecimalString | null;
    turnoverRatio?: DecimalString | null;
    orderCount?: number;
    calculationIds?: string[];
}

export interface PolicyEvaluationView {
    source: string;
    policyId: string;
    action: string;
    passed: boolean;
    breachMode: boolean;
    bootstrapExemptionApplied: boolean;
    platformRecheckPassed: boolean | null;
    platformRecheckReasons: string[];
    commandId: string | null;
    evaluation: PolicyEvaluationDetail | null;
}

export interface Citation {
    citationId: string;
    bundleId: string;
    chunkId: string;
    documentVersionId: string;
    quote?: string | null;
    startOffset?: number | null;
    endOffset?: number | null;
}

export interface DocumentaryClaim {
    claimId: string;
    text: string;
    citationIds: string[];
    material?: boolean;
    validationStatus?: string;
    validationNotes?: string[];
}

export interface NumericalFinding {
    findingId: string;
    text: string;
    calculationIds: string[];
    inputSnapshotIds?: string[];
    validationStatus?: string;
}

export interface Hypothesis {
    hypothesisId: string;
    text: string;
    assumptions: string[];
    scenarioIds?: string[];
    supportingCitationIds?: string[];
}

export interface ResearchNote {
    status: string;
    claims?: DocumentaryClaim[];
    numericalFindings?: NumericalFinding[];
    hypotheses?: Hypothesis[];
    counterevidence?: string[];
    coverageGaps?: string[];
    citations?: Citation[];
    retrievalRunIds?: string[];
    explanation?: string;
}

export interface Proposal {
    action: string;
    targetWeights?: TargetWeight[];
    supportingClaimIds?: string[];
    supportingCalculationIds?: string[];
}

export interface ValidationResult {
    step: string;
    passed: boolean;
    severity?: string;
    details?: string[];
}

export interface SpecialistTask {
    taskId: string;
    role: string;
    instruction: string;
    inputSnapshotIds?: string[];
    expectedOutputSchema?: string;
    budgetReserved?: Record<string, number>;
    status: string;
    findings?: string[];
    claimIds?: string[];
    usage?: Record<string, number>;
}

export interface VersionInfo {
    provider?: string | null;
    model?: string | null;
    promptVersion?: string | null;
    toolSchemaVersion?: string | null;
    engineVersion?: string;
    evidenceSnapshotId?: string | null;
    indexBuildId?: string | null;
    retrievalMode?: string;
    strategyConfigHash?: string | null;
}

export interface DecisionDetail {
    decision: DecisionSummary;
    portfolioId: string | null;
    requestHash: string | null;
    inputHashes: Record<string, string> | null;
    proposal: Proposal | null;
    researchNote: ResearchNote | null;
    validation: ValidationResult[] | null;
    specialistTasks: SpecialistTask[] | null;
    versions: VersionInfo | null;
    evidenceBundleIds: string[];
    policyEvaluations: PolicyEvaluationView[];
    attempts: DecisionAttempt[];
    toolTraces: ToolTrace[];
    usage: Usage | null;
    orders: Order[];
    resultHash: string | null;
    engineVersion: string | null;
    /** Information cutoff (simulated time) and market session of the decision's cycle. */
    decisionAsOf: IsoInstant | null;
    marketSessionDate: IsoDate | null;
    cycleSequence: number | null;
    frozenInputs: DecisionFrozenInputs | null;
    fillIds: string[] | null;
    links: DecisionLinks | null;
}

/** Exact snapshots the decision was given. */
export interface DecisionFrozenInputs {
    portfolioSnapshotId: string | null;
    portfolioSnapshotVersion: number | null;
    portfolioSnapshotHash: string | null;
    marketSnapshotId: string | null;
    marketSnapshotHash: string | null;
    curveSnapshotId: string | null;
    evidenceSnapshotId: string | null;
    indexBuildId: string | null;
    instrumentUniverseVersion: string | null;
    strategyConfigId: string | null;
    riskPolicyId: string | null;
    availabilityPolicy: string | null;
    dataMode: string | null;
}

/** Public API links (paths) to the decision's run, cycles, portfolio and resulting orders. */
export interface DecisionLinks {
    run: string;
    cycles: string;
    portfolio: string | null;
    orders: string | null;
}

// ─── Portfolios ─────────────────────────────────────────────────────────────

export interface PositionMark {
    securityId: string;
    economicFace: DecimalString;
    markType: string;
    cleanPricePer100?: DecimalString | null;
    accruedPer100?: DecimalString | null;
    pvDirtyUsd?: DecimalString | null;
    observedAt?: IsoInstant | null;
    markAgeBusinessDays?: number | null;
    stale: boolean;
    calculationId?: string | null;
}

export interface ValuationDetail {
    marks?: PositionMark[];
    calculationIds?: string[];
}

export interface Valuation {
    valuationId: string;
    stateVersion: number;
    valuationAt: IsoInstant;
    dataMode: string;
    curveSnapshotId: string | null;
    markPolicy: string;
    complete: boolean;
    incompleteReasons: string[];
    cashUsd: DecimalString;
    bondValueUsd: DecimalString | null;
    receivablesPvUsd: DecimalString | null;
    payablesPvUsd: DecimalString | null;
    equityUsd: DecimalString | null;
    parallelDv01Usd: DecimalString | null;
    effectiveDurationYears: DecimalString | null;
    detail: ValuationDetail | null;
}

export interface Lot {
    lotId: string;
    securityId: string;
    face: DecimalString;
    tradeDate: IsoDate;
    settlementDate: IsoDate;
    cleanPricePer100: DecimalString;
    principalCostUsd: DecimalString;
    accruedPurchasedUsd: DecimalString;
}

export interface Position {
    securityId: string;
    economicFace: DecimalString;
    settledFace: DecimalString;
    lots?: Lot[];
}

export interface OrderIntent {
    orderId: string;
    decisionId: string;
    securityId: string;
    side: string;
    face: DecimalString;
    submittedAt: IsoInstant;
    eligibleSessionDate: IsoDate;
    expiresAt: IsoInstant;
    status: string;
    reservedCashUsd: DecimalString;
    statusReason?: string | null;
    bootstrap?: boolean;
}

export interface PendingSettlement {
    settlementId: string;
    fillId: string;
    securityId: string;
    side: string;
    face: DecimalString;
    settlementDate: IsoDate;
    cashUsd: DecimalString;
}

export interface PortfolioState {
    portfolioId?: string;
    version?: number;
    asOf?: IsoInstant;
    currency?: string;
    cashUsd?: DecimalString;
    reservedCashUsd?: DecimalString;
    positions?: Position[];
    openOrders?: OrderIntent[];
    pendingSettlements?: PendingSettlement[];
    externalCapitalUsd?: DecimalString;
    interestIncomeUsd?: DecimalString;
    realizedGainLossUsd?: DecimalString;
    transactionFeesUsd?: DecimalString;
    spreadCostUsd?: DecimalString;
    bookedUnrealizedUsd?: DecimalString;
    cashFlowsProcessedThrough?: IsoDate | null;
    lastValuationId?: string | null;
    riskBreaches?: string[];
    blockedReason?: string | null;
}

export interface Portfolio {
    portfolioId: string;
    runId: string;
    strategyId: string;
    repetition: number;
    riskPolicyId: string;
    dataMode: string;
    dataModeLabel: string;
    version: number;
    stateHash: string;
    blockedReason: string | null;
    blockedAt: IsoInstant | null;
    state: PortfolioState | null;
    openOrderCount: number;
    pendingSettlementCount: number;
    latestValuation: Valuation | null;
    updatedAt: IsoInstant;
    cash: PortfolioCash | null;
    paymentCalendar: PaymentCalendarView | null;
}

/** Display arithmetic over the stored state (computed by the API, not the engine). */
export interface PortfolioCash {
    settledCashUsd: DecimalString;
    reservedCashUsd: DecimalString;
    pendingPayablesUsd: DecimalString;
    pendingReceivablesUsd: DecimalString;
    committedCashUsd: DecimalString;
    availableCashUsd: DecimalString;
    basis: string;
}

export interface ProjectedPayment {
    securityId: string;
    kind: 'COUPON' | 'REDEMPTION' | string;
    paymentDate: IsoDate;
    unadjustedDate?: IsoDate;
    accrualStart?: IsoDate;
    accrualEnd?: IsoDate;
    amountPer100?: DecimalString;
    projectedEntitledFaceUsd: DecimalString;
    projectedAmountUsd: DecimalString;
    synthetic?: boolean;
}

/** Research-engine projection (POST /internal/v1/instruments/payment-calendar), passed through. */
export interface PaymentCalendar {
    portfolioId?: string;
    portfolioVersion?: number;
    after?: IsoDate;
    through?: IsoDate;
    cashFlowsProcessedThrough?: IsoDate | null;
    basis?: string;
    entitlementRule?: string;
    note?: string;
    items: ProjectedPayment[];
    totals?: { couponsUsd: DecimalString; redemptionsUsd: DecimalString; totalUsd: DecimalString };
}

export interface PaymentCalendarView {
    status: 'available' | 'unavailable' | 'no_holdings' | string;
    unavailableReason: string | null;
    calendar: PaymentCalendar | null;
}

export interface JournalLine {
    lineId: string;
    account: string;
    securityId: string | null;
    debitUsd: DecimalString;
    creditUsd: DecimalString;
    memo: string | null;
}

export interface Journal {
    journalId: string;
    eventId: string;
    eventType: string;
    effectiveAt: IsoInstant;
    template: string;
    committedVersion: number;
    commandId: string;
    lines: JournalLine[];
}

export interface Fill {
    fillId: string;
    executedAt: IsoInstant;
    observationId: string;
    quoteKind: string;
    referenceCleanPricePer100: DecimalString;
    executionCleanPricePer100: DecimalString;
    dirtyPricePer100: DecimalString;
    considerationUsd: DecimalString;
    feesUsd: DecimalString;
    settlementDate: IsoDate;
    timingLabel: string;
}

export interface Order {
    orderId: string;
    portfolioId: string;
    decisionId: string;
    securityId: string;
    side: string;
    face: DecimalString;
    submittedAt: IsoInstant;
    eligibleSessionDate: IsoDate;
    expiresAt: IsoInstant;
    status: string;
    statusReason: string | null;
    reservedCashUsd: DecimalString;
    bootstrap: boolean;
    createdInVersion: number;
    lastUpdatedVersion: number;
    fill: Fill | null;
}

// ─── Instruments, curves, valuation (research-engine passthrough) ─────────

export interface SecurityTerms {
    schemaVersion?: string;
    termsVersion: string;
    termsEffectiveFrom: IsoDate;
    termsEffectiveTo?: IsoDate | null;
    identity: {
        securityId: string;
        classification: 'synthetic' | 'actual' | string;
        issuerId: string;
        externalIdentifiers?: { scheme: string; value: string }[];
        displayName: string;
    };
    economics: {
        currency?: string;
        instrumentType?: string;
        couponRate: DecimalString;
        couponFrequency?: number;
        redemptionPer100?: DecimalString;
        callable?: boolean;
    };
    dates: {
        originalIssueDate: IsoDate;
        datedDate: IsoDate;
        maturityDate: IsoDate;
        firstCouponDate?: IsoDate | null;
    };
    schedule?: Record<string, JsonValue>;
    conventions?: {
        dayCount?: string;
        businessDayAdjustment?: string;
        calendarId?: string;
        calendarVersion?: string;
        settlementLagBusinessDays?: number;
        priceQuoteBasis?: string;
        yieldConvention?: string;
    };
    tradingUnits?: { minFaceUsd?: DecimalString; faceIncrementUsd?: DecimalString };
    provenance: {
        sourceId: string;
        sourceArtifact: string;
        sourceRow?: string | null;
        checksum?: string | null;
        availableAt: IsoInstant;
        validationStatus: string;
        notes?: string;
    };
}

export interface InstrumentList {
    items: SecurityTerms[];
    page?: number;
    pageSize?: number;
    totalCount?: number;
    universeId?: string;
    universeVersion?: string;
    classification?: string;
    description?: string;
    hypotheticalNotice?: string;
}

export interface CurveNode {
    nodeDate: IsoDate;
    timeYears: DecimalString;
    discountFactor: DecimalString;
    zeroRate: DecimalString;
    sourceTenor?: string | null;
}

export interface CalibrationResidual {
    tenor: string;
    kind: string;
    inputQuote: DecimalString;
    modelQuote: DecimalString;
    rateResidual: DecimalString;
    pricePer100Residual?: DecimalString | null;
    priceResidualPer100?: DecimalString | null;
    withinTolerance: boolean;
}

export interface CurveSpecification {
    specId: string;
    version: string;
    curveFamily?: string;
    inputSourceId?: string;
    calendarId?: string;
    calendarVersion?: string;
    timeDayCount?: string;
    zeroRateConvention?: string;
    shortEndTreatment?: { maxZeroCouponTenorMonths?: number; quoteConvention?: string; description?: string };
    instruments?: { tenor: string; kind: string; quoteConvention: string; dayCount: string; couponFrequency?: number | null }[];
    interpolation?: string;
    extrapolation?: string;
    requiredTenors?: string[];
    minNodes?: number;
    tolerances?: Record<string, JsonValue>;
    engine?: string;
}

export interface CurveSnapshot {
    curveSnapshotId: string;
    curveId: string;
    version: string;
    currency?: string;
    dataMode?: string;
    sessionDate: IsoDate;
    referenceDate: IsoDate;
    valuationAt: IsoInstant;
    availableAt: IsoInstant;
    inputObservationIds: string[];
    inputObservationHashes?: string[];
    specification: CurveSpecification;
    status: string;
    failureReasons?: string[];
    usedTenors?: string[];
    excludedTenors?: string[];
    residuals?: CalibrationResidual[];
    maxAbsPriceResidualPer100?: DecimalString | null;
    maxAbsRateResidual?: DecimalString | null;
    nodes?: CurveNode[];
    validatedHorizonDate?: IsoDate | null;
    engineVersion?: string;
    contentHash?: string | null;
}

// ─── Evidence ───────────────────────────────────────────────────────────────

export interface AvailabilityCheck {
    recordId: string;
    recordType: string;
    availableAt: IsoInstant;
    cutoff: IsoInstant;
    passed: boolean;
}

export interface SupportSpan {
    kind: string;
    chunkId?: string | null;
    versionId?: string | null;
    startOffset?: number | null;
    endOffset?: number | null;
    quote?: string | null;
    sourceRef?: string | null;
}

export interface ChunkProvenance {
    channels: string[];
    lexicalRank?: number | null;
    vectorRank?: number | null;
    graphRank?: number | null;
    rankingContribution?: Record<string, DecimalString>;
    fusedScore?: DecimalString;
    finalRank?: number;
    graph?: {
        seedId: string;
        pathAssertionIds: string[];
        pathLength: number;
        supportSpans?: SupportSpan[];
        availabilityChecks?: AvailabilityCheck[];
        graphScore?: DecimalString;
        addedByGraph?: boolean;
    } | null;
    availabilityChecks?: AvailabilityCheck[];
}

export interface DeliveredChunk {
    chunkId: string;
    versionId: string;
    documentId: string;
    sourceId: string;
    documentType: string;
    title: string;
    sourceUrl: string;
    publishedAt: IsoInstant;
    availableAt: IsoInstant;
    availabilityPolicy?: string;
    headingPath: string[];
    ordinal: number;
    startOffset: number;
    endOffset: number;
    text: string;
    textHash?: string;
    tokenCount?: number;
    fidelityFlags?: string[];
    synthetic?: boolean;
    provenance?: ChunkProvenance;
}

export interface StructuredFact {
    assertionId: string;
    relation: string;
    subjectId: string;
    subjectLabel: string;
    objectId: string;
    objectLabel: string;
    availableAt: IsoInstant;
    support: SupportSpan[];
}

export interface EvidenceBundle {
    bundleId: string;
    retrievalRunId: string;
    decisionAsOf: IsoInstant;
    mode: string;
    indexBuildId: string;
    snapshotId: string;
    chunks: DeliveredChunk[];
    structuredFacts?: StructuredFact[];
    totalTokens?: number;
    chunkCount?: number;
    truncatedByBudget?: string[];
    empty?: boolean;
    page?: number;
    pageSize?: number;
    totalCount?: number;
}

/** GET /api/v1/evidence/chunks/{chunkId} (being added by the .NET workstream). */
export interface EvidenceChunkDetail {
    chunkId: string;
    versionId?: string;
    documentId?: string;
    documentTitle?: string;
    title?: string;
    sourceUrl?: string;
    sourceId?: string;
    documentType?: string;
    publishedAt?: IsoInstant;
    publishedAtPrecision?: string;
    publicationTimezone?: string;
    availableAt?: IsoInstant;
    availabilityPolicy?: string;
    headingPath?: string[];
    startOffset?: number;
    endOffset?: number;
    text?: string;
    normalizedText?: string;
    fidelityFlags?: string[];
    synthetic?: boolean;
}

export interface EvidenceGraphNode {
    nodeId: string;
    nodeType: string;
    label: string;
    availableAt?: IsoInstant;
    properties?: Record<string, string>;
}

export interface EvidenceGraphEdge {
    assertionId: string;
    subjectId: string;
    objectId: string;
    relation: string;
    support?: SupportSpan[];
    availableAt?: IsoInstant;
    extractionMethod?: string;
    extractionVersion?: string;
    extractionRunId?: string;
    validationStatus?: string;
    confidence?: DecimalString;
    inputIds?: string[];
}

export interface EvidenceGraph {
    bundleId?: string;
    nodes: EvidenceGraphNode[];
    edges: EvidenceGraphEdge[];
    limitsHit?: string[];
    graphBackend?: string;
    graphBuildId?: string | null;
}

// ─── Research notes, admin, health ──────────────────────────────────────────

export interface ResearchNoteQuery {
    question: string;
    asOf?: string;
    evidenceSnapshotId?: string;
    indexBuildId?: string;
    retrievalMode?: string;
    responseMode: ResponseMode;
}

export interface ResearchNoteResponse {
    orderAuthority: false;
    note: JsonValue | null;
}

export interface FixedIncomeHealth {
    status: string;
    checkedAt: IsoInstant;
    database: { ready: boolean; error: string | null; queuedRuns: number; runningRuns: number };
    researchEngine: {
        reachable: boolean;
        ready: boolean;
        engineVersion: string | null;
        engineVersionAllowed: boolean;
        schemaVersions: string[];
        capabilities: JsonObject | null;
        error: string | null;
    };
    signingKeyConfigured: boolean;
    apiKeyConfigured: boolean;
    allowedEngineVersions: string[];
}

export interface IngestionCommand {
    sourceIds?: string[];
    reason?: string;
}

export interface IndexBuildCommand {
    evidenceSnapshotId?: string;
    baseIndexBuildId?: string;
    validateOnly: boolean;
    reason?: string;
}

export interface PaperCycleCommand {
    experimentId: string;
    experimentVersion?: number;
    runId?: string;
    responseMode?: ResponseMode;
}
