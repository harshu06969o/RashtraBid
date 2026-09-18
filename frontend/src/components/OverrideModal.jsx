/**
 * Stage 8 — Override Modal (Pure JavaScript)
 */

import { useState } from 'react';
import { submitOfficerOverride } from '../api/client';

const RESULT_OPTIONS = ['ACCEPT', 'REJECT', 'SEEK_CLARIFICATION', 'MARK_PENDING'];

const RESULT_STYLE = {
  PASS:               { color: '#166534', bg: '#dcfce7' },
  FAIL:               { color: '#991b1b', bg: '#fee2e2' },
  REVIEW:             { color: '#92400e', bg: '#fef3c7' },
  PENDING:            { color: '#1e40af', bg: '#dbeafe' },
  MISSING:            { color: '#6b21a8', bg: '#f3e8ff' },
  EXPIRED:            { color: '#7f1d1d', bg: '#fef2f2' },
  NOT_APPLICABLE:     { color: '#374151', bg: '#f3f4f6' },
  ACCEPT:             { color: '#166534', bg: '#dcfce7' },
  REJECT:             { color: '#991b1b', bg: '#fee2e2' },
  SEEK_CLARIFICATION: { color: '#92400e', bg: '#fef3c7' },
  MARK_PENDING:       { color: '#1e40af', bg: '#dbeafe' },
};

