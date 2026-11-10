import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Valuation } from '../api/types';
import { fmtInstantIn, fmtUsd, ZONE_UTC } from '../lib/format';

export interface EquitySeries {
    key: string;
    label: string;
    color: string;
    valuations: Valuation[];
}

interface Row {
    t: string;
    [key: string]: string | number | null;
}

/**
 * Reconciled equity per portfolio as reported by the API. Incomplete or missing
 * valuations are left as gaps (never interpolated) and counted under the chart.
 */
export function EquityCurves({ series, height = 300 }: { series: EquitySeries[]; height?: number }) {
    const times = new Set<string>();
    series.forEach(s => s.valuations.forEach(v => times.add(v.valuationAt)));
    const sorted = [...times].sort();
    const rows: Row[] = sorted.map(t => {
        const row: Row = { t };
        for (const s of series) {
            const v = s.valuations.find(x => x.valuationAt === t);
            row[s.key] = v && v.complete && v.equityUsd !== null ? Number(v.equityUsd) : null;
        }
        return row;
    });
    const gaps = series
        .map(s => ({ label: s.label, count: s.valuations.filter(v => !v.complete || v.equityUsd === null).length }))
        .filter(g => g.count > 0);

    if (rows.length === 0) {
        return <p className="fi-muted-note">No saved valuations yet.</p>;
    }

    return (
        <div className="fi-chart">
            <ResponsiveContainer width="100%" height={height}>
                <LineChart data={rows} margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
                    <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                    <XAxis
                        dataKey="t"
                        stroke="var(--text-secondary)"
                        fontSize={11}
                        tickLine={false}
                        tickFormatter={(t: string) => t.slice(0, 10)}
                        minTickGap={24}
                    />
                    <YAxis
                        stroke="var(--text-secondary)"
                        fontSize={11}
                        tickLine={false}
                        width={84}
                        domain={['auto', 'auto']}
                        tickFormatter={(v: number) => fmtUsd(v, 0)}
                    />
                    <Tooltip
                        contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-light)', borderRadius: 8 }}
                        labelStyle={{ color: 'var(--text-secondary)' }}
                        itemStyle={{ color: 'var(--text-primary)' }}
                        labelFormatter={label => `Valuation at ${fmtInstantIn(String(label), ZONE_UTC)}`}
                        formatter={(value, name) => [value === null || value === undefined ? 'incomplete' : fmtUsd(Number(value)), String(name)]}
                    />
                    <Legend wrapperStyle={{ fontSize: 12, color: 'var(--text-secondary)' }} />
                    {series.map(s => (
                        <Line
                            key={s.key}
                            type="linear"
                            dataKey={s.key}
                            name={s.label}
                            stroke={s.color}
                            strokeWidth={2}
                            dot={false}
                            activeDot={{ r: 4, stroke: 'var(--bg-card)', strokeWidth: 2 }}
                            connectNulls={false}
                            isAnimationActive={false}
                        />
                    ))}
                </LineChart>
            </ResponsiveContainer>
            {gaps.length > 0 && (
                <p className="fi-chart-note">
                    <i className="fas fa-exclamation-triangle"></i> Gaps mark incomplete or stale valuations (not interpolated):{' '}
                    {gaps.map(g => `${g.label} ${g.count}`).join(' · ')}
                </p>
            )}
        </div>
    );
}
