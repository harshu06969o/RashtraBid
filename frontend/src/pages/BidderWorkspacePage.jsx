/**
 * BidderWorkspacePage v4 -- RashtraBid Vendor Portal
 * Clean, guided UX. 2 tabs: Browse Tenders | My Applications
 */
import { useEffect, useState } from 'react';
import { useSelector } from 'react-redux';
import { getMyProfile, getMyBids, listTenders, submitBid, uploadBidderDocument, listBidDocuments, evaluateBid, runVerification } from '../api/client';
import { UploadCloud, FileText, CheckCircle2, AlertTriangle, RefreshCw, ShieldCheck, Eye, Send, ChevronDown, ChevronUp, X, FileCheck, Loader2 } from 'lucide-react';

const RULE_ICON = {
  TURNOVER: '💰', GST_STATUS: '🏛️', UDYAM: '🏭', MAKE_IN_INDIA: '🇮🇳',
  NAME_MATCH: '📋', EPFO_COMPLIANCE: '👷', OEM_AUTHORIZATION: '🔑',
  ISO_9001_CERT: '✅', DEBARMENT_DECLARATION: '📜', DEFAULT: '📄',
};
const SEV_COLOR = { CRITICAL: '#dc2626', HIGH: '#d97706', MEDIUM: '#2563eb', LOW: '#64748b' };

function Chip({ children, c = '#475569', bg = '#f1f5f9', b = '#cbd5e1' }) {
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 8px', borderRadius: 20, fontSize: 11, fontWeight: 700, background: bg, color: c, border: `1px solid ${b}`, whiteSpace: 'nowrap' }}>{children}</span>;
}

function SBadge({ status }) {
  const m = {
    PASS: ['#166534', '#dcfce7', '#86efac', '✓ PASS'],
    COMPLIANT: ['#166534', '#dcfce7', '#86efac', '✓ COMPLIANT'],
    APPROVED: ['#15803d', '#dcfce7', '#86efac', '⭐ APPROVED'],
    FAIL: ['#991b1b', '#fee2e2', '#fca5a5', '✗ NON-COMPLIANT'],
    NON_COMPLIANT: ['#991b1b', '#fee2e2', '#fca5a5', '✗ NON-COMPLIANT'],
    REJECTED: ['#7f1d1d', '#fef2f2', '#fecaca', '🚫 REJECTED'],
    CLARIFICATION_REQUESTED: ['#9a3412', '#ffedd5', '#fed7aa', '📋 SHOW-CAUSE'],
    REVIEW: ['#92400e', '#fffbeb', '#fde68a', '⚠ REVIEW'],
    UNDER_REVIEW: ['#92400e', '#fffbeb', '#fde68a', '⚠ UNDER REVIEW'],
    PENDING: ['#475569', '#f1f5f9', '#cbd5e1', '· PENDING'],
    HIGH: ['#991b1b', '#fee2e2', '#fca5a5', '⚠ HIGH RISK'],
    MEDIUM: ['#92400e', '#fffbeb', '#fde68a', '⚠ MED RISK'],
    LOW: ['#166534', '#dcfce7', '#86efac', '✓ LOW RISK'],
  };
  const [c, bg, b, t] = m[(status || '').toUpperCase()] || m.PENDING;
  return <Chip c={c} bg={bg} b={b}>{t}</Chip>;
}

const DOC_GUIDE = [
  { doc: 'CA Turnover Certificate', desc: '3-year avg turnover, signed by Chartered Accountant' },
  { doc: 'GST Registration Certificate', desc: 'Active GSTN on bid date' },
  { doc: 'Udyam / MSME Certificate', desc: 'MSME registration number and status' },
  { doc: 'PAN Card Copy', desc: 'PAN matching registered legal entity name' },
  { doc: 'OEM Authorization Letter', desc: 'Authorization from original equipment manufacturer' },
  { doc: 'ISO 9001 Certificate', desc: 'Quality certificate valid on bid closing date' },
  { doc: 'EPFO Evidence', desc: 'Establishment registration (if 20+ employees)' },
  { doc: 'Debarment Declaration', desc: 'Signed declaration of non-blacklisting' },
];

