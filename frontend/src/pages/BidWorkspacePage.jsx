/**
 * BidWorkspacePage — TECHNICAL_EVALUATOR only
 *
 * Owns:
 *  - Bid compliance matrix table (all bids, status, risk band, score)
 *  - "Run Evaluation" trigger per bid
 *  - Rule-level result breakdown (which rules PASS/FAIL/REVIEW per bid)
 *  - Link: "View Full Evidence →" navigates to /compliance?bidId=xxx
 *
 * Does NOT contain:
 *  ✗ Document upload zone  (→ /my-bids for bidders)
 *  ✗ Evidence inspector  (→ /compliance)
 *  ✗ Government connector logs  (→ /compliance)
 *  ✗ Officer override actions  (→ /dashboard)
 *  ✗ Financial data  (→ /financial)
 *  ✗ Audit chain  (→ /audit)
 */

import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { listBids, evaluateBid, listTenders, getTenderBids } from '../api/client';

// ─── Status Styles ────────────────────────────────────────────────────────────

const STATUS_STYLE = {
  PASS:        { bg: '#dcfce7', color: '#166534', border: '#86efac' },
  COMPLIANT:   { bg: '#dcfce7', color: '#166534', border: '#86efac' },
  FAIL:        { bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' },
  NON_COMPLIANT: { bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' },
  REVIEW:      { bg: '#fffbeb', color: '#92400e', border: '#fde68a' },
  UNDER_REVIEW:{ bg: '#fffbeb', color: '#92400e', border: '#fde68a' },
  PENDING:     { bg: '#f1f5f9', color: '#475569', border: '#cbd5e1' },
  PENDING_VERIFICATION: { bg: '#f1f5f9', color: '#475569', border: '#cbd5e1' },
  CRITICAL:    { bg: '#fdf4ff', color: '#7e22ce', border: '#d8b4fe' },
  HIGH:        { bg: '#fffbeb', color: '#92400e', border: '#fde68a' },
  LOW:         { bg: '#f0fdf4', color: '#166534', border: '#bbf7d0' },
  MEDIUM:      { bg: '#eff6ff', color: '#1d4ed8', border: '#bfdbfe' },
};

function Pill({ status }) {
  const s = STATUS_STYLE[status] || { bg: '#f1f5f9', color: '#475569', border: '#cbd5e1' };
  return (
    <span style={{
      display: 'inline-block', padding: '2px 9px', borderRadius: 20,
      fontSize: 11, fontWeight: 700,
      background: s.bg, color: s.color, border: `1px solid ${s.border}`,
    }}>
      {status?.replace(/_/g, ' ')}
    </span>
  );
}

function ScoreBar({ score }) {
  const color = score >= 90 ? '#16a34a' : score >= 70 ? '#d97706' : score >= 50 ? '#ea580c' : '#dc2626';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, background: '#e2e8f0', borderRadius: 99, height: 6, overflow: 'hidden', minWidth: 60 }}>
        <div style={{ width: `${score}%`, height: '100%', background: color, transition: 'width 0.4s' }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 700, color, minWidth: 32 }}>{score}</span>
    </div>
  );
}