export default function OverrideModal({
  bidId, bidderName, ruleType, currentResult, ruleResultId: _ruleResultId, onClose, onSuccess,
}) {
  const [newDecision, setNewDecision] = useState('ACCEPT');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const canSubmit = reason.trim().length >= 10; // min 10 chars

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      // Use the dedicated /override endpoint with correct OfficerOverrideRequest schema
      await submitOfficerOverride(String(bidId), {
        justification: `Rule [${ruleType}] override: ${currentResult} → ${newDecision}. Officer justification: ${reason.trim()}`,
        new_status: newDecision === 'ACCEPT' ? 'PASS' : newDecision === 'REJECT' ? 'FAIL' : newDecision,
        actor: 'officer@gem.gov.in',
        metric: ruleType,
        notes: reason.trim(),
      });
      onSuccess();
      onClose();
    } catch (e) {
      const msg = e?.message || (typeof e === 'object' ? JSON.stringify(e) : String(e));
      setError(msg || 'Override failed');
    } finally {
      setSubmitting(false);
    }
  }

  const fromStyle = RESULT_STYLE[currentResult] ?? { color: '#374151', bg: '#f3f4f6' };
  const toStyle   = RESULT_STYLE[newDecision]   ?? { color: '#374151', bg: '#f3f4f6' };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(15,23,42,0.6)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 16,
    }}>
      <div style={{
        background: '#fff', borderRadius: 16, width: '100%', maxWidth: 500,
        boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          background: 'linear-gradient(135deg, #1e3a5f 0%, #1e40af 100%)',
          padding: '18px 24px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#fff' }}>
              ⚖️ Officer Override
            </div>
            <div style={{ fontSize: 11, color: '#93c5fd', marginTop: 2 }}>
              {bidderName} — {ruleType.replace(/_/g, ' ')}
            </div>
          </div>
          <button
            id="btn-override-close"
            onClick={onClose}
            style={{
              background: 'rgba(255,255,255,0.15)', border: 'none', borderRadius: 8,
              color: '#fff', cursor: 'pointer', padding: '4px 10px', fontSize: 16,
            }}
          >
            ✕
          </button>
        </div>

        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Current Result */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Current Engine Result
            </div>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              padding: '6px 14px', borderRadius: 8,
              background: fromStyle.bg, color: fromStyle.color,
              fontWeight: 800, fontSize: 13,
              border: `1.5px solid ${fromStyle.color}20`,
            }}>
              {currentResult}
              <span style={{ fontSize: 10, opacity: 0.7, fontWeight: 400 }}>
                — set by deterministic rule engine
              </span>
            </div>
          </div>

          {/* Arrow */}
          <div style={{ textAlign: 'center', fontSize: 20, color: '#94a3b8' }}>↓</div>

          {/* New Decision */}
          <div>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Officer Decision
            </label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
              {RESULT_OPTIONS.map(opt => {
                const s = RESULT_STYLE[opt] ?? { color: '#374151', bg: '#f3f4f6' };
                const selected = newDecision === opt;
                return (
                  <button
                    key={opt}
                    id={`btn-override-to-${opt.toLowerCase()}`}
                    onClick={() => setNewDecision(opt)}
                    style={{
                      padding: '6px 14px', borderRadius: 8, fontSize: 11, fontWeight: 700,
                      border: selected ? `2px solid ${s.color}` : '2px solid #e2e8f0',
                      background: selected ? s.bg : '#fff',
                      color: selected ? s.color : '#64748b',
                      cursor: 'pointer',
                    }}
                  >
                    {opt.replace(/_/g, ' ')}
                  </button>
                );
              })}
            </div>
            {newDecision && (
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 11, color: '#94a3b8' }}>Final decision will be:</span>
                <span style={{
                  padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
                  background: toStyle.bg, color: toStyle.color,
                }}>
                  {newDecision}
                </span>
              </div>
            )}
          </div>

          {/* Reason — mandatory */}
          <div>
            <label
              htmlFor="override-reason"
              style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', justifyContent: 'space-between' }}
            >
              <span>Justification <span style={{ color: '#dc2626' }}>*</span></span>
              <span style={{ fontWeight: 400, color: reason.trim().length < 10 ? '#dc2626' : '#16a34a' }}>
                {reason.trim().length}/min 10 chars
              </span>
            </label>
            <textarea
              id="override-reason"
              value={reason}
              onChange={e => setReason(e.target.value)}
              placeholder="Enter detailed justification for overriding the engine result. This will be recorded in the immutable audit log and may be reviewed during procurement audit."
              rows={4}
              style={{
                width: '100%', marginTop: 6, padding: '10px 12px',
                border: `1.5px solid ${reason.trim().length >= 10 ? '#86efac' : reason.length > 0 ? '#fca5a5' : '#e2e8f0'}`,
                borderRadius: 8, fontSize: 12, resize: 'vertical',
                outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
              }}
            />
          </div>

          {/* Accountability notice */}
          <div style={{
            background: '#fef3c7', border: '1px solid #fcd34d', borderRadius: 8,
            padding: '8px 12px', fontSize: 11, color: '#92400e',
            display: 'flex', gap: 8, alignItems: 'flex-start',
          }}>
            <span style={{ flexShrink: 0, fontSize: 14 }}>⚠️</span>
            <span>
              This override will be permanently recorded in the audit log with your identity,
              timestamp, and SHA-256 chain hash. RashtraBid does not make procurement decisions —
              you are the accountable authority.
            </span>
          </div>

          {/* Error */}
          {error && (
            <div style={{ background: '#fee2e2', borderRadius: 8, padding: '8px 12px', color: '#991b1b', fontSize: 12 }}>
              ⛔ {error}
            </div>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button
              id="btn-override-cancel"
              onClick={onClose}
              disabled={submitting}
              style={{
                padding: '8px 20px', borderRadius: 8, border: '1.5px solid #e2e8f0',
                background: '#fff', color: '#64748b', cursor: 'pointer',
                fontSize: 12, fontWeight: 700,
              }}
            >
              Cancel
            </button>
            <button
              id="btn-override-confirm"
              onClick={handleSubmit}
              disabled={!canSubmit || submitting}
              style={{
                padding: '8px 20px', borderRadius: 8, border: 'none',
                background: canSubmit && !submitting ? '#1e3a5f' : '#94a3b8',
                color: '#fff', cursor: canSubmit && !submitting ? 'pointer' : 'not-allowed',
                fontSize: 12, fontWeight: 700,
              }}
            >
              {submitting ? '⏳ Submitting…' : '✓ Confirm Override'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