export default function BidderWorkspacePage() {
  const authUser = useSelector(s => s.auth?.user);
  const [profile, setProfile] = useState(null);
  const [myBids, setMyBids] = useState([]);
  const [tenders, setTenders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('TENDERS');
  const [msg, setMsg] = useState(null);
  const [detailT, setDetailT] = useState(null);
  const [applyT, setApplyT] = useState(null);
  const [bidAmt, setBidAmt] = useState('');
  const [applying, setApplying] = useState(false);
  const [expandedBid, setExpandedBid] = useState(null);
  const [bidDocs, setBidDocs] = useState({});
  const [uploading, setUploading] = useState(null);
  const [reverifying, setReverifying] = useState(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const [p, b, t] = await Promise.allSettled([getMyProfile(), getMyBids(), listTenders()]);
      if (p.status === 'fulfilled' && p.value) setProfile(p.value);
      setMyBids(b.status === 'fulfilled' ? (b.value?.bids || (Array.isArray(b.value) ? b.value : [])) : []);
      setTenders(t.status === 'fulfilled' ? (t.value?.tenders || (Array.isArray(t.value) ? t.value : [])) : []);
    } catch (e) { flash('error', 'Failed to load: ' + e.message); }
    finally { setLoading(false); }
  }

  function flash(type, text) { setMsg({ type, text }); if (type === 'success') setTimeout(() => setMsg(null), 6000); }

  function appliedFor(t) {
    const id = t?.id || t?._id, no = t?.tender_no, ref = t?.reference_number;
    return myBids.find(b => b.tender_id === id || b.tender_id === no || b.tender_reference === ref || b.tender_reference === no || b.tender_id === ref) || null;
  }

  async function handleApply(e) {
    e.preventDefault();
    if (!applyT) return;
    setApplying(true);
    try {
      const tId = applyT.id || applyT._id || applyT.tender_no;
      const res = await submitBid({ tender_id: tId, tender_reference: applyT.reference_number || applyT.tender_no, bid_amount: parseFloat(bidAmt) || 0 });
      const newBidId = res?.id || res?._id;
      flash('success', 'Application submitted! Now upload your compliance documents.');
      setApplyT(null); setBidAmt('');
      await load();
      if (newBidId) { setExpandedBid(newBidId); setActiveTab('MY_BIDS'); }
    } catch (err) { flash('error', 'Submission failed: ' + (err.message || 'Server error')); }
    finally { setApplying(false); }
  }

  async function loadDocs(bidId) {
    try {
      const r = await listBidDocuments(bidId);
      const docs = Array.isArray(r) ? r : (r?.documents || []);
      setBidDocs(prev => ({ ...prev, [bidId]: docs }));
    } catch {}
  }

  async function handleUpload(bidId, files) {
    if (!files?.length) return;
    setUploading(bidId);
    try {
      for (const f of files) await uploadBidderDocument(bidId, f);
      await evaluateBid(bidId).catch(() => {});
      await loadDocs(bidId);
      await load();
      flash('success', `${files.length} doc(s) uploaded and AI-parsed.`);
    } catch (err) { flash('error', 'Upload failed: ' + err.message); }
    finally { setUploading(null); }
  }

  async function handleReverify(bidId) {
    setReverifying(bidId);
    try {
      await runVerification(bidId).catch(() => {});
      await evaluateBid(bidId).catch(() => {});
      await load(); await loadDocs(bidId);
      flash('success', 'Verification refreshed.');
    } catch {} finally { setReverifying(null); }
  }

  const co = profile?.company_name || authUser?.name || 'My Company';
  const TABS = [{ key: 'TENDERS', label: '🌐 Available Tenders', n: tenders.length }, { key: 'MY_BIDS', label: '📋 My Applications', n: myBids.length }];

  return (
    <div style={{ minHeight: 'calc(100vh - 54px)', background: '#f1f5f9', fontFamily: "'Inter', -apple-system, sans-serif" }}>
      {/* Header */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e2e8f0', padding: '16px 32px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
              <Chip c="#0369a1" bg="#e0f2fe" b="#bae6fd">GeM VENDOR PORTAL</Chip>
              <span style={{ fontSize: 11, color: '#64748b' }}>BIDDER · Central Procurement</span>
            </div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 900, color: '#0f172a' }}>{co}</h1>
            <div style={{ display: 'flex', gap: 16, marginTop: 4, fontSize: 12, color: '#64748b', flexWrap: 'wrap' }}>
              {profile?.gstin && <span>GSTIN: <strong>{profile.gstin}</strong></span>}
              {profile?.pan && <span>PAN: <strong>{profile.pan}</strong></span>}
              {profile?.turnover_cr && <span>Turnover: <strong style={{ color: '#166534' }}>₹{profile.turnover_cr} Cr</strong></span>}
              {profile?.category && <span>Category: <strong>{profile.category}</strong></span>}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: '8px 14px', textAlign: 'right' }}>
              <div style={{ fontSize: 10, color: '#15803d', fontWeight: 700 }}>VENDOR STATUS</div>
              <div style={{ fontSize: 12, color: '#166534', fontWeight: 800 }}>✓ Active Verified</div>
            </div>
            <button onClick={load} style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #e2e8f0', background: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600, color: '#334155' }}>
              <RefreshCw size={13} /> Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e2e8f0' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', padding: '0 32px' }}>
          {TABS.map(t => (
            <button key={t.key} onClick={() => setActiveTab(t.key)} style={{ padding: '13px 20px', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: 13, fontWeight: activeTab === t.key ? 800 : 500, color: activeTab === t.key ? '#2563eb' : '#64748b', borderBottom: activeTab === t.key ? '2px solid #2563eb' : '2px solid transparent', display: 'flex', alignItems: 'center', gap: 7 }}>
              {t.label}
              <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 10, fontWeight: 800, background: activeTab === t.key ? '#eff6ff' : '#f1f5f9', color: activeTab === t.key ? '#2563eb' : '#94a3b8' }}>{t.n}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Flash msg */}
      {msg && (
        <div style={{ maxWidth: 1100, margin: '12px auto 0', padding: '0 32px' }}>
          <div style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: msg.type === 'success' ? '#dcfce7' : '#fee2e2', border: `1px solid ${msg.type === 'success' ? '#86efac' : '#fca5a5'}`, color: msg.type === 'success' ? '#166534' : '#991b1b' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {msg.type === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}{msg.text}
            </span>
            <button onClick={() => setMsg(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', fontSize: 18 }}>×</button>
          </div>
        </div>
      )}

      {/* Content */}
      <div style={{ maxWidth: 1100, margin: '24px auto 60px', padding: '0 32px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '80px 0', color: '#64748b' }}>
            <Loader2 size={28} style={{ margin: '0 auto 10px', display: 'block' }} /><div>Loading…</div>
          </div>
        ) : activeTab === 'TENDERS' ? (
          <TendersTab tenders={tenders} appliedFor={appliedFor} onDetail={setDetailT} onApply={t => { setApplyT(t); setBidAmt(''); }} onViewBid={b => { setExpandedBid(b.id || b._id); setActiveTab('MY_BIDS'); }} />
        ) : (
          <MyBidsTab myBids={myBids} tenders={tenders} expandedBid={expandedBid} onExpand={id => { const next = expandedBid === id ? null : id; setExpandedBid(next); if (next) loadDocs(next); }} bidDocs={bidDocs} uploading={uploading} reverifying={reverifying} onUpload={handleUpload} onReverify={handleReverify} onBrowse={() => setActiveTab('TENDERS')} />
        )}
      </div>

      {detailT && <TenderDetailModal tender={detailT} applied={appliedFor(detailT)} onClose={() => setDetailT(null)} onApply={() => { setDetailT(null); setApplyT(detailT); setBidAmt(''); }} onViewBid={b => { setDetailT(null); setExpandedBid(b.id || b._id); setActiveTab('MY_BIDS'); }} />}
      {applyT && <ApplyModal tender={applyT} bidAmt={bidAmt} setBidAmt={setBidAmt} applying={applying} onClose={() => setApplyT(null)} onSubmit={handleApply} />}
    </div>
  );
}