export default function BidWorkspacePage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryTenderId = searchParams.get('tenderId') || '';

  const [tenders, setTenders] = useState([]);
  const [selectedTenderId, setSelectedTenderId] = useState(queryTenderId);
  const [tender, setTender] = useState(null);
  const [bids, setBids] = useState([]);
  const [loading, setLoading] = useState(false);
  const [evaluating, setEvaluating] = useState({});
  const [expandedBid, setExpandedBid] = useState(null);
  const [banner, setBanner] = useState(null);
  const [isMobile, setIsMobile] = useState(typeof window !== 'undefined' ? window.innerWidth <= 880 : false);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 880);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const loadData = useCallback(async (targetTenderId) => {
    setLoading(true);
    try {
      // 1. Fetch all tenders for dropdown
      const tendersRes = await listTenders().catch(() => null);
      const tenderList = tendersRes?.tenders || (Array.isArray(tendersRes) ? tendersRes : []);
      setTenders(tenderList);

      const activeId = targetTenderId !== undefined ? targetTenderId : selectedTenderId;

      if (activeId) {
        // Find matching tender object
        const matched = tenderList.find(t =>
          (t.id && t.id === activeId) ||
          (t._id && t._id === activeId) ||
          (t.tender_no && t.tender_no === activeId) ||
          (t.reference_number && t.reference_number === activeId)
        );
        setTender(matched || { id: activeId, reference_number: activeId, title: `Tender ${activeId}` });

        // Fetch bids strictly for this tender
        const bidsRes = await getTenderBids(activeId).catch(() => null);
        const list = bidsRes?.bids || (Array.isArray(bidsRes) ? bidsRes : []);
        if (Array.isArray(list)) {
          setBids(list);
        } else {
          setBids([]);
        }
      } else {
        // No specific tender selected: load all bids
        setTender(null);
        const bidsRes = await listBids().catch(() => null);
        const list = bidsRes?.bids || (Array.isArray(bidsRes) ? bidsRes : []);
        if (Array.isArray(list)) {
          setBids(list);
        } else {
          setBids([]);
        }
      }
    } finally {
      setLoading(false);
    }
  }, [selectedTenderId]);

  useEffect(() => {
    setSelectedTenderId(queryTenderId);
    loadData(queryTenderId);
  }, [queryTenderId, loadData]);

  function handleTenderSelect(e) {
    const nextId = e.target.value;
    setSelectedTenderId(nextId);
    if (nextId) {
      setSearchParams({ tenderId: nextId });
    } else {
      setSearchParams({});
    }
  }

  async function runEval(bid) {
    setEvaluating(prev => ({ ...prev, [bid.id]: true }));
    setBanner(null);
    try {
      const result = await evaluateBid(bid.id).catch(() => null);
      if (result) {
        setBids(prev => prev.map(b => b.id === bid.id
          ? { ...b, ...result, overall_status: result.overall_status || b.overall_status }
          : b
        ));
        setBanner({ type: 'success', msg: `✓ Evaluation complete for ${bid.bidder?.name || bid.bidder_name}: ${result.overall_status}` });
      } else {
        setBanner({ type: 'warning', msg: `Offline mode: evaluation not committed. Current status shown.` });
      }
    } catch {
      setBanner({ type: 'error', msg: 'Evaluation failed.' });
    } finally {
      setEvaluating(prev => ({ ...prev, [bid.id]: false }));
    }
  }

  const total = bids.length;
  const passCount = bids.filter(b => ['PASS', 'COMPLIANT'].includes(b.overall_status || b.compliance_status)).length;
  const failCount = bids.filter(b => ['FAIL', 'NON_COMPLIANT'].includes(b.overall_status || b.compliance_status)).length;
  const reviewCount = bids.filter(b => ['REVIEW', 'UNDER_REVIEW'].includes(b.overall_status || b.compliance_status)).length;

  return (
    <div style={{
      minHeight: 'calc(100vh - 54px)', background: '#f8fafc', fontFamily: "'Inter', sans-serif",
      padding: isMobile ? '14px 12px' : '24px 28px', maxWidth: 1400, margin: '0 auto',
      width: '100%', maxWidth: '100vw', overflowX: 'hidden', boxSizing: 'border-box'
    }}>

      {/* ─── Header & Tender Filter Selector ─────────────────────────────────── */}
      <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: isMobile ? '16px 14px' : '20px 24px', marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <span style={{ fontSize: 10, fontWeight: 800, padding: '3px 10px', borderRadius: 6, background: '#dbeafe', color: '#1d4ed8', border: '1px solid #93c5fd', letterSpacing: '0.06em' }}>
            🔵 TECHNICAL EVALUATOR
          </span>
          <h1 style={{ margin: '6px 0 2px', fontSize: isMobile ? 18 : 22, fontWeight: 800, color: '#0f172a' }}>Bid Compliance Matrix</h1>
          <p style={{ margin: 0, fontSize: 12, color: '#64748b' }}>
            {tender ? `${tender.reference_number || tender.tender_no || tender.title}` : 'All Procurement Tenders'}
            {' '}· <strong style={{ color: '#0f172a' }}>{total}</strong> bids received for this scope
          </p>
        </div>

        {/* Tender Scoping Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', width: isMobile ? '100%' : 'auto' }}>
          <div style={{ width: isMobile ? '100%' : 'auto' }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#475569', display: 'block', marginBottom: 4 }}>
              Active Tender Scope:
            </label>
            <select
              value={selectedTenderId}
              onChange={handleTenderSelect}
              style={{
                padding: '8px 12px', borderRadius: 8, border: '1.5px solid #cbd5e1',
                fontSize: 12, fontWeight: 700, background: '#fff', color: '#0f172a',
                width: isMobile ? '100%' : 'auto', minWidth: isMobile ? 0 : 280, maxWidth: '100%',
                cursor: 'pointer', outline: 'none', boxSizing: 'border-box',
              }}
            >
              <option value="">🌐 All Tenders Combined ({tenders.length} total)</option>
              {tenders.map(t => {
                const tId = t.id || t._id || t.tender_no;
                const ref = t.reference_number || t.tender_no || t.title;
                return (
                  <option key={tId} value={tId}>
                    {ref} {t.title ? `— ${t.title.slice(0, 32)}…` : ''}
                  </option>
                );
              })}
            </select>
          </div>

          <button
            onClick={() => loadData(selectedTenderId)}
            disabled={loading}
            style={{
              padding: '8px 16px', borderRadius: 8, border: '1px solid #e2e8f0',
              background: '#f8fafc', color: '#475569', fontSize: 12, fontWeight: 700,
              cursor: loading ? 'wait' : 'pointer', alignSelf: isMobile ? 'stretch' : 'flex-end',
              width: isMobile ? '100%' : 'auto',
            }}
          >
            {loading ? '⏳ Loading…' : '🔄 Refresh Bids'}
          </button>
        </div>
      </div>

      {/* ─── Banner ──────────────────────────────────────────────────────────── */}
      {banner && (
        <div style={{
          marginBottom: 20, padding: '12px 18px', borderRadius: 8, fontSize: 13, fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          background: banner.type === 'success' ? '#dcfce7' : banner.type === 'warning' ? '#fffbeb' : '#fee2e2',
          color: banner.type === 'success' ? '#166534' : banner.type === 'warning' ? '#92400e' : '#991b1b',
          border: `1px solid ${banner.type === 'success' ? '#86efac' : banner.type === 'warning' ? '#fde68a' : '#fca5a5'}`,
        }}>
          {banner.msg}
          <button onClick={() => setBanner(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: 18 }}>×</button>
        </div>
      )}

      {/* ─── KPI Cards ───────────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Total Bids', value: total, color: '#1e3a8a', bg: '#eff6ff', border: '#bfdbfe', icon: '📦' },
          { label: 'Compliant', value: passCount, color: '#166534', bg: '#dcfce7', border: '#86efac', icon: '✓' },
          { label: 'Require Review', value: reviewCount, color: '#92400e', bg: '#fffbeb', border: '#fde68a', icon: '⚠️' },
          { label: 'Non-Compliant', value: failCount, color: '#991b1b', bg: '#fee2e2', border: '#fca5a5', icon: '✗' },
        ].map(k => (
          <div key={k.label} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: k.bg, border: `1px solid ${k.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, flexShrink: 0 }}>
              {k.icon}
            </div>
            <div>
              <div style={{ fontSize: 22, fontWeight: 800, color: k.color, lineHeight: 1 }}>{k.value}</div>
              <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{k.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ─── Bid Matrix Table or Empty State ───────────────────────────────────── */}
      <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: '#0f172a' }}>
              Compliance Evaluation Matrix
              {tender && <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, color: '#2563eb' }}>({tender.reference_number || tender.tender_no || tender.title})</span>}
            </div>
            <div style={{ fontSize: 12, color: '#64748b' }}>
              Click any row to expand rule-level results · Click "View Evidence" for full compliance trace
            </div>
          </div>
        </div>

        {bids.length === 0 ? (
          <div style={{ padding: '56px 24px', textAlign: 'center', background: '#fafafa' }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>📭</div>
            <div style={{ fontSize: 17, fontWeight: 800, color: '#0f172a', marginBottom: 6 }}>
              No Bids Submitted Against This Tender Yet
            </div>
            <p style={{ color: '#64748b', fontSize: 13, maxWidth: 520, margin: '0 auto 20px', lineHeight: 1.5 }}>
              This procurement tender is currently published and open for bid submissions. Vendors can select this tender from the Bidder Portal to apply and submit their sealed verification documents.
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
              <button
                onClick={() => navigate('/my-bids')}
                style={{ padding: '9px 20px', borderRadius: 8, border: 'none', background: 'linear-gradient(135deg, #1e3a8a, #2563eb)', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}
              >
                Go to Bidder Portal →
              </button>
              <button
                onClick={() => navigate('/tenders')}
                style={{ padding: '9px 20px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', color: '#475569', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}
              >
                Back to Tender Workspace
              </button>
            </div>
          </div>
        ) : (
          <div className="responsive-table-wrapper">
            <table style={{ width: '100%', minWidth: 720, borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #f1f5f9', background: '#f8fafc' }}>
                  {['Code', 'Bidder', 'GSTIN', 'Turnover', 'MII %', 'Score', 'Status', 'Risk', 'Actions'].map(h => (
                    <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: '#64748b', letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
              {bids.map((b, i) => {
                const isExpanded = expandedBid === b.id;
                const status = b.overall_status || b.compliance_status;
                return (
                  <>
                    <tr
                      key={b.id}
                      style={{ borderBottom: '1px solid #f1f5f9', background: isExpanded ? '#f0f9ff' : (i % 2 === 0 ? '#fff' : '#fafafa'), cursor: 'pointer' }}
                      onClick={() => setExpandedBid(isExpanded ? null : b.id)}
                    >
                      <td style={{ padding: '12px 14px', fontWeight: 800, color: '#1e3a8a', fontSize: 14 }}>{b.bidder_code}</td>
                      <td style={{ padding: '12px 14px' }}>
                        <div style={{ fontWeight: 700, color: '#0f172a' }}>{b.bidder?.name || b.bidder_name}</div>
                        <div style={{ fontSize: 10, color: '#64748b', fontFamily: 'monospace', marginTop: 2 }}>PAN: {b.bidder?.pan || '—'}</div>
                      </td>
                      <td style={{ padding: '12px 14px', fontFamily: 'monospace', fontSize: 11, color: '#475569' }}>{b.bidder?.gstin || '—'}</td>
                      <td style={{ padding: '12px 14px', fontWeight: 700, color: (b.bidder?.turnover_cr || 0) >= 10 ? '#166534' : '#b91c1c' }}>
                        ₹{(b.bidder?.turnover_cr || 0).toFixed(1)} Cr
                      </td>
                      <td style={{ padding: '12px 14px', fontWeight: 700, color: (b.bidder?.local_content_pct || 0) >= 50 ? '#166534' : '#b91c1c' }}>
                        {(b.bidder?.local_content_pct || 0).toFixed(1)}%
                      </td>
                      <td style={{ padding: '12px 14px', minWidth: 120 }}>
                        <ScoreBar score={b.readiness_score || 0} />
                      </td>
                      <td style={{ padding: '12px 14px' }}><Pill status={status} /></td>
                      <td style={{ padding: '12px 14px' }}><Pill status={b.risk_band || 'LOW'} /></td>
                      <td style={{ padding: '12px 14px' }}>
                        <div style={{ display: 'flex', gap: 6 }} onClick={e => e.stopPropagation()}>
                          <button
                            onClick={() => runEval(b)}
                            disabled={evaluating[b.id]}
                            style={{ padding: '5px 10px', borderRadius: 6, border: '1px solid #bfdbfe', background: '#eff6ff', color: '#1d4ed8', fontSize: 11, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }}
                          >
                            {evaluating[b.id] ? '⏳ Running…' : '▶ Evaluate'}
                          </button>
                          <button
                            onClick={() => navigate(`/compliance?bidId=${b.id}`)}
                            style={{ padding: '5px 10px', borderRadius: 6, border: '1px solid #e2e8f0', background: '#f8fafc', color: '#475569', fontSize: 11, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap' }}
                          >
                            View Evidence →
                          </button>
                        </div>
                      </td>
                    </tr>

                    {/* ─── Expanded Rule-Level Results ─── */}
                    {isExpanded && (
                      <tr key={`${b.id}-expanded`}>
                        <td colSpan={9} style={{ padding: 0, background: '#f0f9ff', borderBottom: '2px solid #bfdbfe' }}>
                          <div style={{ padding: '16px 20px' }}>
                            <div style={{ fontSize: 12, fontWeight: 800, color: '#1e3a8a', marginBottom: 12 }}>
                              Rule-Level Results for {b.bidder?.name || b.bidder_name}
                            </div>

                            {/* Rule results */}
                            {(b.evaluation_results || []).length > 0 ? (
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 10, marginBottom: 14 }}>
                                {(b.evaluation_results || []).map(r => (
                                  <div key={r.rule_id} style={{
                                    background: '#fff', border: `1px solid ${STATUS_STYLE[r.status]?.border || '#e2e8f0'}`,
                                    borderLeft: `3px solid ${STATUS_STYLE[r.status]?.color || '#64748b'}`,
                                    borderRadius: 8, padding: '10px 14px',
                                  }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                      <span style={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 700, color: '#1e3a8a' }}>{r.rule_id}</span>
                                      <Pill status={r.status} />
                                    </div>
                                    <div style={{ fontSize: 11, color: '#475569' }}>{r.explanation}</div>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 12 }}>No evaluation results yet — click ▶ Evaluate to run compliance check.</div>
                            )}

                            {/* Verifications */}
                            {(b.verifications || []).length > 0 && (
                              <div style={{ marginBottom: 12 }}>
                                <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Government Registry Connectors</div>
                                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                  {(b.verifications || []).map(v => (
                                    <span key={v.source} style={{
                                      padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                                      background: STATUS_STYLE[v.status]?.bg || '#f1f5f9',
                                      color: STATUS_STYLE[v.status]?.color || '#475569',
                                      border: `1px solid ${STATUS_STYLE[v.status]?.border || '#cbd5e1'}`,
                                    }}>
                                      {v.source}: {v.status} · {v.message}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Flag / issue note */}
                            {(b.shortfall_details || b.contradiction_details || b.pending_details) && (
                              <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderLeft: '3px solid #d97706', borderRadius: 6, padding: '8px 12px', fontSize: 12, color: '#92400e' }}>
                                ⚠️ {b.shortfall_details || b.contradiction_details || b.pending_details}
                              </div>
                            )}

                            <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                              <button
                                onClick={() => navigate(`/compliance?bidId=${b.id}`)}
                                style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: 'linear-gradient(135deg, #1e3a8a, #2563eb)', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}
                              >
                                View Full Evidence & Compliance Trace →
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
        )}
      </div>

      {/* ─── Zero-LLM Notice ─────────────────────────────────────────────────── */}
      <div style={{ marginTop: 16, padding: '10px 16px', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, fontSize: 11, color: '#166534', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span>🛡️</span>
        <span><strong>Zero-LLM Evaluation:</strong> All PASS/FAIL/REVIEW decisions are computed by deterministic Pandas/Boolean rules engine. AI is used only for document entity extraction. Officers make all final decisions.</span>
      </div>
    </div>
  );
}
