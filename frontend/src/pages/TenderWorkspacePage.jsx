/**
 * TenderWorkspacePage v4 — Procurement Officer Dashboard
 * Clean, guided UX for creating tenders and reviewing published ones.
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, X, CheckCircle2, AlertTriangle, RefreshCw, UploadCloud, Eye, Trash2, Send, Loader2, Edit } from 'lucide-react';
import { listTenders, createTender, updateTender, uploadTenderDocument, getTenderBids, deleteTender } from '../api/client';

const RULE_ICON = {
  TURNOVER: '💰', GST_STATUS: '🏛️', UDYAM: '🏭', MAKE_IN_INDIA: '🇮🇳',
  NAME_MATCH: '📋', EPFO_COMPLIANCE: '👷', OEM_AUTHORIZATION: '🔑',
  ISO_9001_CERT: '✅', DEBARMENT_DECLARATION: '📜', DEFAULT: '📄',
};
const SEV_COLOR = { CRITICAL: '#dc2626', HIGH: '#d97706', MEDIUM: '#2563eb', LOW: '#64748b' };

function Chip({ children, c = '#475569', bg = '#f1f5f9', b = '#cbd5e1' }) {
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, padding: '2px 8px', borderRadius: 20, fontSize: 11, fontWeight: 700, background: bg, color: c, border: `1px solid ${b}`, whiteSpace: 'nowrap' }}>{children}</span>;
}

function StatusPill({ status }) {
  const m = {
    ACTIVE: ['#166534', '#dcfce7', '#86efac', '✓ ACTIVE'],
    DRAFT: ['#475569', '#f1f5f9', '#cbd5e1', '📝 DRAFT'],
    CLOSED: ['#991b1b', '#fee2e2', '#fca5a5', '⛔ CLOSED'],
    PUBLISHED: ['#1d4ed8', '#eff6ff', '#bfdbfe', '📢 PUBLISHED'],
  };
  const [c, bg, b, t] = m[(status || '').toUpperCase()] || m.DRAFT;
  return <Chip c={c} bg={bg} b={b}>{t}</Chip>;
}

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return 'Invalid Date';
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return 'Invalid Date';
  }
}

export default function TenderWorkspacePage() {
  const navigate = useNavigate();
  const [tenders, setTenders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('MY_TENDERS');
  const [msg, setMsg] = useState(null);
  
  const [detailT, setDetailT] = useState(null);
  
  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const res = await listTenders();
      setTenders(res?.tenders || (Array.isArray(res) ? res : []));
    } catch (e) {
      flash('error', 'Failed to load tenders: ' + e.message);
    } finally {
      setLoading(false);
    }
  }

  function flash(type, text) {
    setMsg({ type, text });
    if (type === 'success') setTimeout(() => setMsg(null), 6000);
  }

  const handleTenderCreated = (tender) => {
    setActiveTab('MY_TENDERS');
    flash('success', `Tender ${tender.reference_number || tender.tender_no} created successfully.`);
    load();
  };

  const handleTenderDeleted = (id) => {
    setDetailT(null);
    setTenders(prev => prev.filter(t => t.id !== id && t._id !== id && t.tender_no !== id));
    flash('success', 'Tender and all associated data deleted.');
  };

  const TABS = [
    { key: 'MY_TENDERS', label: '📋 My Published Tenders', n: tenders.length },
    { key: 'CREATE', label: '➕ Create New Tender' }
  ];

  return (
    <div style={{ minHeight: 'calc(100vh - 54px)', background: '#f1f5f9', fontFamily: "'Inter', -apple-system, sans-serif" }}>
      {/* Header */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e2e8f0', padding: '16px 32px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
              <Chip c="#92400e" bg="#fffbeb" b="#fde68a">GeM OFFICER PORTAL</Chip>
              <span style={{ fontSize: 11, color: '#64748b' }}>PROCUREMENT · Authority</span>
            </div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 900, color: '#0f172a' }}>Tender Management</h1>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
              Create, publish, and monitor technical tenders securely.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
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
            <button key={t.key} onClick={() => setActiveTab(t.key)} style={{ padding: '13px 20px', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: 13, fontWeight: activeTab === t.key ? 800 : 500, color: activeTab === t.key ? '#d97706' : '#64748b', borderBottom: activeTab === t.key ? '2px solid #d97706' : '2px solid transparent', display: 'flex', alignItems: 'center', gap: 7 }}>
              {t.label}
              {t.n !== undefined && (
                <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 10, fontWeight: 800, background: activeTab === t.key ? '#fffbeb' : '#f1f5f9', color: activeTab === t.key ? '#d97706' : '#94a3b8' }}>{t.n}</span>
              )}
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
            <Loader2 size={28} className="animate-spin" style={{ margin: '0 auto 10px', display: 'block' }} /><div>Loading Tenders…</div>
          </div>
        ) : activeTab === 'MY_TENDERS' ? (
          <MyTendersTab tenders={tenders} onDetail={setDetailT} navigate={navigate} onCreate={() => setActiveTab('CREATE')} />
        ) : (
          <CreateTenderTab onCreated={handleTenderCreated} onCancel={() => setActiveTab('MY_TENDERS')} />
        )}
      </div>

      {/* Tender Detail Modal */}
      {detailT && <TenderDetailModal tender={detailT} onClose={() => setDetailT(null)} navigate={navigate} onDelete={handleTenderDeleted} />}
    </div>
  );
}

