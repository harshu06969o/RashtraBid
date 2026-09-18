/**
 * RashtraBid v6.0 — Financial Evaluator Workspace
 * RBAC: FINANCIAL_EVALUATOR only
 * Features:
 *   - Shows ONLY bids where compliance_status == COMPLIANT (tech-cleared)
 *   - Financial Envelope Unsealing (hard-blocked for non-PASS bids)
 *   - MII / MSE Preference Calculator
 *   - L1 Ranking Table (Make-in-India adjusted)
 */

import { useEffect, useState } from 'react';
import { useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import {
  listTenders, getTenderBids, unsealBid, getL1Ranking,
} from '../api/client';

// ─── Palette ──────────────────────────────────────────────────────────────────
const C = {
  bg: '#0a0f1e',
  surface: 'rgba(255,255,255,0.04)',
  border: 'rgba(255,255,255,0.08)',
  gold: '#f59e0b',
  goldBg: 'rgba(245,158,11,0.12)',
  goldBorder: 'rgba(245,158,11,0.3)',
  green: '#10b981',
  greenBg: 'rgba(16,185,129,0.12)',
  red: '#ef4444',
  redBg: 'rgba(239,68,68,0.12)',
  blue: '#3b82f6',
  blueBg: 'rgba(59,130,246,0.12)',
  muted: '#64748b',
  text: '#f1f5f9',
  textDim: '#94a3b8',
};

const card = {
  background: C.surface,
  border: `1px solid ${C.border}`,
  borderRadius: 16,
  padding: '24px',
};

function StatusPill({ status }) {
  const MAP = {
    COMPLIANT: { bg: C.greenBg, color: C.green, label: '✓ COMPLIANT' },
    NON_COMPLIANT: { bg: C.redBg, color: C.red, label: '✗ NON-COMPLIANT' },
    UNDER_REVIEW: { bg: 'rgba(245,158,11,0.12)', color: C.gold, label: '⏳ UNDER REVIEW' },
    PENDING: { bg: 'rgba(100,116,139,0.12)', color: C.muted, label: '○ PENDING' },
    PASS: { bg: C.greenBg, color: C.green, label: '✓ PASS' },
    FAIL: { bg: C.redBg, color: C.red, label: '✗ FAIL' },
    SEALED: { bg: C.goldBg, color: C.gold, label: '🔒 SEALED' },
    UNSEALED: { bg: C.greenBg, color: C.green, label: '🔓 UNSEALED' },
  };
  const s = MAP[status] || { bg: 'rgba(255,255,255,0.05)', color: C.textDim, label: status };
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 10px',
      borderRadius: 20, fontSize: 11, fontWeight: 700,
      background: s.bg, color: s.color,
    }}>{s.label}</span>
  );
}

function MIIBadge({ miiClass, isMse }) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {miiClass && (
        <span style={{
          padding: '2px 8px', borderRadius: 12, fontSize: 10, fontWeight: 700,
          background: miiClass === 'CLASS_I' ? 'rgba(16,185,129,0.15)' : 'rgba(59,130,246,0.15)',
          color: miiClass === 'CLASS_I' ? C.green : C.blue,
        }}>MII {miiClass?.replace('_', ' ')}</span>
      )}
      {isMse && (
        <span style={{
          padding: '2px 8px', borderRadius: 12, fontSize: 10, fontWeight: 700,
          background: 'rgba(139,92,246,0.15)', color: '#8b5cf6',
        }}>MSE ✓</span>
      )}
    </div>
  );
}

