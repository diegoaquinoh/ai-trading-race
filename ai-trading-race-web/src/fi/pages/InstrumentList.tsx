import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useInstruments } from '../api/hooks';
import { SyntheticBadge, Tag } from '../components/Badges';
import { Instant } from '../components/Instant';
import { Notice, PageHeader, Panel } from '../components/Layout';
import { Pagination } from '../components/Pagination';
import { QueryState } from '../components/States';
import { DASH, fmtPct } from '../lib/format';
import { isSyntheticTerms } from '../lib/instrument';

export function InstrumentList() {
    const [asOf, setAsOf] = useState('');
    const [universeVersion, setUniverseVersion] = useState('');
    const [page, setPage] = useState(1);
    const query = useInstruments({ asOf: asOf ? `${asOf}T23:59:59Z` : undefined, universeVersion: universeVersion || undefined, page, pageSize: 50 });

    return (
        <div className="fi-page">
            <PageHeader
                icon="fa-file-contract"
                title="Instruments"
                breadcrumbs={[{ to: '/fi', label: 'Research lab' }]}
                subtitle="Admitted securities and their contractual term versions. Synthetic notes are hypothetical and carry internal identifiers."
            />
            <Panel title="Security master" icon="fa-table">
                <div className="fi-filters">
                    <label>Terms as of (UTC end of day)
                        <input type="date" value={asOf} onChange={e => { setAsOf(e.target.value); setPage(1); }} />
                    </label>
                    <label>Universe version
                        <input type="text" value={universeVersion} placeholder="latest" onChange={e => { setUniverseVersion(e.target.value); setPage(1); }} />
                    </label>
                </div>
                <QueryState query={query} label="instruments" isEmpty={d => d.items.length === 0} emptyMessage="No admitted instruments for these filters.">
                    {data => (
                        <>
                            {(data.hypotheticalNotice || data.classification === 'synthetic') && (
                                <Notice tone="warn" icon="fa-flask">
                                    <strong>Synthetic universe{data.universeVersion ? ` ${data.universeVersion}` : ''}.</strong>{' '}
                                    {data.hypotheticalNotice || 'Hypothetical instruments; they do not represent actual securities, and their prices are curve-model values.'}
                                </Notice>
                            )}
                            <div className="fi-table-wrap">
                                <table className="fi-table">
                                    <thead>
                                        <tr>
                                            <th>Security</th>
                                            <th>Classification</th>
                                            <th>Coupon</th>
                                            <th>Issue / maturity</th>
                                            <th>Conventions</th>
                                            <th>Terms version</th>
                                            <th>Provenance</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {data.items.map(t => (
                                            <tr key={`${t.identity.securityId}@${t.termsVersion}`}>
                                                <td>
                                                    <Link to={`/fi/instruments/${encodeURIComponent(t.identity.securityId)}`} className="mono">{t.identity.securityId}</Link>
                                                    <div className="fi-small">{t.identity.displayName}</div>
                                                </td>
                                                <td>{isSyntheticTerms(t) ? <SyntheticBadge /> : <Tag tone="ok">actual</Tag>}</td>
                                                <td className="mono">{fmtPct(t.economics.couponRate, 3)} <span className="fi-small">s/a</span></td>
                                                <td className="mono fi-small">{t.dates.originalIssueDate} → {t.dates.maturityDate}</td>
                                                <td className="fi-small">{t.conventions?.dayCount ?? DASH} · {t.conventions?.calendarId ?? DASH} · T+{t.conventions?.settlementLagBusinessDays ?? '?'}</td>
                                                <td className="fi-small mono">{t.termsVersion}<div>from {t.termsEffectiveFrom}{t.termsEffectiveTo ? ` to ${t.termsEffectiveTo}` : ''}</div></td>
                                                <td className="fi-small">
                                                    <Tag tone={t.provenance.validationStatus === 'validated' ? 'ok' : t.provenance.validationStatus === 'rejected' ? 'fail' : 'muted'}>
                                                        {t.provenance.validationStatus}
                                                    </Tag>
                                                    <div className="mono">{t.provenance.sourceId}</div>
                                                    <Instant value={t.provenance.availableAt} inline />
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                            {data.totalCount !== undefined && (
                                <Pagination page={data.page ?? page} pageSize={data.pageSize ?? 50} totalCount={data.totalCount} onPage={setPage} label="instruments" />
                            )}
                        </>
                    )}
                </QueryState>
            </Panel>
        </div>
    );
}
