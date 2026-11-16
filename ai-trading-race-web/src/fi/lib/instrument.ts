import type { SecurityTerms } from '../api/types';
import { asArray, asObject, pick, pickBool, pickStr } from './read';

export function isSyntheticTerms(terms: SecurityTerms | undefined | null, securityId?: string): boolean {
    return terms?.identity?.classification === 'synthetic' || (securityId ?? terms?.identity?.securityId ?? '').startsWith('SYN-');
}

// The instrument valuation endpoint (/api/v1/instruments/{id}/valuation) is being
// added in parallel; these readers locate fields under the likely envelopes
// without assuming one exact shape. No value is derived here.

export interface ModelValues {
    cleanPricePer100?: string;
    dirtyPricePer100?: string;
    accruedPer100?: string;
    accruedInterestUsd?: string;
    ytm?: string;
    calculationId?: string;
    markType?: string;
}

export interface ObservedQuoteView {
    kind?: string;
    bidPer100?: string;
    askPer100?: string;
    midPer100?: string;
    priceBasis?: string;
    executable?: boolean;
    observedAt?: string;
    availableAt?: string;
    sourceId?: string;
}

export interface CashFlowView {
    paymentDate?: string;
    kind?: string;
    amountPer100?: string;
    amountUsd?: string;
    accrualStart?: string;
    accrualEnd?: string;
}

export interface KeyRateView {
    keyTenorYears?: string;
    dv01?: string;
}

export interface ScenarioView {
    scenarioId?: string;
    description?: string;
    shiftBp?: string;
    pricePer100?: string;
    pvUsd?: string;
    pnlUsd?: string;
}

export interface RelativeValueView {
    status?: string;
    reason?: string;
    referenceModel?: string;
    cleanPriceResidualPer100?: string;
    yieldResidual?: string;
}

export interface InstrumentValuationView {
    terms?: SecurityTerms;
    synthetic?: boolean;
    dataMode?: string;
    valuationDate?: string;
    settlementDate?: string;
    faceUsd?: string;
    curveSnapshotId?: string;
    curveSpecId?: string;
    curveMaxAbsPriceResidual?: string;
    curveStatus?: string;
    model: ModelValues;
    observed?: ObservedQuoteView;
    cashFlows: CashFlowView[];
    risk: {
        ytm?: string;
        yieldModifiedDurationYears?: string;
        effectiveDurationYears?: string;
        effectiveConvexity?: string;
        yieldConvexity?: string;
        parallelDv01?: string;
        dv01Basis?: string;
        keyRates: KeyRateView[];
        keyRateSumMinusParallel?: string;
        remainingMaturityYears?: string;
        maturityBucket?: string;
    };
    scenarios: ScenarioView[];
    relativeValue?: RelativeValueView;
    calculationIds: string[];
    diagnostics: string[];
    engineVersion?: string;
}

const MODEL_ROOTS = ['curveModel', 'model', 'modelValues', 'modelValuation', 'price', 'pricing'];

function fromRoots(source: unknown, roots: string[], field: string, withRoot = true): string | undefined {
    const paths = roots.map(r => `${r}.${field}`);
    if (withRoot) paths.push(field);
    return pickStr(source, ...paths);
}

