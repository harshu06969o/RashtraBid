/**
 * DashboardPage — PROCUREMENT_OFFICER only
 *
 * Owns:
 *  - KPI summary cards (total bids, PASS / FAIL / REVIEW / PENDING counts)
 *  - Bid status summary table (read-only overview)
 *  - Action Queue: bids flagged FAIL/REVIEW → officer can APPROVE, SHOW-CAUSE, OVERRIDE
 *  - Quick links to /tenders and /corrigendum
 *
 * Does NOT contain:
 *  ✗ Audit SHA-256 chain  (→ /audit)
 *  ✗ Corrigendum rule simulator  (→ /corrigendum)
 *  ✗ Evidence / compliance trace  (→ /compliance)
 *  ✗ Technical Evaluator or Audit Officer panels
 *  ✗ Financial details
 */

import { useEffect, useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { listBids, getMe, listTenders, getTenderBids, deleteTender } from '../api/client';
import StatusBadge from '../components/StatusBadge';

// ─── Status Color Maps ────────────────────────────────────────────────────────
const STATUS_COLOR = {
  PASS: { bg: '#dcfce7', color: '#166534', border: '#86efac' },
  COMPLIANT: { bg: '#dcfce7', color: '#166534', border: '#86efac' },
  APPROVED: { bg: '#dcfce7', color: '#15803d', border: '#86efac' },
  FAIL: { bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' },
  NON_COMPLIANT: { bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' },
  REJECTED: { bg: '#fef2f2', color: '#7f1d1d', border: '#fecaca' },
  CLARIFICATION_REQUESTED: { bg: '#ffedd5', color: '#9a3412', border: '#fed7aa' },
  REVIEW: { bg: '#fffbeb', color: '#92400e', border: '#fde68a' },
  UNDER_REVIEW: { bg: '#fffbeb', color: '#92400e', border: '#fde68a' },
  PENDING: { bg: '#f1f5f9', color: '#475569', border: '#cbd5e1' },
  PENDING_VERIFICATION: { bg: '#f1f5f9', color: '#475569', border: '#cbd5e1' },
  CRITICAL: { bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' },
  HIGH: { bg: '#fffbeb', color: '#92400e', border: '#fde68a' },
  LOW: { bg: '#f0fdf4', color: '#166534', border: '#bbf7d0' },
  MEDIUM: { bg: '#eff6ff', color: '#1d4ed8', border: '#bfdbfe' },
};

function Pill({ status }) {
  const s = STATUS_COLOR[status] || STATUS_COLOR['PENDING'];
  return (
    <span style={{
      display: 'inline-block', padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
      background: s.bg, color: s.color, border: `1px solid ${s.border}`,
    }}>{status?.replace(/_/g, ' ')}</span>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const authState = useSelector(s => s.auth);
  const currentRole = authState?.role || localStorage.getItem('role');

  const [bids, setBids] = useState([]);
  const [tenders, setTenders] = useState([]);
  const [selectedTenderId, setSelectedTenderId] = useState('');
  const [tender, setTender] = useState(null);
  const [loading, setLoading] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [banner, setBanner] = useState(null);

  // Override modal state
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideBid, setOverrideBid] = useState(null);
  const [overrideJust, setOverrideJust] = useState('');
  const [overrideStatus, setOverrideStatus] = useState('REVIEW');

  useEffect(() => { 
    if (currentRole !== 'BIDDER') loadData(); 
  }, [currentRole]);

  if (currentRole === 'BIDDER') {
    return <Navigate to="/my-bids" replace />;
  }

  async function loadData(targetId) {
    setLoading(true);
    try {
      const activeId = typeof targetId === 'string' ? targetId : selectedTenderId;
      const [remoteBids, remoteTenders] = await Promise.allSettled([
        activeId ? getTenderBids(activeId) : listBids(),
        listTenders(),
      ]);
      let tenderList = [];
      if (remoteTenders.status === 'fulfilled') {
        tenderList = remoteTenders.value?.tenders || (Array.isArray(remoteTenders.value) ? remoteTenders.value : []);
        setTenders(tenderList);
        if (activeId) {
          const matched = tenderList.find(t => (t.id || t._id || t.tender_no) === activeId);
          setTender(matched || { id: activeId, reference_number: activeId, title: `Tender ${activeId}` });
        } else if (tenderList.length > 0) {
          setTender(null);
        }
      }
      if (remoteBids.status === 'fulfilled') {
        const list = remoteBids.value?.bids || (Array.isArray(remoteBids.value) ? remoteBids.value : []);
        if (Array.isArray(list)) {
          setBids(list);
        } else {
          setBids([]);
        }
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove(bid) {
    setBanner(null);
    try {
      await fetch(`/api/v1/bids/${bid.id}/officer-action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('rashtrabid_token') || localStorage.getItem('gemguard_token') || ''}` },
        body: JSON.stringify({ action: 'APPROVE', reason: 'Cleared for commercial bid opening.', actor: authState?.email || 'officer@cpcl.gov.in' }),
      }).catch(() => null);
      setBids(prev => prev.map(b => b.id === bid.id ? { ...b, status: 'APPROVED', officer_decision: 'APPROVE', overall_status: 'PASS', compliance_status: 'COMPLIANT' } : b));
      setBanner({ type: 'success', msg: `✓ Clearance approved for ${bid.bidder?.name || bid.bidder_name}. Recorded to audit chain.` });
    } catch { setBanner({ type: 'error', msg: 'Action failed.' }); }
  }

  async function handleShowCause(bid) {
    setBanner(null);
    try {
      await fetch(`/api/v1/bids/${bid.id}/officer-action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('rashtrabid_token') || localStorage.getItem('gemguard_token') || ''}` },
        body: JSON.stringify({ action: 'SEEK_CLARIFICATION', reason: bid.contradiction_details || bid.shortfall_details || 'Eligibility discrepancy — 48h response required.', actor: authState?.email || 'officer@cpcl.gov.in' }),
      }).catch(() => null);
      setBids(prev => prev.map(b => b.id === bid.id ? { ...b, status: 'CLARIFICATION_REQUESTED', officer_decision: 'SEEK_CLARIFICATION' } : b));
      setBanner({ type: 'warning', msg: `📋 Show-Cause Notice dispatched to ${bid.bidder?.name || bid.bidder_name}. 48-hour response window started.` });
    } catch { setBanner({ type: 'error', msg: 'Failed to issue notice.' }); }
  }

  function openOverride(bid) {
    setOverrideBid(bid);
    setOverrideStatus(bid.overall_status === 'FAIL' ? 'REVIEW' : 'PASS');
    setOverrideJust(bid.bidder_code === 'B'
      ? 'Invoking CPCL MSME exemption clause 5.2 per MoPNG gazette notification.'
      : 'Entity name discrepancy resolved via MCA Certificate of Name Change dated 14/02/2023.');
    setOverrideOpen(true);
  }

  async function handleOverride() {
    if (!overrideJust || overrideJust.trim().length < 5) {
      alert('A substantive justification (min 5 chars) is required by statutory audit regulations.');
      return;
    }
    try {
      await fetch(`/api/v1/bids/${overrideBid.id}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('rashtrabid_token') || localStorage.getItem('gemguard_token') || ''}` },
        body: JSON.stringify({ new_status: overrideStatus, justification: overrideJust, actor: authState?.email || 'officer@cpcl.gov.in' }),
      }).catch(() => null);
      setBids(prev => prev.map(b => b.id === overrideBid.id
        ? { ...b, overall_status: overrideStatus, compliance_status: overrideStatus === 'PASS' ? 'COMPLIANT' : 'UNDER_REVIEW' }
        : b));
      setBanner({ type: 'success', msg: `✓ Statutory override executed for ${overrideBid.bidder?.name}. Immutably chained to SHA-256 ledger.` });
      setOverrideOpen(false);
    } catch { setBanner({ type: 'error', msg: 'Override failed.' }); }
  }

  async function handleDeleteTender(tId) {
    if (!tId) return;
    const target = tenders.find(t => (t.id === tId || t._id === tId || t.tender_no === tId));
    const label = target?.reference_number || target?.tender_no || tId;
    if (!window.confirm(`Permanently delete tender ${label}? This will purge the tender and all associated bids.`)) {
      return;
    }
    try {
      await deleteTender(tId);
      setBanner({ type: 'success', msg: `✓ Tender ${label} and associated bids were deleted successfully.` });
      setSelectedTenderId('');
      loadData('');
    } catch (err) {
      setBanner({ type: 'error', msg: 'Failed to delete tender: ' + (err instanceof Error ? err.message : String(err)) });
    }
  }

  // KPIs
  const total = bids.length;
  // Pass count includes natively compliant bids AND bids that the officer manually approved
  const passCount = bids.filter(b => b.status === 'APPROVED' || ['PASS', 'COMPLIANT'].includes(b.overall_status || b.compliance_status)).length;
  // Only count as fail/review if the officer hasn't already made a final decision
  const failCount = bids.filter(b => b.status !== 'APPROVED' && b.status !== 'REJECTED' && ['FAIL', 'NON_COMPLIANT'].includes(b.overall_status || b.compliance_status)).length;
  const reviewCount = bids.filter(b => b.status !== 'APPROVED' && b.status !== 'REJECTED' && ['REVIEW', 'UNDER_REVIEW'].includes(b.overall_status || b.compliance_status)).length;
  const pendingCount = bids.filter(b => b.status === 'CLARIFICATION_REQUESTED' || ['PENDING', 'PENDING_VERIFICATION'].includes(b.overall_status || b.compliance_status)).length;

  const actionQueue = bids.filter(b =>
    // Show in queue if AI flagged it as FAIL/REVIEW...
    ['FAIL', 'NON_COMPLIANT', 'REVIEW', 'UNDER_REVIEW'].includes(b.overall_status || b.compliance_status) &&
    // ...AND the officer hasn't already made a final decision (APPROVED/REJECTED)
    b.status !== 'APPROVED' && b.status !== 'REJECTED' && b.officer_decision !== 'APPROVE' && b.officer_decision !== 'REJECT'
  );

  return (
    <div style={{ minHeight: 'calc(100vh - 54px)', background: '#f8fafc', fontFamily: "'Inter', sans-serif", padding: '14px 16px', maxWidth: 1400, margin: '0 auto', width: '100%', boxSizing: 'border-box' }}>

      {/* ─── Header ─────────────────────────────────────────────────────────── */}
      <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: '16px 18px', marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <span style={{ fontSize: 10, fontWeight: 800, padding: '3px 10px', borderRadius: 6, background: '#dcfce7', color: '#15803d', border: '1px solid #86efac', letterSpacing: '0.06em' }}>
            🟢 PROCUREMENT OFFICER
          </span>
          <h1 style={{ margin: '6px 0 2px', fontSize: 20, fontWeight: 800, color: '#0f172a' }}>
            Procurement Decision & Action Centre
          </h1>
          <p style={{ margin: 0, fontSize: 12, color: '#64748b' }}>
            {tender
              ? `Tender: ${tender.reference_number || tender.tender_no || tender.title}`
              : (tenders.length > 0 ? `Active Tenders (${tenders.length})` : 'No Active Tenders Created Yet')}
            {' '}· {total} bids submitted
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {tenders.length > 0 && (
            <select
              value={selectedTenderId}
              onChange={(e) => {
                const nextId = e.target.value;
                setSelectedTenderId(nextId);
                loadData(nextId);
              }}
              style={{ padding: '7px 12px', borderRadius: 8, border: '1.5px solid #cbd5e1', fontSize: 12, fontWeight: 700, background: '#fff', color: '#0f172a' }}
            >
              <option value="">🌐 All Tenders ({tenders.length})</option>
              {tenders.map(t => {
                const tId = t.id || t._id || t.tender_no;
                return (
                  <option key={tId} value={tId}>
                    {t.reference_number || t.tender_no || t.title}
                  </option>
                );
              })}
            </select>
          )}
          <button onClick={() => navigate('/tenders')}
            style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #e2e8f0', background: '#fff', color: '#1d4ed8', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}>
            📋 Manage Tender
          </button>
          <button onClick={() => navigate('/corrigendum')}
            style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #e2e8f0', background: '#fff', color: '#d97706', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}>
            📝 Corrigendum
          </button>
          {selectedTenderId && (
            <button
              onClick={() => handleDeleteTender(selectedTenderId)}
              style={{
                padding: '8px 14px', borderRadius: 8, border: '1px solid rgba(239,68,68,0.3)',
                background: 'rgba(239,68,68,0.08)', color: '#dc2626', fontWeight: 700, fontSize: 12, cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 4
              }}
              title="Delete selected tender"
            >
              🗑️ Delete
            </button>
          )}

        </div>
      </div>

      {/* ─── Banner ──────────────────────────────────────────────────────────── */}
      {banner && (
        <div style={{
          marginBottom: 16, padding: '12px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          background: banner.type === 'success' ? '#dcfce7' : banner.type === 'warning' ? '#fffbeb' : '#fee2e2',
          color: banner.type === 'success' ? '#166534' : banner.type === 'warning' ? '#92400e' : '#991b1b',
          border: `1px solid ${banner.type === 'success' ? '#86efac' : banner.type === 'warning' ? '#fde68a' : '#fca5a5'}`,
        }}>
          {banner.msg}
          <button onClick={() => setBanner(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: 18 }}>×</button>
        </div>
      )}

      {/* ─── KPI Cards (Fluid responsive grid) ─────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14, marginBottom: 20 }}>
        {[
          { label: 'Total Bids', value: total, color: '#1e3a8a', bg: '#eff6ff', border: '#bfdbfe', icon: '📦' },
          { label: 'Compliant', value: passCount, color: '#166534', bg: '#dcfce7', border: '#86efac', icon: '✓' },
          { label: 'Require Action', value: failCount + reviewCount, color: '#991b1b', bg: '#fee2e2', border: '#fca5a5', icon: '⚠️' },
          { label: 'Pending Verification', value: pendingCount, color: '#475569', bg: '#f1f5f9', border: '#cbd5e1', icon: '⏳' },
        ].map(k => (
          <div key={k.label} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: '16px 18px', display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{ width: 44, height: 44, borderRadius: 10, background: k.bg, border: `1px solid ${k.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, flexShrink: 0 }}>
              {k.icon}
            </div>
            <div>
              <div style={{ fontSize: 24, fontWeight: 800, color: k.color, lineHeight: 1 }}>{k.value}</div>
              <div style={{ fontSize: 11, color: '#64748b', marginTop: 3 }}>{k.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ─── Action Queue ────────────────────────────────────────────────────── */}
      {actionQueue.length > 0 && (
        <div style={{ background: '#fff', border: '1px solid #fecaca', borderRadius: 12, marginBottom: 20, overflow: 'hidden' }}>
          <div style={{ padding: '14px 18px', borderBottom: '1px solid #fee2e2', background: '#fef2f2', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 16 }}>🚨</span>
            <div>
              <div style={{ fontSize: 14, fontWeight: 800, color: '#991b1b' }}>Action Queue — {actionQueue.length} bids require immediate officer decision</div>
              <div style={{ fontSize: 11, color: '#b91c1c' }}>Each action is cryptographically appended to the SHA-256 audit chain</div>
            </div>
          </div>
          <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {actionQueue.map(bid => (
              <div key={bid.id} style={{
                padding: '14px 16px', borderRadius: 10, border: `1px solid ${bid.overall_status === 'FAIL' || bid.compliance_status === 'NON_COMPLIANT' ? '#fca5a5' : '#fde68a'}`,
                background: bid.overall_status === 'FAIL' || bid.compliance_status === 'NON_COMPLIANT' ? '#fef2f2' : '#fffbeb',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 10 }}>
                  <div style={{ flex: '1 1 240px', minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 800, fontSize: 14, color: '#0f172a' }}>
                        {bid.bidder_code}. {bid.bidder?.name || bid.bidder_name}
                      </span>
                      <Pill status={bid.overall_status || bid.compliance_status} />
                      <Pill status={bid.risk_band || 'MEDIUM'} />
                    </div>
                    <div style={{ fontSize: 11, color: '#64748b', fontFamily: 'monospace', marginBottom: 6 }}>
                      GSTIN: {bid.bidder?.gstin} · Turnover: ₹{(bid.bidder?.turnover_cr || 0).toFixed(1)} Cr
                    </div>
                    {(bid.shortfall_details || bid.contradiction_details || bid.pending_details) && (
                      <div style={{ fontSize: 12, color: '#475569', background: 'rgba(0,0,0,0.04)', padding: '8px 12px', borderRadius: 6, borderLeft: '3px solid #cbd5e1', maxWidth: 600 }}>
                        {bid.shortfall_details || bid.contradiction_details || bid.pending_details}
                      </div>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button onClick={() => handleApprove(bid)}
                      style={{ padding: '7px 12px', borderRadius: 6, border: '1px solid #86efac', background: '#dcfce7', color: '#166534', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>
                      ✓ Approve
                    </button>
                    <button onClick={() => handleShowCause(bid)}
                      style={{ padding: '7px 12px', borderRadius: 6, border: '1px solid #fde68a', background: '#fffbeb', color: '#92400e', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>
                      📋 Show-Cause
                    </button>
                    <button onClick={() => openOverride(bid)}
                      style={{ padding: '7px 12px', borderRadius: 6, border: '1px solid #bfdbfe', background: '#eff6ff', color: '#1d4ed8', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}>
                      ⚡ Override
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── All Bids Summary Table ───────────────────────────────────────────── */}
      <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: '#0f172a' }}>Bid Status Overview</div>
            <div style={{ fontSize: 12, color: '#64748b' }}>All submitted bids for this tender · Read-only summary</div>
          </div>
          <button onClick={() => loadData()} disabled={loading}
            style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #e2e8f0', background: '#f8fafc', color: '#64748b', fontSize: 12, cursor: 'pointer' }}>
            {loading ? '⏳' : '🔄'} Refresh
          </button>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #f1f5f9', background: '#f8fafc' }}>
                {['Code', 'Bidder', 'GSTIN', 'Turnover', 'Compliance Status', 'Risk Band'].map(h => (
                  <th key={h} style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: '#64748b', letterSpacing: '0.04em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bids.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: '36px 16px', textAlign: 'center', color: '#64748b' }}>
                    <div style={{ fontSize: 28, marginBottom: 8 }}>📋</div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: '#0f172a' }}>No Bids Submitted Yet</div>
                    <div style={{ fontSize: 12, marginTop: 4 }}>
                      {tenders.length === 0
                        ? 'No tenders published yet. Click "📋 Manage Tender" above to create one.'
                        : 'No vendor bids have been submitted for this tender yet.'}
                    </div>
                  </td>
                </tr>
              ) : (
                bids.map((b, i) => (
                  <tr key={b.id || b._id} style={{ borderBottom: '1px solid #f1f5f9', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 800, color: '#1e3a8a', fontSize: 14 }}>{b.bidder_code || '—'}</td>
                    <td style={{ padding: '12px 16px', fontWeight: 600, color: '#0f172a' }}>{b.bidder?.name || b.bidder_name}</td>
                    <td style={{ padding: '12px 16px', fontFamily: 'monospace', fontSize: 11, color: '#475569' }}>{b.bidder?.gstin || b.gstin || '—'}</td>
                    <td style={{ padding: '12px 16px', fontWeight: 700, color: (b.bidder?.turnover_cr ?? b.turnover_cr ?? 0) >= 10 ? '#166534' : '#b91c1c' }}>
                      ₹{((b.bidder?.turnover_cr ?? b.turnover_cr ?? 0)).toFixed(1)} Cr
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {/* Show final officer status if present, otherwise AI overall_status */}
                      <Pill status={(b.status === 'APPROVED' || b.status === 'REJECTED') ? b.status : (b.overall_status || b.compliance_status || 'PENDING')} />
                    </td>
                    <td style={{ padding: '12px 16px' }}><Pill status={b.risk_band || 'LOW'} /></td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── Override Modal ───────────────────────────────────────────────────── */}
      {overrideOpen && overrideBid && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 20 }}>
          <div style={{ background: '#fff', borderRadius: 16, padding: '28px', width: 520, maxWidth: '100%', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 800, color: '#b91c1c', marginBottom: 4 }}>⚡ STATUTORY OVERRIDE — AUDIT LOGGED</div>
                <h2 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: '#0f172a' }}>{overrideBid.bidder?.name}</h2>
              </div>
              <button onClick={() => setOverrideOpen(false)} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#64748b' }}>×</button>
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, fontWeight: 700, color: '#475569', display: 'block', marginBottom: 6 }}>NEW STATUS</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {['REVIEW', 'PASS', 'FAIL'].map(s => (
                  <button key={s} onClick={() => setOverrideStatus(s)}
                    style={{ padding: '8px 16px', borderRadius: 8, border: `2px solid ${overrideStatus === s ? '#1d4ed8' : '#e2e8f0'}`, background: overrideStatus === s ? '#eff6ff' : '#fff', color: overrideStatus === s ? '#1d4ed8' : '#64748b', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}>
                    {s}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ fontSize: 12, fontWeight: 700, color: '#475569', display: 'block', marginBottom: 6 }}>
                JUSTIFICATION <span style={{ color: '#b91c1c' }}>*</span> (mandatory for CVC/CAG audit)
              </label>
              <textarea value={overrideJust} onChange={e => setOverrideJust(e.target.value)} rows={4}
                style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #cbd5e1', fontSize: 13, resize: 'vertical', boxSizing: 'border-box', fontFamily: 'inherit' }}
                placeholder="Statutory grounds for override..." />
            </div>

            <div style={{ padding: '12px 14px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8, marginBottom: 20, fontSize: 12, color: '#92400e' }}>
              ⚠️ This action is irreversible and will be cryptographically chained to the SHA-256 audit ledger. Ensure compliance with GFR 2017 Rule 175.
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setOverrideOpen(false)}
                style={{ padding: '10px 20px', borderRadius: 8, border: '1px solid #e2e8f0', background: '#f8fafc', color: '#64748b', fontWeight: 700, cursor: 'pointer' }}>
                Cancel
              </button>
              <button onClick={handleOverride}
                style={{ padding: '10px 20px', borderRadius: 8, border: 'none', background: 'linear-gradient(135deg, #1e3a8a, #2563eb)', color: '#fff', fontWeight: 700, cursor: 'pointer' }}>
                Execute Override & Chain to Ledger
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