function TendersTab({ tenders, appliedFor, onDetail, onApply, onViewBid }) {
  if (!tenders.length) return (
    <div style={{ textAlign: 'center', padding: '80px 20px', background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0' }}>
      <div style={{ fontSize: 40, marginBottom: 10 }}>🌐</div>
      <div style={{ fontWeight: 800, fontSize: 17, color: '#0f172a' }}>No Open Tenders</div>
      <div style={{ fontSize: 13, color: '#64748b', marginTop: 4 }}>Procurement officers will publish tenders here.</div>
    </div>
  );
  return (
    <div>
      <div style={{ marginBottom: 18 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: '#0f172a' }}>Available Tenders ({tenders.length})</h2>
        <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>View details and eligibility rules before applying.</p>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {tenders.map(t => {
          const id = t.id || t._id;
          const rules = t.requirement_rules || t.rules || [];
          const applied = appliedFor(t);
          const dl = t.closing_date ? new Date(t.closing_date) : null;
          const days = dl ? Math.ceil((dl - Date.now()) / 86400000) : null;
          const expired = days !== null && days < 0;
          return (
            <div key={id} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: '20px 24px', boxShadow: '0 1px 4px rgba(0,0,0,0.03)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 280 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 800, color: '#1e40af', background: '#eff6ff', padding: '2px 8px', borderRadius: 5, border: '1px solid #bfdbfe' }}>
                      {t.reference_number || t.tender_no || id?.slice(-8)}
                    </span>
                    <Chip c="#166534" bg="#dcfce7" b="#86efac">{t.status || 'ACTIVE'}</Chip>
                    <span style={{ fontSize: 11, color: '#64748b' }}>{t.organization || t.buyer} · {t.category || 'Goods'}</span>
                  </div>
                  <h3 style={{ margin: '0 0 10px', fontSize: 16, fontWeight: 800, color: '#0f172a' }}>{t.title}</h3>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    {t.turnover_threshold_cr > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5, background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 6, padding: '4px 10px', fontSize: 12 }}>
                        <span>💰</span><span style={{ color: '#166534', fontWeight: 700 }}>Turnover ≥ ₹{t.turnover_threshold_cr} Cr</span>
                      </div>
                    )}
                    {rules.length > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, padding: '4px 10px', fontSize: 12 }}>
                        <span>📋</span><span style={{ color: '#334155', fontWeight: 600 }}>{rules.length} Eligibility Rules</span>
                      </div>
                    )}
                    {dl && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5, background: expired ? '#fee2e2' : days <= 7 ? '#fffbeb' : '#f8fafc', border: `1px solid ${expired ? '#fca5a5' : days <= 7 ? '#fde68a' : '#e2e8f0'}`, borderRadius: 6, padding: '4px 10px', fontSize: 12 }}>
                        <span>🗓️</span>
                        <span style={{ color: expired ? '#991b1b' : days <= 7 ? '#92400e' : '#334155', fontWeight: 600 }}>
                          {expired ? 'Expired' : `Closes ${dl.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })} (${days}d left)`}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 155, flexShrink: 0 }}>
                  <button onClick={() => onDetail(t)} style={{ padding: '9px 16px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', color: '#1e293b', fontSize: 13, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                    <Eye size={14} /> View Details
                  </button>
                  {applied ? (
                    <button onClick={() => onViewBid(applied)} style={{ padding: '9px 16px', borderRadius: 8, border: '1px solid #86efac', background: '#f0fdf4', color: '#166534', fontSize: 13, fontWeight: 800, cursor: 'pointer', textAlign: 'center' }}>
                      ✓ Applied · View Bid
                    </button>
                  ) : (
                    <button onClick={() => onApply(t)} disabled={expired} style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: expired ? '#e2e8f0' : 'linear-gradient(135deg,#1d4ed8,#2563eb)', color: expired ? '#94a3b8' : '#fff', fontSize: 13, fontWeight: 800, cursor: expired ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, boxShadow: expired ? 'none' : '0 2px 8px rgba(37,99,235,0.3)' }}>
                      <Send size={13} />{expired ? 'Closed' : 'Apply Now'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MyBidsTab({ myBids, tenders, expandedBid, onExpand, bidDocs, uploading, reverifying, onUpload, onReverify, onBrowse }) {
  if (!myBids.length) return (
    <div style={{ textAlign: 'center', padding: '80px 20px', background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0' }}>
      <div style={{ fontSize: 40, marginBottom: 10 }}>📋</div>
      <div style={{ fontWeight: 800, fontSize: 17, color: '#0f172a' }}>No Applications Yet</div>
      <div style={{ fontSize: 13, color: '#64748b', margin: '6px 0 18px' }}>Apply for a tender to see it here.</div>
      <button onClick={onBrowse} style={{ padding: '10px 22px', borderRadius: 8, border: 'none', background: '#2563eb', color: '#fff', fontSize: 13, fontWeight: 800, cursor: 'pointer' }}>Browse Tenders</button>
    </div>
  );
  return (
    <div>
      <div style={{ marginBottom: 18, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: '#0f172a' }}>My Applications ({myBids.length})</h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>Upload compliance certificates. AI verifies automatically.</p>
        </div>
        <button onClick={onBrowse} style={{ padding: '8px 16px', borderRadius: 8, border: '1px solid #2563eb', background: '#eff6ff', color: '#1d4ed8', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>+ Browse Tenders</button>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {myBids.map(b => {
          const bId = b.id || b._id;
          const isOpen = expandedBid === bId;
          const tender = tenders.find(t => t.id === b.tender_id || t.tender_no === b.tender_reference || t.reference_number === b.tender_reference) || {};
          const tTitle = tender.title || b.tender_reference || 'Tender Application';
          const rr = b.evaluation_results || [];
          const docs = bidDocs[bId] || [];
          const score = b.readiness_score !== undefined ? b.readiness_score : (b.overall_status === 'PASS' ? 90 : rr.length ? 60 : 30);
          const scoreColor = score >= 75 ? '#22c55e' : score >= 50 ? '#f59e0b' : '#ef4444';
          return (
            <div key={bId} style={{ background: '#fff', border: `1.5px solid ${isOpen ? '#3b82f6' : '#e2e8f0'}`, borderRadius: 12, overflow: 'hidden', boxShadow: '0 1px 4px rgba(0,0,0,0.03)' }}>
              <div onClick={() => onExpand(bId)} style={{ padding: '18px 24px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 14, flexWrap: 'wrap', background: isOpen ? '#fafbff' : '#fff' }}>
                <div style={{ flex: 1, minWidth: 250 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 5 }}>
                    <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#1e40af', fontWeight: 800, background: '#eff6ff', padding: '2px 8px', borderRadius: 5, border: '1px solid #bfdbfe' }}>{b.tender_reference || bId?.slice(-8)}</span>
                    {/* Show final officer status if present, otherwise AI overall_status */}
                    {(b.status === 'APPROVED' || b.status === 'REJECTED') ? (
                      <SBadge status={b.status} />
                    ) : (
                      b.overall_status && <SBadge status={b.overall_status} />
                    )}
                    {b.risk_band && b.status !== 'APPROVED' && b.status !== 'REJECTED' && <SBadge status={b.risk_band} />}
                  </div>
                  <h3 style={{ margin: '2px 0', fontSize: 15, fontWeight: 800, color: '#0f172a' }}>{tTitle}</h3>
                  <div style={{ fontSize: 12, color: '#64748b', display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 3 }}>
                    <span>Applied: {b.created_at ? new Date(b.created_at).toLocaleDateString('en-IN') : 'Recent'}</span>
                    {b.bid_amount > 0 && <span>Bid: <strong>₹{(b.bid_amount / 1e7).toFixed(2)} Cr</strong></span>}
                    <span>{docs.length} docs uploaded</span>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 2 }}>Readiness</div>
                    <div style={{ position: 'relative', width: 52, height: 52 }}>
                      <svg viewBox="0 0 36 36" style={{ width: 52, height: 52, transform: 'rotate(-90deg)' }}>
                        <circle cx="18" cy="18" r="14" fill="none" stroke="#f1f5f9" strokeWidth="3.5" />
                        <circle cx="18" cy="18" r="14" fill="none" stroke={scoreColor} strokeWidth="3.5" strokeDasharray={`${(score / 100) * 87.96} 87.96`} strokeLinecap="round" />
                      </svg>
                      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 900, color: '#0f172a' }}>{score}</div>
                    </div>
                  </div>
                  {isOpen ? <ChevronUp size={18} color="#64748b" /> : <ChevronDown size={18} color="#64748b" />}
                </div>
              </div>
              {isOpen && (
                <div style={{ borderTop: '1px solid #f1f5f9', background: '#f8fafc', padding: '20px 24px' }}>
                  {/* Action bar */}
                  <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
                    <button onClick={e => { e.stopPropagation(); onReverify(bId); }} disabled={reverifying === bId} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', color: '#334155', fontSize: 12, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
                      {reverifying === bId ? <Loader2 size={13} /> : <RefreshCw size={13} />}{reverifying === bId ? 'Verifying…' : 'Re-verify Compliance'}
                    </button>
                    <label style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #2563eb', background: '#eff6ff', color: '#1d4ed8', fontSize: 12, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
                      {uploading === bId ? <Loader2 size={13} /> : <UploadCloud size={13} />}{uploading === bId ? 'Uploading…' : 'Upload Documents'}
                      <input type="file" multiple accept=".pdf,.png,.jpg,.jpeg" style={{ display: 'none' }} disabled={uploading === bId} onChange={e => e.target.files?.length && onUpload(bId, Array.from(e.target.files))} />
                    </label>
                  </div>
                  {/* Rule compliance */}
                  {rr.length > 0 && (
                    <div style={{ marginBottom: 20 }}>
                      <h4 style={{ margin: '0 0 10px', fontSize: 13, fontWeight: 800, color: '#0f172a', display: 'flex', alignItems: 'center', gap: 6 }}><ShieldCheck size={15} color="#15803d" /> Rule Compliance Breakdown</h4>
                      <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, overflow: 'hidden' }}>
                        {rr.map((r, i) => {
                          const ruleDef = (tender.requirement_rules || tender.rules || []).find(x => x.rule_id === r.rule_id) || {};
                          const ruleName = ruleDef.conditions?.name || ruleDef.name || (r.metric || '').replace(/_/g, ' ');
                          const isOptional = ruleDef.conditions?.type === 'CONDITIONAL' || ruleDef.severity === 'LOW';
                          const statusTag = isOptional ? 'OPTIONAL' : 'MANDATORY';
                          return (
                            <div key={i} style={{ padding: '12px 16px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                              <div style={{ minWidth: 80, fontFamily: 'monospace', fontWeight: 700, fontSize: 12, color: '#1e40af' }}>{r.clause_id || ruleDef.clause_id || `Rule ${i + 1}`}</div>
                              <div style={{ flex: 1, minWidth: 160 }}>
                                <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>{String(ruleName).toUpperCase()}</div>
                                <div style={{ fontSize: 10, fontWeight: 800, color: isOptional ? '#94a3b8' : '#ef4444', textTransform: 'uppercase', marginTop: 2, display: 'inline-block', background: isOptional ? '#f1f5f9' : '#fee2e2', padding: '1px 6px', borderRadius: 4 }}>{statusTag}</div>
                              </div>
                              <SBadge status={r.status || 'PENDING'} />
                              <div style={{ fontSize: 11, color: '#475569', flex: 2, minWidth: 200, lineHeight: 1.4 }}>{r.explanation || '—'}</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                  {/* Documents */}
                  <div>
                    <h4 style={{ margin: '0 0 10px', fontSize: 13, fontWeight: 800, color: '#0f172a', display: 'flex', alignItems: 'center', gap: 6 }}><FileCheck size={15} color="#334155" /> Uploaded Documents ({docs.length})</h4>
                    {docs.length === 0 ? (
                      <div style={{ background: '#fff', border: '2px dashed #cbd5e1', borderRadius: 10, padding: '20px', textAlign: 'center' }}>
                        <UploadCloud size={22} color="#94a3b8" style={{ margin: '0 auto 6px', display: 'block' }} />
                        <div style={{ fontSize: 13, fontWeight: 700, color: '#334155', marginBottom: 4 }}>No documents uploaded yet</div>
                        <div style={{ fontSize: 12, color: '#64748b' }}>Use "Upload Documents" above to attach CA cert, GST cert, Udyam, PAN, OEM auth, ISO 9001 etc. AI will parse them.</div>
                      </div>
                    ) : (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(230px,1fr))', gap: 10 }}>
                        {docs.map((d, i) => (
                          <div key={d.id || i} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: '12px 14px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                              <FileText size={15} color="#3b82f6" style={{ flexShrink: 0 }} />
                              <div style={{ overflow: 'hidden', flex: 1 }}>
                                <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{d.original_filename || d.filename || 'Document'}</div>
                                <div style={{ fontSize: 10, color: '#64748b' }}>{d.doc_type?.replace(/_/g, ' ') || 'Processing'}{d.page_count ? ` · ${d.page_count}p` : ''}</div>
                              </div>
                              <span style={{ fontSize: 10, fontWeight: 800, padding: '2px 6px', borderRadius: 4, flexShrink: 0, background: d.pipeline_status === 'PROCESSED' ? '#dcfce7' : '#fffbeb', color: d.pipeline_status === 'PROCESSED' ? '#166534' : '#92400e' }}>{d.pipeline_status || 'PENDING'}</span>
                            </div>
                            {d.evidence_count > 0 && <div style={{ fontSize: 10, background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 4, padding: '3px 8px', color: '#166534', fontWeight: 700 }}>🤖 {d.evidence_count} fields AI-extracted</div>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  {/* Document guide when empty */}
                  {docs.length === 0 && rr.length === 0 && (
                    <div style={{ marginTop: 16, background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 10, padding: '14px 18px' }}>
                      <div style={{ fontSize: 13, fontWeight: 800, color: '#1e40af', marginBottom: 8 }}>📎 Required Compliance Documents</div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 6 }}>
                        {DOC_GUIDE.map((d, i) => (
                          <div key={i} style={{ fontSize: 12, display: 'flex', gap: 6 }}>
                            <span style={{ color: '#2563eb', fontWeight: 700, flexShrink: 0 }}>📄 {d.doc}</span>
                            <span style={{ color: '#475569' }}>— {d.desc}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TenderDetailModal({ tender, applied, onClose, onApply, onViewBid }) {
  const rules = tender.requirement_rules || tender.rules || [];
  const dl = tender.closing_date ? new Date(tender.closing_date) : null;
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 20 }}>
      <div style={{ background: '#fff', borderRadius: 16, width: 700, maxWidth: '100%', maxHeight: '88vh', display: 'flex', flexDirection: 'column', boxShadow: '0 25px 60px rgba(0,0,0,0.3)', overflow: 'hidden' }}>
        <div style={{ padding: '20px 24px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <span style={{ fontSize: 11, fontWeight: 800, color: '#1e40af', background: '#eff6ff', padding: '2px 8px', borderRadius: 4 }}>{tender.reference_number || tender.tender_no}</span>
            <h2 style={{ margin: '6px 0 0', fontSize: 19, fontWeight: 900, color: '#0f172a' }}>{tender.title}</h2>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 3 }}>{tender.organization || tender.buyer} · {tender.category || 'Goods'}</div>
          </div>
          <button onClick={onClose} style={{ background: '#f1f5f9', border: 'none', width: 32, height: 32, borderRadius: '50%', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><X size={16} color="#64748b" /></button>
        </div>
        <div style={{ padding: '20px 24px', overflowY: 'auto', flex: 1 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 10, marginBottom: 20 }}>
            {[
              { l: 'Issuing Authority', v: tender.organization || tender.buyer || '—' },
              { l: 'Submission Deadline', v: dl ? dl.toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' }) : 'Open', red: true },
              { l: 'Min Turnover Requirement', v: tender.turnover_threshold_cr ? `≥ ₹${tender.turnover_threshold_cr} Crore (3-year avg)` : 'As per tender', green: true },
              { l: 'MII Local Content', v: `≥ ${tender.local_content_threshold_pct || tender.local_content_pct || 50}% (Class-I Supplier)` },
            ].map(({ l, v, red, green }) => (
              <div key={l} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '12px 14px' }}>
                <div style={{ fontSize: 11, color: '#64748b', marginBottom: 3 }}>{l}</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: green ? '#166534' : red ? '#dc2626' : '#0f172a' }}>{v}</div>
              </div>
            ))}
          </div>
          {tender.description && <div style={{ marginBottom: 20 }}><div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 6 }}>Scope</div><p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>{tender.description}</p></div>}
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 10 }}>Eligibility Requirements ({rules.length})</div>
            {rules.length === 0 ? <div style={{ fontSize: 13, color: '#64748b', background: '#f8fafc', borderRadius: 8, padding: 14 }}>No rules compiled yet. Officer needs to upload the RFP PDF.</div> : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {rules.map((r, i) => {
                  const icon = RULE_ICON[r.rule_type] || RULE_ICON.DEFAULT;
                  const sc = SEV_COLOR[r.severity] || '#64748b';
                  const tv = r.threshold_value;
                  const showThreshold = tv && !['ACTIVE', 'EXISTS', 'True', 'CONSISTENT'].includes(tv);
                  return (
                    <div key={i} style={{ background: '#fff', border: '1px solid #e2e8f0', borderLeft: `3px solid ${sc}`, borderRadius: 8, padding: '10px 14px', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                      <span style={{ fontSize: 18, flexShrink: 0 }}>{icon}</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 12, fontWeight: 800, color: '#0f172a' }}>
                          {r.requirement_id || r.clause_id}: {r.description || (r.metric || '').replace(/_/g, ' ')}
                          {showThreshold && <span style={{ color: '#166534', fontWeight: 900 }}> ≥ {tv}{r.threshold_unit === 'INR_CR' ? ' Cr' : r.threshold_unit === 'PERCENTAGE' ? '%' : ''}</span>}
                        </div>
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
                          Evidence: <strong>{(r.evidence_type || 'Certificate').replace(/_/g, ' ')}</strong>
                          {r.verification_sources && <> · Verify via: <strong>{Array.isArray(r.verification_sources) ? r.verification_sources.join(', ') : r.verification_sources}</strong></>}
                        </div>
                        {r.clause?.clause_text && <div style={{ fontSize: 11, color: '#475569', marginTop: 4, fontStyle: 'italic', lineHeight: 1.4 }}>"{r.clause.clause_text.slice(0, 180)}{r.clause.clause_text.length > 180 ? '…' : ''}"</div>}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 3, alignItems: 'flex-end', flexShrink: 0 }}>
                        <span style={{ fontSize: 10, fontWeight: 800, padding: '2px 7px', borderRadius: 4, background: `${sc}18`, color: sc, border: `1px solid ${sc}30` }}>{r.severity || 'CRITICAL'}</span>
                        {r.is_mandatory !== false && <span style={{ fontSize: 9, fontWeight: 700, color: '#991b1b', background: '#fee2e2', border: '1px solid #fca5a5', padding: '1px 5px', borderRadius: 3 }}>MANDATORY</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
        <div style={{ padding: '14px 24px', borderTop: '1px solid #e2e8f0', display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button onClick={onClose} style={{ padding: '9px 18px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', color: '#475569', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>Close</button>
          {applied ? (
            <button onClick={() => onViewBid(applied)} style={{ padding: '9px 20px', borderRadius: 8, border: '1px solid #86efac', background: '#f0fdf4', color: '#166534', fontSize: 13, fontWeight: 800, cursor: 'pointer' }}>✓ Applied · View Application</button>
          ) : (
            <button onClick={onApply} style={{ padding: '9px 20px', borderRadius: 8, border: 'none', background: 'linear-gradient(135deg,#1d4ed8,#2563eb)', color: '#fff', fontSize: 13, fontWeight: 800, cursor: 'pointer', boxShadow: '0 2px 8px rgba(37,99,235,0.35)' }}>Apply Now →</button>
          )}
        </div>
      </div>
    </div>
  );
}

function ApplyModal({ tender, bidAmt, setBidAmt, applying, onClose, onSubmit }) {
  const crAmt = (parseFloat(bidAmt || 0) / 1e7).toFixed(2);
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1001, padding: 20 }}>
      <div style={{ background: '#fff', borderRadius: 16, width: 540, maxWidth: '100%', boxShadow: '0 25px 60px rgba(0,0,0,0.3)', overflow: 'hidden' }}>
        <div style={{ padding: '20px 24px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div><Chip c="#166534" bg="#dcfce7" b="#86efac">APPLY FOR TENDER</Chip><h2 style={{ margin: '6px 0 0', fontSize: 17, fontWeight: 800, color: '#0f172a' }}>{tender.reference_number || tender.tender_no}</h2></div>
          <button onClick={onClose} style={{ background: '#f1f5f9', border: 'none', width: 32, height: 32, borderRadius: '50%', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><X size={16} color="#64748b" /></button>
        </div>
        <form onSubmit={onSubmit} style={{ padding: '20px 24px' }}>
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '12px 16px', marginBottom: 18 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>{tender.title}</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 3 }}>{tender.organization} · Min Turnover: ₹{tender.turnover_threshold_cr || '—'} Cr</div>
          </div>
          <div style={{ marginBottom: 18 }}>
            <label style={{ fontSize: 12, fontWeight: 700, color: '#475569', display: 'block', marginBottom: 6 }}>
              Commercial Bid Value (INR) <span style={{ color: '#dc2626' }}>*</span>
            </label>
            <input type="number" required value={bidAmt} onChange={e => setBidAmt(e.target.value)} placeholder="e.g. 45000000" style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #cbd5e1', fontSize: 14, fontWeight: 700, boxSizing: 'border-box', outline: 'none' }} />
            {bidAmt && <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>≈ ₹{crAmt} Crore</div>}
          </div>
          <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 8, padding: '12px 14px', marginBottom: 20, fontSize: 12, color: '#0369a1', lineHeight: 1.5 }}>
            ℹ️ After submitting, you can upload compliance documents (CA cert, GST cert, OEM auth, ISO 9001 etc.) in My Applications for AI verification.
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button type="button" onClick={onClose} style={{ padding: '10px 18px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', color: '#475569', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
            <button type="submit" disabled={applying || !bidAmt} style={{ padding: '10px 24px', borderRadius: 8, border: 'none', background: applying || !bidAmt ? '#93c5fd' : 'linear-gradient(135deg,#1d4ed8,#2563eb)', color: '#fff', fontSize: 13, fontWeight: 800, cursor: applying || !bidAmt ? 'wait' : 'pointer' }}>
              {applying ? 'Submitting…' : 'Submit Application →'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