export default function FinancialWorkspacePage() {
  const navigate = useNavigate();
  const authState = useSelector(s => s.auth);
  const role = authState?.role || localStorage.getItem('role');

  const [tenders, setTenders] = useState([]);
  const [selectedTender, setSelectedTender] = useState(null);
  const [bids, setBids] = useState([]);
  const [l1Data, setL1Data] = useState(null);
  const [loading, setLoading] = useState(false);
  const [l1Loading, setL1Loading] = useState(false);
  const [unsealingId, setUnsealingId] = useState(null);
  const [resetting, setResetting] = useState(false);
  const [banner, setBanner] = useState(null);
  const [notes, setNotes] = useState('');

  // Guard: only FINANCIAL_EVALUATOR
  useEffect(() => {
    if (role && role !== 'FINANCIAL_EVALUATOR') {
      navigate('/dashboard', { replace: true });
    }
  }, [role]);

  useEffect(() => { loadTenders(); }, []);

  async function loadTenders() {
    setLoading(true);
    try {
      const data = await listTenders();
      const list = Array.isArray(data) ? data : (data?.tenders || data?.items || []);
      setTenders(list);
      if (list.length > 0 && !selectedTender) {
        await selectTender(list[0]);
      }
    } catch (e) {
      setBanner({ type: 'error', msg: e.message });
    } finally {
      setLoading(false);
    }
  }

  async function selectTender(tender) {
    setSelectedTender(tender);
    setBids([]);
    setL1Data(null);
    try {
      const data = await getTenderBids(tender.id || tender._id);
      const list = Array.isArray(data) ? data : (data?.bids || []);
      setBids(list);
    } catch (e) {
      // Fallback: no bids yet
      setBids([]);
    }
  }

  async function handleUnseal(bid) {
    setUnsealingId(bid.id);
    try {
      const res = await unsealBid(bid.id, { actor: 'financial@gem.gov.in', notes });
      setBanner({ type: 'success', msg: `✓ Bid #${bid.id.slice(-6).toUpperCase()} unsealed successfully. Financial data is now accessible.` });
      // Refresh bids
      await selectTender(selectedTender);
    } catch (e) {
      setBanner({ type: 'error', msg: `Unseal failed: ${e.message}` });
    } finally {
      setUnsealingId(null);
    }
  }

  async function handleL1() {
    if (!selectedTender) return;
    setL1Loading(true);
    try {
      const data = await getL1Ranking(selectedTender.id || selectedTender._id);
      setL1Data(data);
    } catch (e) {
      setBanner({ type: 'error', msg: `L1 calculation failed: ${e.message}` });
    } finally {
      setL1Loading(false);
    }
  }

  // Only show COMPLIANT bids for unsealing
  const passedBids = bids.filter(b =>
    ['COMPLIANT', 'PASS'].includes(b.compliance_status || b.overall_status || '')
  );
  const blockedBids = bids.filter(b =>
    !['COMPLIANT', 'PASS'].includes(b.compliance_status || b.overall_status || '')
  );

  return (
    <div style={{ minHeight: '100vh', background: C.bg, fontFamily: "'Inter', sans-serif", color: C.text }}>
      {/* Header */}
      <div style={{
        borderBottom: `1px solid ${C.border}`,
        background: 'rgba(255,255,255,0.02)',
        padding: '20px 32px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 12,
            background: 'linear-gradient(135deg, #f59e0b, #d97706)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 20, boxShadow: '0 4px 16px rgba(245,158,11,0.4)',
          }}>💰</div>
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: C.text }}>
              Financial Evaluator Workspace
            </h1>
            <p style={{ margin: 0, fontSize: 12, color: C.muted }}>
              Envelope Unsealing · MII/MSE Preferences · L1 Ranking — GFR 2017 Compliant
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{
            padding: '6px 14px', borderRadius: 20, fontSize: 11, fontWeight: 700,
            background: C.goldBg, color: C.gold, border: `1px solid ${C.goldBorder}`,
          }}>💰 FINANCIAL_EVALUATOR</span>

        </div>
      </div>

      {banner && (
        <div style={{
          margin: '16px 32px',
          padding: '12px 16px', borderRadius: 10,
          background: banner.type === 'error' ? C.redBg : C.greenBg,
          border: `1px solid ${banner.type === 'error' ? 'rgba(239,68,68,0.3)' : 'rgba(16,185,129,0.3)'}`,
          color: banner.type === 'error' ? '#fca5a5' : '#6ee7b7',
          fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          {banner.msg}
          <button onClick={() => setBanner(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: 18 }}>×</button>
        </div>
      )}

      <div style={{ padding: '24px 32px', display: 'grid', gridTemplateColumns: '280px 1fr', gap: 24, maxWidth: 1400, margin: '0 auto' }}>
        {/* Left: Tender List */}
        <div>
          <div style={{ ...card, marginBottom: 16 }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 13, fontWeight: 700, color: C.textDim, letterSpacing: '0.08em' }}>
              ACTIVE TENDERS
            </h3>
            {loading ? (
              <div style={{ textAlign: 'center', padding: 24, color: C.muted }}>⏳ Loading…</div>
            ) : tenders.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 24, color: C.muted, fontSize: 12 }}>
                No tenders found.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {tenders.map(t => (
                  <button
                    key={t.id || t._id}
                    onClick={() => selectTender(t)}
                    style={{
                      padding: '12px 14px', borderRadius: 10, border: `1px solid ${(selectedTender?.id || selectedTender?._id) === (t.id || t._id) ? C.goldBorder : C.border}`,
                      background: (selectedTender?.id || selectedTender?._id) === (t.id || t._id) ? C.goldBg : 'transparent',
                      color: C.text, cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
                    }}
                  >
                    <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 4 }}>{t.title || t.tender_no || t.reference_number}</div>
                    <div style={{ fontSize: 10, color: C.muted }}>{t.reference_number || t.tender_no}</div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* L1 Ranking Trigger */}
          {selectedTender && (
            <div style={card}>
              <h3 style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 700, color: C.textDim }}>L1 DETERMINATION</h3>
              <p style={{ fontSize: 11, color: C.muted, margin: '0 0 14px' }}>
                Ranks all technically-passed bids by adjusted price (MII + MSE preferences applied per GFR 2017).
              </p>
              <button onClick={handleL1} disabled={l1Loading}
                style={{
                  width: '100%', padding: '10px', borderRadius: 8, border: 'none',
                  background: l1Loading ? '#374151' : 'linear-gradient(135deg, #f59e0b, #d97706)',
                  color: '#fff', fontWeight: 700, fontSize: 13, cursor: l1Loading ? 'not-allowed' : 'pointer',
                  boxShadow: l1Loading ? 'none' : '0 4px 12px rgba(245,158,11,0.4)',
                }}>
                {l1Loading ? '⏳ Calculating…' : '📊 Calculate L1 Ranking'}
              </button>
            </div>
          )}
        </div>

        {/* Right: Main Content */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* L1 Ranking Table */}
          {l1Data && (
            <div style={card}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800 }}>📊 L1 Ranking — Make-in-India Adjusted</h2>
                <span style={{ fontSize: 11, color: C.muted }}>Calculated at {new Date().toLocaleTimeString()}</span>
              </div>
              {l1Data.rankings && l1Data.rankings.length > 0 ? (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                      {['Rank', 'Bidder', 'Quoted Price', 'MII Class', 'MSE', 'Adjusted Price'].map(h => (
                        <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: C.muted, letterSpacing: '0.05em' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {l1Data.rankings.map((r, i) => (
                      <tr key={r.bid_id || i}
                        style={{ borderBottom: `1px solid ${C.border}`, background: i === 0 ? 'rgba(245,158,11,0.06)' : 'transparent' }}>
                        <td style={{ padding: '12px 14px' }}>
                          {i === 0 ? (
                            <span style={{ background: C.goldBg, color: C.gold, padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 800 }}>🥇 L1</span>
                          ) : (
                            <span style={{ color: C.textDim, fontWeight: 700, fontSize: 13 }}>#{i + 1}</span>
                          )}
                        </td>
                        <td style={{ padding: '12px 14px', fontSize: 13, fontWeight: 600 }}>{r.bidder_name}</td>
                        <td style={{ padding: '12px 14px', fontSize: 13, fontFamily: 'monospace' }}>
                          ₹{Number(r.quoted_price || 0).toLocaleString('en-IN')}
                        </td>
                        <td style={{ padding: '12px 14px' }}><MIIBadge miiClass={r.mii_class} /></td>
                        <td style={{ padding: '12px 14px', fontSize: 13 }}>{r.is_mse ? '✅' : '—'}</td>
                        <td style={{ padding: '12px 14px', fontSize: 13, fontFamily: 'monospace', fontWeight: 700, color: i === 0 ? C.gold : C.text }}>
                          ₹{Number(r.adjusted_price || 0).toLocaleString('en-IN')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div style={{ padding: '24px', textAlign: 'center', color: C.muted, fontSize: 13 }}>
                  No technically-passed bids available for L1 ranking yet.
                </div>
              )}
            </div>
          )}

          {/* Technically Cleared Bids — Unsealing */}
          {passedBids.length > 0 && (
            <div style={card}>
              <h2 style={{ margin: '0 0 6px', fontSize: 16, fontWeight: 800 }}>
                🔓 Financial Envelope Unsealing
              </h2>
              <p style={{ margin: '0 0 20px', fontSize: 12, color: C.muted }}>
                Only bids cleared by Technical Evaluator are shown. Unsealing is irreversible and appended to the SHA-256 audit chain.
              </p>
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 11, color: C.textDim, fontWeight: 600, display: 'block', marginBottom: 6 }}>
                  EVALUATION NOTES (optional — appended to audit chain)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Financially reviewed per GFR Rule 175(i)"
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  style={{
                    width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 13,
                    background: 'rgba(255,255,255,0.05)', border: `1px solid ${C.border}`,
                    color: C.text, outline: 'none', boxSizing: 'border-box',
                  }}
                />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {passedBids.map(bid => {
                  const isUnsealing = unsealingId === bid.id;
                  const isAlreadyUnsealed = bid.financial_sealed === false || bid.envelope_unsealed;
                  return (
                    <div key={bid.id} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '16px 20px', borderRadius: 12,
                      border: `1px solid ${isAlreadyUnsealed ? 'rgba(16,185,129,0.3)' : C.goldBorder}`,
                      background: isAlreadyUnsealed ? C.greenBg : C.goldBg,
                    }}>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>
                          {bid.bidder?.name || bid.bidder_name || `Bid #${(bid.id || '').slice(-6).toUpperCase()}`}
                        </div>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <StatusPill status={bid.compliance_status || bid.overall_status} />
                          {bid.financial_envelope?.quoted_price && (
                            <span style={{ fontSize: 12, color: C.muted }}>
                              Quoted: ₹{Number(bid.financial_envelope.quoted_price).toLocaleString('en-IN')}
                            </span>
                          )}
                        </div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <StatusPill status={isAlreadyUnsealed ? 'UNSEALED' : 'SEALED'} />
                        {!isAlreadyUnsealed && (
                          <button
                            onClick={() => handleUnseal(bid)}
                            disabled={isUnsealing}
                            style={{
                              padding: '9px 18px', borderRadius: 8, border: 'none',
                              background: isUnsealing ? '#374151' : 'linear-gradient(135deg, #f59e0b, #d97706)',
                              color: '#fff', fontWeight: 700, fontSize: 12, cursor: isUnsealing ? 'not-allowed' : 'pointer',
                              boxShadow: isUnsealing ? 'none' : '0 4px 12px rgba(245,158,11,0.4)',
                            }}>
                            {isUnsealing ? '⏳ Unsealing…' : '🔓 Unseal Envelope'}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Blocked Bids */}
          {blockedBids.length > 0 && (
            <div style={card}>
              <h2 style={{ margin: '0 0 6px', fontSize: 16, fontWeight: 800, color: C.textDim }}>
                🔒 Blocked — Awaiting Technical Clearance
              </h2>
              <p style={{ margin: '0 0 16px', fontSize: 12, color: C.muted }}>
                These bids are locked until the Technical Evaluator marks them as <strong>PASS / COMPLIANT</strong>.
                Financial evaluation is prohibited until then (Two-Envelope Protocol enforced).
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {blockedBids.map(bid => (
                  <div key={bid.id} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '14px 20px', borderRadius: 12,
                    border: `1px solid rgba(100,116,139,0.2)`,
                    background: 'rgba(100,116,139,0.05)',
                    opacity: 0.7,
                  }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4, color: C.textDim }}>
                        {bid.bidder?.name || bid.bidder_name || `Bid #${(bid.id || '').slice(-6).toUpperCase()}`}
                      </div>
                      <StatusPill status={bid.compliance_status || bid.overall_status || 'PENDING'} />
                    </div>
                    <div style={{
                      padding: '8px 16px', borderRadius: 8,
                      background: 'rgba(100,116,139,0.1)', border: '1px solid rgba(100,116,139,0.2)',
                      color: C.muted, fontSize: 12, fontWeight: 600,
                    }}>
                      🔒 Financially Locked
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Empty State */}
          {!loading && bids.length === 0 && selectedTender && (
            <div style={{ ...card, textAlign: 'center', padding: '60px 32px' }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
              <h3 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 700 }}>No Bids Yet</h3>
              <p style={{ color: C.muted, fontSize: 13, margin: '0 0 20px' }}>
                No bids have been submitted for this tender yet, or they haven't been technically evaluated.
              </p>
              <button onClick={handleResetDemo} style={{
                padding: '10px 20px', borderRadius: 8, border: `1px solid ${C.goldBorder}`,
                background: C.goldBg, color: C.gold, fontWeight: 700, fontSize: 13, cursor: 'pointer',
              }}>
                🌱 Seed Benchmark Bids
              </button>
            </div>
          )}

          {/* MII / MSE Info Card */}
          <div style={{ ...card, background: 'rgba(59,130,246,0.05)', borderColor: 'rgba(59,130,246,0.2)' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 700, color: '#60a5fa' }}>
              📋 MII / MSE Preference Rules (GFR 2017 + Order 2020)
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
              {[
                { label: 'Class I Local Supplier', rule: '≥ 50% local content', effect: 'No price disadvantage; purchase preference', color: '#10b981' },
                { label: 'Class II Local Supplier', rule: '20–49% local content', effect: 'Eligible but ranked below Class I', color: '#3b82f6' },
                { label: 'MSE Preference', rule: 'Valid Udyam registration', effect: '25% order reservation; price preference', color: '#8b5cf6' },
              ].map(item => (
                <div key={item.label} style={{
                  padding: '14px', borderRadius: 10,
                  background: `${item.color}0f`, border: `1px solid ${item.color}33`,
                }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: item.color, marginBottom: 6 }}>{item.label}</div>
                  <div style={{ fontSize: 11, color: C.muted, marginBottom: 4 }}>Criteria: {item.rule}</div>
                  <div style={{ fontSize: 11, color: C.textDim }}>{item.effect}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