export function readInstrumentValuation(body: unknown): InstrumentValuationView {
    const risk = pick(body, 'risk', 'positionRisk') ?? body;
    const observedRaw = asObject(pick(body, 'observed', 'observedQuote', 'quote', 'marketQuote'));
    const terms = asObject(pick(body, 'terms', 'securityTerms')) as SecurityTerms | null;
    const rv = asObject(pick(body, 'relativeValue', 'risk.relativeValue'));
    const calcIds = pick(body, 'calculationIds');
    const singleCalc = pickStr(body, 'calculationId');

    return {
        terms: terms ?? undefined,
        synthetic: pickBool(body, 'synthetic', 'isSynthetic'),
        dataMode: pickStr(body, 'dataMode'),
        valuationDate: pickStr(body, 'valuationDate', 'asOfDate', 'date'),
        settlementDate: pickStr(body, 'settlementDate', 'curveModel.settlementDate', 'model.settlementDate'),
        faceUsd: pickStr(body, 'faceUsd', 'risk.faceUsd'),
        curveSnapshotId: pickStr(body, 'curveSnapshotId', 'curve.curveSnapshotId', 'curveModel.curveSnapshotId'),
        curveSpecId: pickStr(body, 'curveSpecId', 'curve.specId', 'curve.specification.specId', 'curveSpecification.specId'),
        curveMaxAbsPriceResidual: pickStr(body, 'curve.maxAbsPriceResidualPer100', 'calibration.maxAbsPriceResidualPer100', 'curveCalibration.maxAbsPriceResidualPer100'),
        curveStatus: pickStr(body, 'curve.status', 'curveStatus'),
        model: {
            cleanPricePer100: fromRoots(body, MODEL_ROOTS, 'cleanPricePer100'),
            dirtyPricePer100: fromRoots(body, MODEL_ROOTS, 'dirtyPricePer100'),
            accruedPer100: fromRoots(body, MODEL_ROOTS, 'accruedPer100'),
            accruedInterestUsd: fromRoots(body, MODEL_ROOTS, 'accruedInterestUsd'),
            ytm: fromRoots(body, MODEL_ROOTS, 'ytm') ?? pickStr(risk, 'ytm'),
            calculationId: fromRoots(body, MODEL_ROOTS, 'calculationId', false),
            markType: fromRoots(body, MODEL_ROOTS, 'markType', false),
        },
        observed: observedRaw ? {
            kind: pickStr(observedRaw, 'kind', 'quoteKind', 'quoteType'),
            bidPer100: pickStr(observedRaw, 'bidPer100'),
            askPer100: pickStr(observedRaw, 'askPer100'),
            midPer100: pickStr(observedRaw, 'midPer100', 'pricePer100'),
            priceBasis: pickStr(observedRaw, 'priceBasis'),
            executable: pickBool(observedRaw, 'executable'),
            observedAt: pickStr(observedRaw, 'observedAt'),
            availableAt: pickStr(observedRaw, 'availableAt'),
            sourceId: pickStr(observedRaw, 'sourceId'),
        } : undefined,
        cashFlows: asArray(pick(body, 'upcomingCashFlows', 'cashFlows', 'upcomingPayments', 'schedule.upcoming')).map(cf => ({
            paymentDate: pickStr(cf, 'paymentDate', 'adjustedPaymentDate', 'date'),
            kind: pickStr(cf, 'kind', 'type'),
            amountPer100: pickStr(cf, 'amountPer100', 'cashPer100'),
            amountUsd: pickStr(cf, 'amountUsd'),
            accrualStart: pickStr(cf, 'accrualStart', 'accrualStartDate'),
            accrualEnd: pickStr(cf, 'accrualEnd', 'accrualEndDate'),
        })),
        risk: {
            ytm: pickStr(risk, 'ytm'),
            yieldModifiedDurationYears: pickStr(risk, 'yieldModifiedDurationYears', 'modifiedDurationYears'),
            effectiveDurationYears: pickStr(risk, 'effectiveDurationYears'),
            effectiveConvexity: pickStr(risk, 'effectiveConvexity'),
            yieldConvexity: pickStr(risk, 'yieldConvexity'),
            parallelDv01: pickStr(risk, 'parallelDv01Usd', 'parallelDv01Per100', 'parallelDv01'),
            dv01Basis: pickStr(risk, 'dv01Basis', 'basis') ?? (pickStr(risk, 'parallelDv01Per100') ? 'per 100 face' : pickStr(risk, 'parallelDv01Usd') ? 'USD for the stated face' : undefined),
            keyRates: asArray(pick(risk, 'keyRateDv01', 'keyRates')).map(k => ({
                keyTenorYears: pickStr(k, 'keyTenorYears', 'tenorYears', 'tenor'),
                dv01: pickStr(k, 'dv01Usd', 'dv01Per100', 'dv01'),
            })),
            keyRateSumMinusParallel: pickStr(risk, 'keyRateSumMinusParallelUsd'),
            remainingMaturityYears: pickStr(risk, 'remainingMaturityYears'),
            maturityBucket: pickStr(risk, 'maturityBucket'),
        },
        scenarios: asArray(pick(body, 'scenarios', 'scenarioPrices', 'risk.scenarios')).map(s => ({
            scenarioId: pickStr(s, 'scenarioId', 'id'),
            description: pickStr(s, 'description'),
            shiftBp: pickStr(s, 'parallelShiftBp', 'shiftBp'),
            pricePer100: pickStr(s, 'scenarioCleanPricePer100', 'scenarioPricePer100', 'cleanPricePer100', 'pricePer100'),
            pvUsd: pickStr(s, 'scenarioPvUsd', 'pvUsd'),
            pnlUsd: pickStr(s, 'pnlUsd', 'pnlPer100'),
        })),
        relativeValue: rv ? {
            status: pickStr(rv, 'status'),
            reason: pickStr(rv, 'reason'),
            referenceModel: pickStr(rv, 'referenceModel'),
            cleanPriceResidualPer100: pickStr(rv, 'cleanPriceResidualPer100'),
            yieldResidual: pickStr(rv, 'yieldResidual'),
        } : typeof pick(body, 'relativeValue') === 'string' ? { status: pickStr(body, 'relativeValue') } : undefined,
        calculationIds: [...asArray<string>(calcIds).filter(x => typeof x === 'string'), ...(singleCalc ? [singleCalc] : [])],
        diagnostics: asArray(pick(body, 'diagnostics')).map(String),
        engineVersion: pickStr(body, 'engineVersion', 'engine.engineVersion'),
    };
}

/** Relative value is only a number when the API says it is available. */
export function relativeValueAvailable(rv: RelativeValueView | undefined): boolean {
    return rv?.status === 'available';
}