function MyTendersTab({ tenders, onDetail, navigate, onCreate }) {
  if (!tenders.length) return (
    <div style={{ textAlign: 'center', padding: '80px 20px', background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0' }}>
      <div style={{ fontSize: 40, marginBottom: 10 }}>📋</div>
      <div style={{ fontWeight: 800, fontSize: 17, color: '#0f172a' }}>No Tenders Published</div>
      <div style={{ fontSize: 13, color: '#64748b', margin: '6px 0 18px' }}>Create your first tender to start accepting bids.</div>
      <button onClick={onCreate} style={{ padding: '10px 22px', borderRadius: 8, border: 'none', background: '#d97706', color: '#fff', fontSize: 13, fontWeight: 800, cursor: 'pointer' }}>+ Create Tender</button>
    </div>
  );

  return (
    <div>
      <div style={{ marginBottom: 18, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: '#0f172a' }}>My Published Tenders ({tenders.length})</h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>Manage your active tenders and review incoming bids.</p>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {tenders.map(t => {
          const id = t.id || t._id;
          const rules = t.requirement_rules || t.rules || [];
          const dlDate = t.closing_date ? new Date(t.closing_date) : null;
          const isValidDate = dlDate && !isNaN(dlDate.getTime());
          const days = isValidDate ? Math.ceil((dlDate - Date.now()) / 86400000) : null;
          const expired = days !== null && days < 0;

          return (
            <div key={id} style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: '20px 24px', boxShadow: '0 1px 4px rgba(0,0,0,0.03)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 280 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 800, color: '#92400e', background: '#fffbeb', padding: '2px 8px', borderRadius: 5, border: '1px solid #fde68a' }}>
                      {t.reference_number || t.tender_no || id?.slice(-8)}
                    </span>
                    <StatusPill status={t.status || 'ACTIVE'} />
                    {days > 0 && days <= 30 && <span style={{ fontSize: 10, fontWeight: 700, background: '#fffbeb', color: '#d97706', border: '1px solid #fde68a', padding: '1px 7px', borderRadius: 20 }}>⏰ {days}d left</span>}
                    {expired && <span style={{ fontSize: 10, fontWeight: 700, background: '#fee2e2', color: '#991b1b', border: '1px solid #fca5a5', padding: '1px 7px', borderRadius: 20 }}>CLOSED</span>}
                  </div>
                  <h3 style={{ margin: '0 0 10px', fontSize: 16, fontWeight: 800, color: '#0f172a' }}>{t.title}</h3>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, padding: '4px 10px', fontSize: 12 }}>
                      <span style={{ color: '#334155', fontWeight: 600 }}>🏛️ {t.authority || t.organization || 'GeM'}</span>
                    </div>
                    {t.estimated_value_cr > 0 && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, padding: '4px 10px', fontSize: 12 }}>
                        <span style={{ color: '#334155', fontWeight: 600 }}>💰 ₹{t.estimated_value_cr} Cr</span>
                      </div>
                    )}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, padding: '4px 10px', fontSize: 12 }}>
                      <span style={{ color: '#334155', fontWeight: 600 }}>📋 {rules.length} Rules Extracted</span>
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 155, flexShrink: 0 }}>
                  <button onClick={() => onDetail(t)} style={{ padding: '9px 16px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', color: '#1e293b', fontSize: 13, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                    <Eye size={14} /> View Details
                  </button>
                  <button onClick={() => navigate(`/bids?tenderId=${encodeURIComponent(id || t.tender_no)}`)} style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: 'linear-gradient(135deg,#d97706,#b45309)', color: '#fff', fontSize: 13, fontWeight: 800, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, boxShadow: '0 2px 8px rgba(217,119,6,0.3)' }}>
                    View Bids →
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TenderDetailModal({ tender, onClose, navigate, onDelete }) {
  const [showPdf, setShowPdf] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const rules = tender.requirement_rules || tender.rules || [];
  const tId = tender.id || tender._id || tender.tender_no;
  // Route through the API gateway (port 3000 → backend), not directly to 8001
  const token = localStorage.getItem('rashtrabid_token') || localStorage.getItem('gemguard_token') || '';
  const pdfUrl = `/api/v1/tenders/${tId}/pdf?token=${token}`;
  const pdfDownloadUrl = `/api/v1/tenders/${tId}/pdf?token=${token}`;

  async function handleDelete() {
    setDeleting(true);
    try {
      await deleteTender(tId);
      onDelete(tId);
    } catch (e) {
      alert("Failed to delete tender: " + e.message);
      setDeleting(false);
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 20 }}>
      <div style={{ background: '#fff', borderRadius: 16, width: 850, maxWidth: '100%', maxHeight: '90vh', display: 'flex', flexDirection: 'column', boxShadow: '0 25px 60px rgba(0,0,0,0.3)', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ padding: '20px 24px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 800, color: '#92400e', background: '#fffbeb', padding: '2px 8px', borderRadius: 4, border: '1px solid #fde68a' }}>{tender.reference_number || tender.tender_no}</span>
              <StatusPill status={tender.status} />
            </div>
            <h2 style={{ margin: 0, fontSize: 19, fontWeight: 900, color: '#0f172a' }}>{tender.title}</h2>
          </div>
          <button onClick={onClose} style={{ background: '#f1f5f9', border: 'none', width: 32, height: 32, borderRadius: '50%', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}><X size={16} color="#64748b" /></button>
        </div>

        {/* Content */}
        <div style={{ padding: '20px 24px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: 20 }}>
          {showPdf ? (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
              <div style={{ padding: '10px 14px', background: '#f8fafc', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', display: 'flex', alignItems: 'center', gap: 6 }}><FileText size={16} color="#3b82f6"/> {tender.filename || tender.original_filename || 'Uploaded RFP Document'}</span>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <a
                    href={pdfDownloadUrl}
                    download={tender.filename || 'tender.pdf'}
                    style={{ padding: '4px 10px', fontSize: 11, fontWeight: 700, borderRadius: 6, border: '1px solid #bfdbfe', background: '#eff6ff', color: '#1d4ed8', cursor: 'pointer', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}
                  >
                    ⬇ Download PDF
                  </a>
                  <button onClick={() => setShowPdf(false)} style={{ padding: '4px 10px', fontSize: 11, fontWeight: 700, borderRadius: 6, border: '1px solid #cbd5e1', background: '#fff', cursor: 'pointer' }}>✕ Close</button>
                </div>
              </div>
              <iframe src={pdfUrl} style={{ width: '100%', height: '500px', border: 'none' }} title="Tender RFP" />
            </div>
          ) : (
            <>
              {/* Metadata */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10 }}>
                {[
                  { l: 'Issuing Authority', v: tender.organization || tender.buyer || '—' },
                  { l: 'Submission Deadline', v: fmtDate(tender.closing_date), red: true },
                  { l: 'Estimated Value', v: tender.estimated_value_cr ? `₹${tender.estimated_value_cr} Cr` : '—' },
                  { l: 'Min Turnover Required', v: tender.turnover_threshold_cr ? `≥ ₹${tender.turnover_threshold_cr} Cr` : 'As per tender', green: true },
                ].map(({ l, v, red, green }) => (
                  <div key={l} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '12px 14px' }}>
                    <div style={{ fontSize: 11, color: '#64748b', marginBottom: 3 }}>{l}</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: green ? '#166534' : red ? '#dc2626' : '#0f172a' }}>{v}</div>
                  </div>
                ))}
              </div>

              {tender.description && (
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 6 }}>Description</div>
                  <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>{tender.description}</p>
                </div>
              )}

              {/* Rules */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Extracted Eligibility Rules ({rules.length})</div>
                  {tender.document_path && (
                    <button onClick={() => setShowPdf(true)} style={{ padding: '6px 12px', fontSize: 12, fontWeight: 700, borderRadius: 6, border: '1px solid #bfdbfe', background: '#eff6ff', color: '#1d4ed8', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <FileText size={14}/> View Uploaded RFP
                    </button>
                  )}
                </div>
                {rules.length === 0 ? (
                  <div style={{ fontSize: 13, color: '#64748b', background: '#f8fafc', borderRadius: 8, padding: 14 }}>No rules extracted.</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {rules.map((r, i) => {
                      const icon = RULE_ICON[r.rule_type] || RULE_ICON.DEFAULT;
                      const sc = SEV_COLOR[r.severity] || '#64748b';
                      const tv = r.threshold_value || r.threshold;
                      const showThreshold = tv && !['ACTIVE', 'EXISTS', 'True', 'CONSISTENT', true].includes(tv);
                      return (
                        <div key={i} style={{ background: '#fff', border: '1px solid #e2e8f0', borderLeft: `3px solid ${sc}`, borderRadius: 8, padding: '12px 16px', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                          <span style={{ fontSize: 18, flexShrink: 0 }}>{icon}</span>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: 13, fontWeight: 800, color: '#0f172a' }}>
                              {r.requirement_id || r.clause_id}: {r.description || (r.metric || '').replace(/_/g, ' ').toUpperCase()}
                              {showThreshold && <span style={{ color: '#166534', fontWeight: 900 }}> ≥ {tv}{r.unit === 'INR_CR' || r.threshold_unit === 'INR_CR' ? ' Cr' : ['%', 'PERCENTAGE'].includes(r.unit || r.threshold_unit) ? '%' : ''}</span>}
                            </div>
                            <div style={{ fontSize: 11, color: '#64748b', marginTop: 3 }}>
                              Evidence: <strong>{(r.evidence_type || 'Certificate').replace(/_/g, ' ')}</strong>
                              {r.verification_source && <> · Source: <strong>{r.verification_source}</strong></>}
                            </div>
                            {r.clause_text && <div style={{ fontSize: 12, color: '#475569', marginTop: 6, fontStyle: 'italic', background: '#f8fafc', padding: '6px 10px', borderRadius: 6, border: '1px solid #e2e8f0' }}>"{r.clause_text}"</div>}
                          </div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end', flexShrink: 0 }}>
                            <span style={{ fontSize: 10, fontWeight: 800, padding: '2px 7px', borderRadius: 4, background: `${sc}18`, color: sc, border: `1px solid ${sc}30` }}>{r.severity || 'CRITICAL'}</span>
                            {r.is_mandatory !== false && <span style={{ fontSize: 9, fontWeight: 700, color: '#991b1b', background: '#fee2e2', border: '1px solid #fca5a5', padding: '2px 5px', borderRadius: 3 }}>MANDATORY</span>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: '14px 24px', borderTop: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            {confirmDelete ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 12, color: '#dc2626', fontWeight: 700 }}>Are you sure?</span>
                <button onClick={handleDelete} disabled={deleting} style={{ padding: '6px 12px', borderRadius: 6, border: 'none', background: '#dc2626', color: '#fff', fontSize: 12, fontWeight: 700, cursor: deleting ? 'wait' : 'pointer' }}>{deleting ? 'Deleting...' : 'Yes, Delete'}</button>
                <button onClick={() => setConfirmDelete(false)} disabled={deleting} style={{ padding: '6px 12px', borderRadius: 6, border: '1px solid #cbd5e1', background: '#f8fafc', color: '#475569', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
              </div>
            ) : (
              <button onClick={() => setConfirmDelete(true)} style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid rgba(239, 68, 68, 0.35)', background: 'rgba(239, 68, 68, 0.08)', color: '#dc2626', fontWeight: 700, fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
                <Trash2 size={14}/> Delete Tender
              </button>
            )}
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button onClick={() => navigate(`/corrigendum`)} style={{ padding: '9px 18px', borderRadius: 8, border: '1px solid #fde68a', background: '#fffbeb', color: '#d97706', fontSize: 13, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}><Edit size={14}/> Corrigendum</button>
            <button onClick={() => navigate(`/bids?tenderId=${encodeURIComponent(tId)}`)} style={{ padding: '9px 20px', borderRadius: 8, border: 'none', background: 'linear-gradient(135deg,#d97706,#b45309)', color: '#fff', fontSize: 13, fontWeight: 800, cursor: 'pointer', boxShadow: '0 2px 8px rgba(217,119,6,0.3)' }}>View Bids →</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Create New Tender Form ──────────────────────────────────────────────────
function CreateTenderTab({ onCreated, onCancel }) {
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [newTender, setNewTender] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [compiledRules, setCompiledRules] = useState([]);
  const [uploadedFile, setUploadedFile] = useState(null);

  const [form, setForm] = useState({
    title: '', reference_number: '', authority: '', estimated_value_cr: '',
    turnover_threshold_cr: '10', local_content_pct: '50', closing_date: '',
  });

  function set(field, val) { setForm(prev => ({ ...prev, [field]: val })); }

  async function handleCreateTender(e) {
    e.preventDefault();
    setSaving(true); setError(null);
    try {
      const payload = {
        ...form,
        tender_no: form.reference_number,
        estimated_value_cr: parseFloat(form.estimated_value_cr) || 0,
        turnover_threshold_cr: parseFloat(form.turnover_threshold_cr) || 10,
        local_content_pct: parseFloat(form.local_content_pct) || 50,
        status: 'DRAFT',
      };
      const result = await createTender(payload);
      setNewTender(result);
      setStep(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create tender.');
    } finally {
      setSaving(false);
    }
  }

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setError(null); setUploadedFile(file);
    try {
      const tId = newTender.id || newTender._id || newTender.tender_no;
      const result = await uploadTenderDocument(tId, file, () => {});
      
      const isTender = result?.is_tender !== false;
      const rules = result?.rules || result?.requirement_rules || [];
      
      if (!isTender) {
        setError(`⚠️ The uploaded document does not appear to be an official RFP (${result?.diagnostics?.detection_reason}). Continuing with baseline rules.`);
      }
      setCompiledRules(rules.length > 0 ? rules : (newTender?.requirement_rules || []));
      setStep(3);
    } catch (err) {
      setError(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
    }
  }

  async function handlePublish() {
    setSaving(true);
    try {
      const tId = newTender.id || newTender._id || newTender.tender_no;
      await updateTender(tId, { status: 'ACTIVE', requirement_rules: compiledRules });
      onCreated({ ...newTender, status: 'ACTIVE', requirement_rules: compiledRules, filename: uploadedFile?.name });
    } catch (err) {
      setError('Publish failed: ' + err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', background: '#fff', borderRadius: 12, border: '1px solid #e2e8f0', overflow: 'hidden', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)' }}>
      {/* Steps Header */}
      <div style={{ display: 'flex', background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
        {[
          { num: 1, title: 'Tender Details', active: step === 1, done: step > 1 },
          { num: 2, title: 'Upload RFP', active: step === 2, done: step > 2 },
          { num: 3, title: 'Review & Publish', active: step === 3, done: step > 3 }
        ].map(s => (
          <div key={s.num} style={{ flex: 1, padding: '16px', textAlign: 'center', fontSize: 13, fontWeight: s.active ? 800 : 600, color: s.active ? '#d97706' : s.done ? '#166534' : '#64748b', background: s.active ? '#fff' : s.done ? '#f0fdf4' : 'transparent', borderBottom: s.active ? '2px solid #d97706' : 'none' }}>
            {s.done ? '✓' : `${s.num}.`} {s.title}
          </div>
        ))}
      </div>

      <div style={{ padding: '32px' }}>
        {error && <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', padding: '12px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, marginBottom: 20 }}>{error}</div>}

        {step === 1 && (
          <form onSubmit={handleCreateTender}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 6 }}>Tender Title *</label>
                <input required value={form.title} onChange={e => set('title', e.target.value)} placeholder="e.g. Supply of Equipment" style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #cbd5e1', boxSizing: 'border-box' }}/>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 6 }}>Reference Number *</label>
                <input required value={form.reference_number} onChange={e => set('reference_number', e.target.value)} placeholder="e.g. GEM/2026/001" style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #cbd5e1', boxSizing: 'border-box' }}/>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 6 }}>Issuing Authority *</label>
                <input required value={form.authority} onChange={e => set('authority', e.target.value)} placeholder="e.g. Ministry of Defense" style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #cbd5e1', boxSizing: 'border-box' }}/>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 6 }}>Closing Date *</label>
                <input required type="date" value={form.closing_date} onChange={e => set('closing_date', e.target.value)} style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #cbd5e1', boxSizing: 'border-box' }}/>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 6 }}>Est. Value (Cr)</label>
                <input type="number" value={form.estimated_value_cr} onChange={e => set('estimated_value_cr', e.target.value)} placeholder="e.g. 50" style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #cbd5e1', boxSizing: 'border-box' }}/>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: '#475569', marginBottom: 6 }}>Min Turnover (Cr)</label>
                <input type="number" value={form.turnover_threshold_cr} onChange={e => set('turnover_threshold_cr', e.target.value)} placeholder="10" style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #cbd5e1', boxSizing: 'border-box' }}/>
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button type="button" onClick={onCancel} style={{ padding: '10px 20px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', color: '#475569', fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
              <button type="submit" disabled={saving} style={{ padding: '10px 24px', borderRadius: 8, border: 'none', background: '#d97706', color: '#fff', fontWeight: 800, cursor: saving ? 'wait' : 'pointer' }}>{saving ? 'Saving...' : 'Next: Upload RFP →'}</button>
            </div>
          </form>
        )}

        {step === 2 && (
          <div style={{ textAlign: 'center', padding: '40px 20px' }}>
            <h3 style={{ margin: '0 0 10px', fontSize: 18, fontWeight: 800, color: '#0f172a' }}>Upload Tender Document (RFP)</h3>
            <p style={{ fontSize: 13, color: '#64748b', marginBottom: 30 }}>RashtraBid AI will automatically extract technical and financial eligibility rules from the PDF.</p>
            
            <label style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', width: '100%', maxWidth: 400, height: 180, border: '2px dashed #cbd5e1', borderRadius: 12, background: '#f8fafc', cursor: uploading ? 'wait' : 'pointer', transition: '0.2s' }}>
              {uploading ? (
                <>
                  <Loader2 className="animate-spin" size={32} color="#d97706" style={{ marginBottom: 12 }} />
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#d97706' }}>Analyzing RFP with AI...</div>
                </>
              ) : (
                <>
                  <UploadCloud size={32} color="#64748b" style={{ marginBottom: 12 }} />
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a', marginBottom: 4 }}>Click or drag PDF here</div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>PDF up to 50MB</div>
                  <input type="file" accept=".pdf" style={{ display: 'none' }} onChange={handleUpload} disabled={uploading} />
                </>
              )}
            </label>
          </div>
        )}

        {step === 3 && (
          <div>
            <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: '16px', marginBottom: 24 }}>
              <h4 style={{ margin: '0 0 8px', fontSize: 14, fontWeight: 800, color: '#166534', display: 'flex', alignItems: 'center', gap: 6 }}><CheckCircle2 size={16}/> {compiledRules.length} Rules Extracted</h4>
              <p style={{ margin: 0, fontSize: 12, color: '#15803d' }}>Review the extracted rules before publishing. Any changes after publishing will require a formal Corrigendum.</p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 30 }}>
              {compiledRules.map((r, i) => {
                const tv = r.threshold_value || r.threshold;
                const showThreshold = tv && !['ACTIVE', 'EXISTS', 'True', 'CONSISTENT', true].includes(tv);
                return (
                  <div key={i} style={{ padding: '12px 16px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 800, color: '#0f172a' }}>
                        {r.requirement_id || r.clause_id}: {r.description || (r.metric || '').replace(/_/g, ' ').toUpperCase()}
                        {showThreshold && <span style={{ color: '#166534', fontWeight: 900 }}> ≥ {tv} {r.unit || r.threshold_unit}</span>}
                      </div>
                      <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>Evidence: {(r.evidence_type || 'Certificate').replace(/_/g, ' ')}</div>
                    </div>
                    {r.is_mandatory !== false && <span style={{ fontSize: 10, fontWeight: 700, color: '#991b1b', background: '#fee2e2', padding: '2px 6px', borderRadius: 4 }}>MANDATORY</span>}
                  </div>
                )
              })}
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <button onClick={() => setStep(2)} style={{ padding: '10px 20px', borderRadius: 8, border: '1px solid #cbd5e1', background: '#fff', color: '#475569', fontWeight: 600, cursor: 'pointer' }}>← Back</button>
              <button onClick={handlePublish} disabled={saving} style={{ padding: '10px 24px', borderRadius: 8, border: 'none', background: 'linear-gradient(135deg,#16a34a,#15803d)', color: '#fff', fontWeight: 800, cursor: saving ? 'wait' : 'pointer', display: 'flex', alignItems: 'center', gap: 6, boxShadow: '0 2px 8px rgba(22,163,74,0.3)' }}>
                {saving ? 'Publishing...' : <><Send size={15}/> Publish Tender</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
