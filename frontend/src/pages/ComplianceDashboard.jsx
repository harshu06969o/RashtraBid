/**
 * ComplianceDashboard — TECHNICAL_EVALUATOR & PROCUREMENT_OFFICER
 *
 * Features:
 *  - Left sidebar: real bids list with status filters (ALL / FAIL / REVIEW / PENDING / HIGH_RISK)
 *  - Right panel: deep-dive for selected bid
 *    Tab 1 — Compliance Summary: rule-level pass/fail table with officer overrides and decision recording
 *    Tab 2 — Evidence Trace: interactive clause → rule → evidence → registry verification DAG
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import ComplianceTraceView from '../components/ComplianceTraceView';
import OverrideModal from '../components/OverrideModal';
import { listBids, getBid, evaluateBid, submitOfficerAction } from '../api/client';

// ── Styles & Mapping ──────────────────────────────────────────────────────────

const RS = {
  PASS:           { color: '#166534', bg: '#dcfce7', border: '#86efac', icon: '✓' },
  FAIL:           { color: '#991b1b', bg: '#fee2e2', border: '#fca5a5', icon: '✗' },
  REVIEW:         { color: '#92400e', bg: '#fef3c7', border: '#fcd34d', icon: '⚠' },
  PENDING:        { color: '#1e40af', bg: '#dbeafe', border: '#93c5fd', icon: '⏳' },
  MISSING:        { color: '#6b21a8', bg: '#f3e8ff', border: '#c4b5fd', icon: '?' },
  EXPIRED:        { color: '#7f1d1d', bg: '#fef2f2', border: '#fca5a5', icon: '⏰' },
  NOT_APPLICABLE: { color: '#374151', bg: '#f3f4f6', border: '#d1d5db', icon: '—' },
};

const RISK_S = {
  LOW:      { color: '#166534', bg: '#dcfce7', dot: '#16a34a' },
  MEDIUM:   { color: '#92400e', bg: '#fef3c7', dot: '#d97706' },
  HIGH:     { color: '#991b1b', bg: '#fee2e2', dot: '#dc2626' },
  CRITICAL: { color: '#4a044e', bg: '#fdf4ff', dot: '#a21caf' },
};

const RULE_LABELS = {
  TURNOVER:      'Annual Turnover',
  GST_STATUS:    'GST Registration',
  UDYAM:         'Udyam / MSME',
  CERT_VALIDITY: 'Certificate Validity',
  NAME_MATCH:    'Entity Name Consistency',
  EXPERIENCE:    'Past Project Experience',
  LOCAL_CONTENT: 'Make in India Local Content',
  SOLVENCY:      'Bank Solvency Certificate',
};

// ── Mini Badges ───────────────────────────────────────────────────────────────

function ResultBadge({ result }) {
  const s = RS[result] ?? RS.REVIEW;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      padding: '2px 9px', borderRadius: 20, fontSize: 11, fontWeight: 700,
      color: s.color, background: s.bg, border: `1px solid ${s.border}`,
    }}>
      {s.icon} {result}
    </span>
  );
}

function RiskBadge({ level }) {
  const s = RISK_S[level] ?? RISK_S.LOW;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '2px 9px', borderRadius: 20, fontSize: 11, fontWeight: 700,
      color: s.color, background: s.bg,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: s.dot }} />
      {level}
    </span>
  );
}

// ── Officer Action Panel ──────────────────────────────────────────────────────

function OfficerActionPanel({ bidId, onSuccess }) {
  const [action, setAction] = useState('ACCEPT');
  const [comment, setComment] = useState('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [ok, setOk] = useState(false);

  const ACTIONS = ['ACCEPT', 'REJECT', 'SEEK_CLARIFICATION', 'MARK_PENDING'];
  const actionStyle = {
    ACCEPT:             { bg: '#dcfce7', color: '#166534' },
    REJECT:             { bg: '#fee2e2', color: '#991b1b' },
    SEEK_CLARIFICATION: { bg: '#fef3c7', color: '#92400e' },
    MARK_PENDING:       { bg: '#dbeafe', color: '#1e40af' },
  };

  async function submit() {
    setLoading(true); setErr(null); setOk(false);
    try {
      // Map UI action names to backend expected values
      const actionMap = {
        'ACCEPT': 'APPROVE',
        'REJECT': 'REJECT',
        'SEEK_CLARIFICATION': 'SEEK_CLARIFICATION',
        'MARK_PENDING': 'SEEK_CLARIFICATION',
      };
      const backendAction = actionMap[action] || action;
      const justification = comment.trim().length >= 10
        ? comment.trim()
        : `Officer recorded compliance evaluation decision: ${backendAction}.`;
      await submitOfficerAction(bidId, {
        action: backendAction,
        reason: justification,       // backend requires 'reason' not 'comment'
        actor: 'officer@gem.gov.in',
      });
      setOk(true);
      setComment('');
      if (onSuccess) onSuccess();
    } catch (e) {
      // Extract readable message from ApiError or plain error
      const msg = e?.message || (typeof e === 'object' ? JSON.stringify(e) : String(e));
      setErr(msg || 'Failed to record decision');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ background: '#f8fafc', borderRadius: 10, padding: '14px', border: '1px solid #e2e8f0', marginBottom: 16 }}>
      <div style={{ fontWeight: 700, fontSize: 12, color: '#1e3a5f', marginBottom: 10 }}>
        👤 Record Officer Decision
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
        {ACTIONS.map(a => {
          const s = actionStyle[a] ?? { bg: '#f3f4f6', color: '#374151' };
          return (
            <button
              key={a}
              id={`btn-action-${a.toLowerCase()}`}
              onClick={() => setAction(a)}
              style={{
                padding: '5px 12px', borderRadius: 8, fontSize: 11, fontWeight: 700,
                border: action === a ? `2px solid ${s.color}` : '2px solid #e2e8f0',
                background: action === a ? s.bg : '#fff',
                color: action === a ? s.color : '#64748b', cursor: 'pointer',
              }}
            >
              {a.replace(/_/g, ' ')}
            </button>
          );
        })}
      </div>
      <textarea
        id="officer-comment"
        value={comment}
        onChange={e => setComment(e.target.value)}
        placeholder="Add officer remarks or compliance verification justification…"
        rows={2}
        style={{
          width: '100%', padding: '8px 10px', border: '1.5px solid #e2e8f0',
          borderRadius: 8, fontSize: 11, resize: 'vertical', fontFamily: 'inherit',
          boxSizing: 'border-box', outline: 'none',
        }}
      />
      {err && <div style={{ color: '#991b1b', fontSize: 11, marginTop: 6 }}>⛔ {err}</div>}
      {ok  && <div style={{ color: '#166534', fontSize: 11, marginTop: 6 }}>✓ Decision successfully recorded in audit log.</div>}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 10 }}>
        <button
          id="btn-officer-submit"
          onClick={submit}
          disabled={loading}
          style={{
            padding: '7px 18px', borderRadius: 8, border: 'none',
            background: loading ? '#94a3b8' : '#1e3a5f', color: '#fff',
            fontSize: 12, fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? '⏳ Recording…' : 'Record Decision'}
        </button>
      </div>
    </div>
  );
}

// ── Summary Table ─────────────────────────────────────────────────────────────

function SummaryTable({ results, onOverride }) {
  const ORDER = { FAIL: 0, EXPIRED: 1, MISSING: 2, REVIEW: 3, PENDING: 4, PASS: 5, NOT_APPLICABLE: 6 };
  const sorted = [...results].sort((a, b) => {
    const resA = a.result || a.status || 'PENDING';
    const resB = b.result || b.status || 'PENDING';
    return (ORDER[resA] ?? 9) - (ORDER[resB] ?? 9);
  });
  const applicable = results.filter(r => (r.result || r.status) !== 'NOT_APPLICABLE');
  const counts = {
    pass: applicable.filter(r => (r.result || r.status) === 'PASS').length,
    fail: applicable.filter(r => ['FAIL', 'MISSING', 'EXPIRED'].includes(r.result || r.status)).length,
    review: applicable.filter(r => (r.result || r.status) === 'REVIEW').length,
    pending: applicable.filter(r => (r.result || r.status) === 'PENDING').length,
  };

  return (
    <div>
      {/* Summary metric cards */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
        {[
          { label: 'Rules Evaluated', value: applicable.length, color: '#1e3a5f', bg: '#f0f4ff' },
          { label: 'Passed', value: counts.pass, color: '#166534', bg: '#dcfce7' },
          { label: 'Failed', value: counts.fail, color: '#991b1b', bg: '#fee2e2' },
          { label: 'Review', value: counts.review, color: '#92400e', bg: '#fef3c7' },
          { label: 'Pending', value: counts.pending, color: '#1e40af', bg: '#dbeafe' },
        ].map(c => (
          <div key={c.label} style={{ background: c.bg, borderRadius: 8, padding: '7px 14px', textAlign: 'center', minWidth: 64 }}>
            <div style={{ fontSize: 19, fontWeight: 800, color: c.color }}>{c.value}</div>
            <div style={{ fontSize: 10, color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>{c.label}</div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid #e2e8f0' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f8fafc' }}>
              {['Requirement', 'Result', 'Explanation', 'Mandatory', 'Action'].map(h => (
                <th key={h} style={{
                  padding: '8px 12px', textAlign: 'left', fontWeight: 700,
                  fontSize: 10, color: '#64748b', textTransform: 'uppercase',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, idx) => {
              const res = r.result || r.status || 'PENDING';
              const ruleType = r.requirement_rule?.rule_type || r.metric || r.clause_id || `Rule ${idx + 1}`;
              const clauseNum = r.requirement_rule?.clause?.clause_number || r.clause_id || '';
              const explanation = r.explanation || 'Rule verified against submitted evidence & government registries.';
              const isMandatory = r.requirement_rule?.is_mandatory ?? r.is_mandatory ?? true;
              const canOverride = ['FAIL', 'REVIEW', 'PENDING', 'MISSING', 'EXPIRED'].includes(res);
              const rowBg = ['FAIL', 'MISSING', 'EXPIRED'].includes(res) ? '#fff5f5'
                : res === 'REVIEW' ? '#fffbeb'
                : res === 'PENDING' ? '#f0f9ff' : '#fff';
              const rId = r.id || r.rule_id || r.clause_id || idx;

              return (
                <tr key={rId} style={{ background: rowBg, borderTop: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '10px 12px' }}>
                    <div style={{ fontWeight: 700, color: '#1e3a5f', fontSize: 12 }}>
                      {RULE_LABELS[ruleType] ?? ruleType.replace(/_/g, ' ')}
                    </div>
                    {clauseNum && (
                      <div style={{ fontSize: 10, color: '#94a3b8' }}>Clause {clauseNum}</div>
                    )}
                  </td>
                  <td style={{ padding: '10px 12px' }}><ResultBadge result={res} /></td>
                  <td style={{ padding: '10px 12px', fontSize: 11, color: '#475569', maxWidth: 260 }}>
                    {explanation}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                    {isMandatory
                      ? <span style={{ color: '#dc2626', fontWeight: 800, fontSize: 11 }}>YES</span>
                      : <span style={{ color: '#94a3b8', fontSize: 11 }}>No</span>}
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    {canOverride && (
                      <button
                        id={`btn-override-${rId}`}
                        onClick={() => onOverride(r)}
                        style={{
                          padding: '4px 10px', borderRadius: 6, fontSize: 10, fontWeight: 700,
                          border: '1.5px solid #f59e0b', background: '#fffbeb', color: '#92400e',
                          cursor: 'pointer',
                        }}
                      >
                        ⚖️ Override
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: 24, textAlign: 'center', color: '#94a3b8', fontSize: 12 }}>
                  No evaluation rules recorded for this bid yet. Click "Re-evaluate" to run rules.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Parsed Data Panel ────────────────────────────────────────────────────────

function ParsedDataPanel({ bid }) {
  const documents = bid.documents || [];
  const comparison = bid.data_comparison || [];
  const evidence = bid.evidence || [];

  return (
    <div>
      {/* Documents list */}
      {documents.length > 0 && (
        <div style={{ marginBottom: 18 }}>
          <div style={{ fontWeight: 700, fontSize: 12, color: '#1e3a5f', marginBottom: 8 }}>
            📄 Uploaded Documents ({documents.length})
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {documents.map((d, i) => (
              <div key={d.id || i} style={{
                background: '#f0f4ff', border: '1px solid #bfdbfe', borderRadius: 8,
                padding: '6px 12px', fontSize: 11, color: '#1e3a5f', display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <span>📋</span>
                <div>
                  <div style={{ fontWeight: 700 }}>{d.original_filename || d.filename}</div>
                  <div style={{ color: '#64748b' }}>{d.doc_type || 'Unknown'} · {d.extraction_method || 'OCR'} · {d.page_count || 0} pages</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Registered vs Extracted Comparison */}
      {comparison.length > 0 && (
        <div style={{ marginBottom: 18 }}>
          <div style={{ fontWeight: 700, fontSize: 12, color: '#1e3a5f', marginBottom: 8 }}>
            🔍 Registered Profile vs. Extracted PDF Values
          </div>
          <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid #e2e8f0' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: '#f8fafc' }}>
                  {['Field', 'Registered (Profile)', 'Extracted (PDF)', 'Match'].map(h => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 700, fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {comparison.map((c, i) => (
                  <tr key={i} style={{ borderTop: '1px solid #f1f5f9', background: c.status === 'MISMATCH' ? '#fff5f5' : c.status === 'MATCH' ? '#f0fdf4' : '#fff' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 700, color: '#334155', textTransform: 'capitalize' }}>
                      {c.field.replace(/_/g, ' ')}
                    </td>
                    <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 11, color: '#1e293b' }}>
                      {c.registered_value || <span style={{ color: '#94a3b8' }}>—</span>}
                    </td>
                    <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 11, color: '#1e293b' }}>
                      {c.extracted_value || <span style={{ color: '#94a3b8', fontFamily: 'inherit' }}>Not extracted from PDF</span>}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      {c.status === 'MATCH' && <span style={{ color: '#166534', fontWeight: 800, fontSize: 11 }}>✓ MATCH</span>}
                      {c.status === 'MISMATCH' && <span style={{ color: '#991b1b', fontWeight: 800, fontSize: 11 }}>✗ MISMATCH</span>}
                      {c.status === 'NOT_EXTRACTED' && <span style={{ color: '#64748b', fontSize: 11 }}>― Not in PDF</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* All extracted entities from PDFs */}
      {evidence.length > 0 ? (
        <div>
          <div style={{ fontWeight: 700, fontSize: 12, color: '#1e3a5f', marginBottom: 8 }}>
            🧠 All PDF-Extracted Entities ({evidence.length} fields)
          </div>
          <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid #e2e8f0' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: '#f8fafc' }}>
                  {['Field', 'Extracted Value', 'Doc Type', 'Confidence', 'Method'].map(h => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 700, fontSize: 10, color: '#64748b', textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {evidence.map((ev, i) => (
                  <tr key={ev.id || i} style={{ borderTop: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '10px 12px', fontWeight: 700, color: '#334155', textTransform: 'capitalize' }}>
                      {(ev.field || ev.field_name || '').replace(/_/g, ' ')}
                    </td>
                    <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 11, fontWeight: 700, color: '#1e3a5f' }}>
                      {ev.normalized_value || ev.raw_value || '—'}
                    </td>
                    <td style={{ padding: '10px 12px', fontSize: 10, color: '#64748b' }}>
                      {ev.doc_type || '—'}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: (ev.confidence || 0) >= 0.8 ? '#166534' : '#d97706' }}>
                        {((ev.confidence || 0) * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px', fontSize: 10, color: '#64748b' }}>
                      {ev.extraction_method || 'PATTERN'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {evidence[0]?.source_snippet && (
            <div style={{ marginTop: 10, padding: '10px 14px', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 11, color: '#475569' }}>
              <div style={{ fontWeight: 700, marginBottom: 4, color: '#1e3a5f' }}>Sample Source Snippet (from PDF):</div>
              <code style={{ fontSize: 11, color: '#334155' }}>…{evidence[0].source_snippet}…</code>
            </div>
          )}
        </div>
      ) : (
        <div style={{ padding: '32px', textAlign: 'center', color: '#94a3b8', background: '#f8fafc', borderRadius: 10, border: '1px dashed #e2e8f0' }}>
          <div style={{ fontSize: 24, marginBottom: 6 }}>📂</div>
          <div style={{ fontWeight: 700, fontSize: 13, color: '#475569', marginBottom: 4 }}>No Document Entities Extracted Yet</div>
          <div style={{ fontSize: 12 }}>Ask the bidder to upload PDF documents (GST Certificate, CA Certificate, PAN Card, etc.).<br />The AI parser will automatically extract GSTIN, PAN, Turnover, Udyam No. and other fields.</div>
        </div>
      )}
    </div>
  );
}

// ── Bidder Detail Panel ────────────────────────────────────────────────────────

function BidderDetail({ bid, onRefresh }) {
  const [activeTab, setActiveTab] = useState('summary');
  const [evaluating, setEvaluating] = useState(false);
  const [overrideProps, setOverrideProps] = useState(null);

  const bidId = bid.id || bid._id;
  const results = (bid.rule_results && bid.rule_results.length > 0)
    ? bid.rule_results
    : (bid.evaluation_results || []);
  const ra = bid.risk_assessment;
  const overallStatus = bid.overall_status || bid.compliance_status || 'PENDING';
  const hasFail    = results.some(r => ['FAIL', 'MISSING', 'EXPIRED'].includes(r.result || r.status));
  const hasReview  = results.some(r => (r.result || r.status) === 'REVIEW');
  const hasPending = results.some(r => (r.result || r.status) === 'PENDING');
  const lastAction = bid.officer_actions?.[bid.officer_actions.length - 1];

  const evidence = bid.evidence || [];
  const verifications = bid.verifications || [];
  const comparison = bid.data_comparison || [];
  const documents = bid.documents || [];

  async function handleEvaluate() {
    setEvaluating(true);
    try {
      await evaluateBid(bidId);
      onRefresh();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Evaluation failed');
    } finally {
      setEvaluating(false);
    }
  }

  function openOverride(r) {
    const ruleType = r.requirement_rule?.rule_type || r.metric || r.clause_id || 'Rule';
    const res = r.result || r.status || 'FAIL';
    setOverrideProps({
      bidId: bidId,
      bidderName: bid.bidder?.name ?? bid.bidder_name ?? 'Bidder',
      ruleType: RULE_LABELS[ruleType] ?? ruleType,
      currentResult: res,
      ruleResultId: r.id || r.rule_id || r.clause_id,
    });
  }

  const TABS = [
    ['summary', '📊 Compliance Summary'],
    ['parsed', '🧾 Parsed Document Data'],
    ['connectors', '🔗 Connector Verification'],
    ['trace', '🔍 Evidence Trace'],
  ];

  return (
    <div>
      {/* Bidder header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ flex: 1 }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: '#1e3a5f' }}>
            {bid.bidder?.name ?? bid.bidder_name ?? 'Bidder'}
          </h2>
          <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
            GSTIN: {bid.bidder?.gstin || bid.gstin || '—'} · ₹{bid.bidder?.turnover_cr ?? bid.turnover_cr ?? '—'} Cr · {bid.bidder?.category || bid.category || 'General'}
          </div>
          <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
            PAN: {bid.bidder?.pan || '—'} · State: {bid.bidder?.state || '—'}
            {bid.bidder?.udyam_number && <span> · Udyam: {bid.bidder.udyam_number}</span>}
          </div>
          {lastAction && (
            <div style={{ fontSize: 10, color: '#64748b', marginTop: 3 }}>
              Last officer action: <strong>{lastAction.action}</strong> by {lastAction.officer_id || 'Officer'}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <RiskBadge level={ra?.risk_level || bid.risk_level || bid.risk_band || 'LOW'} />
          <ResultBadge result={overallStatus} />
          {bid.officer_status && bid.officer_status !== overallStatus && (
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
              background: '#e0e7ff', color: '#3730a3', border: '1px solid #a5b4fc',
            }}>
              Officer: {bid.officer_status}
            </span>
          )}
          <button
            id={`btn-evaluate-${bidId}`}
            onClick={handleEvaluate}
            disabled={evaluating}
            style={{
              background: evaluating ? '#94a3b8' : '#1e3a5f', color: '#fff',
              border: 'none', borderRadius: 8, padding: '6px 12px',
              fontSize: 11, fontWeight: 700, cursor: evaluating ? 'not-allowed' : 'pointer',
            }}
          >
            {evaluating ? '⏳ Evaluating…' : '⟳ Re-evaluate'}
          </button>
        </div>
      </div>

      {/* Exception alert banners */}
      {hasFail && (
        <div style={{
          background: '#fee2e2', border: '1.5px solid #fca5a5', borderRadius: 10,
          padding: '10px 14px', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <span style={{ fontSize: 18 }}>⛔</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, color: '#991b1b', fontSize: 12 }}>Mandatory Requirement Failed</div>
            <div style={{ fontSize: 11, color: '#7f1d1d' }}>Use Override or Evidence Trace to review the verification chain.</div>
          </div>
          <button
            onClick={() => setActiveTab('trace')}
            style={{ background: '#991b1b', color: '#fff', border: 'none', borderRadius: 6, padding: '4px 10px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}
          >
            View Trace →
          </button>
        </div>
      )}
      {hasReview && !hasFail && (
        <div style={{
          background: '#fef3c7', border: '1.5px solid #fcd34d', borderRadius: 10,
          padding: '10px 14px', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <span style={{ fontSize: 18 }}>⚠️</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, color: '#92400e', fontSize: 12 }}>Manual Review Required</div>
            <div style={{ fontSize: 11, color: '#78350f' }}>Registry values require officer verification before clearance.</div>
          </div>
        </div>
      )}
      {hasPending && !hasFail && !hasReview && (
        <div style={{
          background: '#dbeafe', border: '1.5px solid #93c5fd', borderRadius: 10,
          padding: '10px 14px', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <span style={{ fontSize: 18 }}>⏳</span>
          <div style={{ fontWeight: 800, color: '#1e40af', fontSize: 12 }}>Verification Pending — Registry connectors queried</div>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 2, marginBottom: 14, borderBottom: '2px solid #f1f5f9', flexWrap: 'wrap' }}>
        {TABS.map(([tab, label]) => (
          <button
            key={tab}
            id={`tab-${tab}-${bidId}`}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '7px 14px', fontSize: 12, fontWeight: 700,
              border: 'none', background: 'transparent', cursor: 'pointer',
              color: activeTab === tab ? '#1e3a5f' : '#94a3b8',
              borderBottom: activeTab === tab ? '2px solid #1e3a5f' : '2px solid transparent',
              marginBottom: -2,
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'summary' && (
        <>
          <OfficerActionPanel bidId={bidId} onSuccess={onRefresh} />
          <SummaryTable results={results} onOverride={openOverride} />
          {ra && (
            <div style={{
              marginTop: 12, padding: '8px 14px', background: '#f8fafc',
              borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 11, color: '#64748b',
              display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
            }}>
              <span style={{ fontWeight: 700, color: '#475569' }}>Risk Indicator</span>
              <span style={{ color: '#94a3b8' }}>— Deterministic assessment. Officer judgment prevails.</span>
              <RiskBadge level={ra.risk_level || bid.risk_level || bid.risk_band || 'LOW'} />
            </div>
          )}
        </>
      )}

      {activeTab === 'parsed' && (
        <ParsedDataPanel bid={bid} />
      )}

      {activeTab === 'connectors' && (
        <div>
          {verifications.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {verifications.map((vr, i) => {
                const status = vr.connector_status || vr.status || 'PENDING';
                const isVerified = status === 'VERIFIED';
                const isFail = status === 'NOT_VERIFIED' || status === 'MISMATCH';
                const bg = isVerified ? '#f0fdf4' : isFail ? '#fff5f5' : '#f0f9ff';
                const border = isVerified ? '#86efac' : isFail ? '#fca5a5' : '#93c5fd';
                const col = isVerified ? '#166534' : isFail ? '#991b1b' : '#1e40af';
                return (
                  <div key={vr.id || i} style={{ background: bg, border: `1.5px solid ${border}`, borderRadius: 10, padding: '14px 16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <div style={{ fontWeight: 800, fontSize: 13, color: '#1e3a5f' }}>
                        {vr.source_label || `Connector: ${vr.source}`}
                      </div>
                      <span style={{ fontSize: 11, fontWeight: 800, padding: '2px 9px', borderRadius: 12, background: bg, color: col, border: `1px solid ${border}` }}>
                        {isVerified ? '✓' : isFail ? '✗' : '⏳'} {status}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: '#475569', marginBottom: 8 }}>{vr.message}</div>
                    {vr.fields_verified && Object.keys(vr.fields_verified).length > 0 && (
                      <div style={{ background: 'rgba(255,255,255,0.7)', borderRadius: 6, padding: '8px 12px', border: '1px solid #e2e8f0' }}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', marginBottom: 4, textTransform: 'uppercase' }}>Fields Verified by Registry:</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                          {Object.entries(vr.fields_verified).map(([k, v]) => (
                            <div key={k} style={{ fontSize: 11, color: '#1e293b' }}>
                              <span style={{ color: '#64748b' }}>{k.replace(/_/g, ' ')}: </span>
                              <strong style={{ fontFamily: 'monospace' }}>{String(v)}</strong>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ padding: '32px', textAlign: 'center', color: '#94a3b8', background: '#f8fafc', borderRadius: 10, border: '1px dashed #e2e8f0' }}>
              <div style={{ fontSize: 24, marginBottom: 6 }}>🔗</div>
              <div style={{ fontWeight: 700, fontSize: 13, color: '#475569', marginBottom: 4 }}>No Connector Verifications Run Yet</div>
              <div style={{ fontSize: 12 }}>Click "Re-evaluate" to trigger GSTN, PAN, UDYAM, EPFO, MCA21, and DPIIT connector checks.</div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'trace' && (
        <ComplianceTraceView bidId={bidId} bidderName={bid.bidder?.name ?? bid.bidder_name ?? 'Bidder'} />
      )}

      {/* Override modal */}
      {overrideProps && (
        <OverrideModal
          {...overrideProps}
          onClose={() => setOverrideProps(null)}
          onSuccess={() => { onRefresh(); }}
        />
      )}
    </div>
  );
}

// ── Main Dashboard ─────────────────────────────────────────────────────────────

export default function ComplianceDashboard() {
  const [bids, setBids] = useState([]);
  const [selectedBid, setSelectedBid] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [filter, setFilter] = useState('ALL');
  const [error, setError] = useState(null);
  const [searchParams] = useSearchParams();
  const [mobileTab, setMobileTab] = useState('LIST');
  const [isMobile, setIsMobile] = useState(typeof window !== 'undefined' ? window.innerWidth <= 768 : false);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const loadBids = useCallback(async () => {
    setError(null);
    try {
      const data = await listBids();
      setBids(data);
      // Auto-select if bid query param exists or first bid
      const targetBidId = searchParams.get('bid_id');
      if (targetBidId) {
        const found = data.find(b => (b.id || b._id) === targetBidId);
        if (found) {
          selectBid(found);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load bids');
    } finally {
      setLoading(false);
    }
  }, [searchParams]);

  useEffect(() => { loadBids(); }, [loadBids]);

  async function selectBid(bid) {
    setDetailLoading(true);
    if (typeof window !== 'undefined' && window.innerWidth <= 768) {
      setMobileTab('DETAIL');
    }
    try {
      const bId = bid.id || bid._id;
      const data = await getBid(bId);
      setSelectedBid(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load bid details');
    } finally {
      setDetailLoading(false);
    }
  }

  async function refreshSelected() {
    if (!selectedBid) return;
    try {
      const bId = selectedBid.id || selectedBid._id;
      const data = await getBid(bId);
      setSelectedBid(data);
    } catch {
      // ignore
    }
    await loadBids();
  }

  const filteredBids = bids.filter(bid => {
    const risk = bid.risk_level || bid.risk_band || 'LOW';
    const status = bid.overall_status || bid.compliance_status || 'PENDING';
    if (filter === 'ALL') return true;
    if (filter === 'FAIL') return status === 'FAIL';
    if (filter === 'REVIEW') return status === 'REVIEW';
    if (filter === 'PENDING') return status === 'PENDING';
    if (filter === 'HIGH_RISK') return risk === 'HIGH' || risk === 'CRITICAL';
    return true;
  });

  const FILTERS = [
    { key: 'ALL', label: 'All' },
    { key: 'FAIL', label: '⛔ Fail' },
    { key: 'REVIEW', label: '⚠ Review' },
    { key: 'PENDING', label: '⏳ Pending' },
    { key: 'HIGH_RISK', label: '🔴 High Risk' },
  ];

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh', flexDirection: 'column', gap: 10, color: '#94a3b8' }}>
      <div style={{ fontSize: 32 }}>⏳</div>
      <div style={{ fontSize: 14, fontWeight: 600 }}>Loading compliance intelligence data…</div>
    </div>
  );

  if (error && bids.length === 0) return (
    <div style={{ padding: 32 }}>
      <div style={{ background: '#fee2e2', borderRadius: 12, padding: '20px 24px', border: '1px solid #fca5a5', maxWidth: 480 }}>
        <div style={{ fontWeight: 800, color: '#991b1b', fontSize: 14, marginBottom: 6 }}>⚠ Backend Connection Error</div>
        <div style={{ color: '#7f1d1d', fontSize: 13, marginBottom: 12 }}>{error}</div>
        <button
          onClick={() => { setLoading(true); loadBids(); }}
          style={{ background: '#991b1b', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 18px', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}
        >
          ⟳ Retry
        </button>
      </div>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', height: 'calc(100vh - 54px)', overflow: 'hidden', width: '100%', maxWidth: '100vw', boxSizing: 'border-box' }}>
      {/* Mobile Tab Toggle Bar */}
      {isMobile && (
        <div style={{ display: 'flex', background: '#0f172a', borderBottom: '1px solid #1e293b', flexShrink: 0 }}>
          <button
            onClick={() => setMobileTab('LIST')}
            style={{
              flex: 1, padding: '12px 14px', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 700,
              background: mobileTab === 'LIST' ? '#1e293b' : 'transparent',
              color: mobileTab === 'LIST' ? '#FBBF24' : '#94A3B8',
              borderBottom: mobileTab === 'LIST' ? '2px solid #FF9900' : '2px solid transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            }}
          >
            📋 Bidders ({filteredBids.length})
          </button>
          <button
            onClick={() => setMobileTab('DETAIL')}
            style={{
              flex: 1, padding: '12px 14px', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 700,
              background: mobileTab === 'DETAIL' ? '#1e293b' : 'transparent',
              color: mobileTab === 'DETAIL' ? '#FBBF24' : '#94A3B8',
              borderBottom: mobileTab === 'DETAIL' ? '2px solid #FF9900' : '2px solid transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            }}
          >
            🔍 Details {selectedBid ? `(${selectedBid.bidder_code || '1'})` : ''}
          </button>
        </div>
      )}

      {/* Left: Bidder list */}
      {(!isMobile || mobileTab === 'LIST') && (
        <div style={{
          width: isMobile ? '100%' : 320,
          flexShrink: 0,
          borderRight: isMobile ? 'none' : '1px solid #e2e8f0',
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden', background: '#fff',
          height: isMobile ? '100%' : 'auto',
        }}>
          <div style={{ padding: '12px 14px', borderBottom: '1px solid #f1f5f9' }}>
            <div style={{ fontWeight: 800, fontSize: 13, color: '#1e3a5f' }}>Compliance Trace & Review</div>
            <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 1 }}>
              {selectedBid?.tender_reference || selectedBid?.tender_id ? `Tender: ${selectedBid.tender_reference || selectedBid.tender_id}` : 'Technical Verification'}
            </div>
          </div>
          <div style={{ padding: '6px 10px', display: 'flex', gap: 4, flexWrap: 'wrap', borderBottom: '1px solid #f1f5f9' }}>
            {FILTERS.map(f => (
              <button
                key={f.key}
                id={`filter-${f.key.toLowerCase()}`}
                onClick={() => setFilter(f.key)}
                style={{
                  padding: '3px 7px', borderRadius: 20, fontSize: 10, fontWeight: 700,
                  border: filter === f.key ? '1.5px solid #1e3a5f' : '1.5px solid #e2e8f0',
                  background: filter === f.key ? '#1e3a5f' : '#fff',
                  color: filter === f.key ? '#fff' : '#64748b', cursor: 'pointer',
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {filteredBids.map((bid, idx) => {
              const bId = bid.id || bid._id || String(idx);
              const risk = bid.risk_level || bid.risk_band || 'LOW';
              const riskS = RISK_S[risk] ?? RISK_S.LOW;
              const status = bid.overall_status || bid.compliance_status || 'PENDING';
              const statusS = RS[status] ?? RS.PENDING;
              const isSelected = (selectedBid?.id || selectedBid?._id) === bId;
              const bidderName = bid.bidder?.name || bid.bidder_name || `Bid #${bId.slice(0, 8)}`;
              const turnover = bid.bidder?.turnover_cr ?? bid.turnover_cr ?? '—';
              const category = bid.bidder?.category || bid.category || 'General';

              return (
                <div
                  key={bId}
                  id={`bid-row-${bId}`}
                  onClick={() => selectBid(bid)}
                  style={{
                    padding: '11px 14px', borderBottom: '1px solid #f1f5f9', cursor: 'pointer',
                    background: isSelected ? '#f0f4ff' : '#fff',
                    borderLeft: isSelected ? '3px solid #1e3a5f' : '3px solid transparent',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 700, fontSize: 12, color: '#1e3a5f', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {bidderName}
                      </div>
                      <div style={{ fontSize: 10, color: '#64748b', marginTop: 1 }}>
                        ₹{turnover} Cr · {category}
                      </div>
                      {bid.officer_status && (
                        <div style={{ fontSize: 9, color: '#7c3aed', marginTop: 2, fontWeight: 700 }}>
                          Officer: {bid.officer_status}
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, alignItems: 'flex-end', flexShrink: 0 }}>
                      <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 20, color: riskS.color, background: riskS.bg }}>
                        ● {risk}
                      </span>
                      <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 20, color: statusS.color, background: statusS.bg }}>
                        {statusS.icon} {status}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
            {filteredBids.length === 0 && (
              <div style={{ padding: 20, textAlign: 'center', color: '#94a3b8', fontSize: 12 }}>No bids match this filter.</div>
            )}
          </div>
        </div>
      )}

      {/* Right: Detail panel */}
      {(!isMobile || mobileTab === 'DETAIL') && (
        <div style={{ flex: 1, overflowY: 'auto', padding: isMobile ? '14px 12px' : 24, background: '#f8fafc', width: isMobile ? '100%' : 'auto', boxSizing: 'border-box' }}>
          {isMobile && selectedBid && (
            <button
              onClick={() => setMobileTab('LIST')}
              style={{
                marginBottom: 12, padding: '6px 12px', borderRadius: 6,
                background: '#fff', border: '1px solid #cbd5e1', color: '#1e3a5f',
                fontSize: 12, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
              }}
            >
              ← Back to Bidders List
            </button>
          )}
          {detailLoading ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 160, color: '#94a3b8', fontSize: 13 }}>
              ⏳ Loading bidder detail…
            </div>
          ) : selectedBid ? (
            <BidderDetail bid={selectedBid} onRefresh={refreshSelected} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '50vh', color: '#94a3b8', gap: 10, textAlign: 'center', padding: 20 }}>
              <span style={{ fontSize: 40 }}>📋</span>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Select a bidder to view compliance trace</div>
              <div style={{ fontSize: 12 }}>
                {isMobile ? 'Tap the "Bidders" tab above and pick a bidder.' : 'Click any bidder in the list to trace evidence from tender clause down to registry verification'}
              </div>
              {isMobile && (
                <button
                  onClick={() => setMobileTab('LIST')}
                  style={{ marginTop: 8, padding: '8px 16px', borderRadius: 6, background: '#1e3a5f', color: '#fff', border: 'none', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}
                >
                  View Bidders List ({filteredBids.length})
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
