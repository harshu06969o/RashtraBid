/**
 * Stage 9 — Corrigendum Impact Analyzer
 * Allows officers to simulate tender amendments (e.g. raising/lowering turnover threshold)
 * and see deterministic what-if bidder impact analysis before issuing a formal corrigendum.
 * Historical results are preserved — never overwritten.
 */

import { useState, useEffect } from 'react';
import { listTenders, runCorrigendumAnalysis } from '../api/client';

const RS = {
  PASS:    { color: '#166534', bg: '#dcfce7', icon: '✓' },
  FAIL:    { color: '#991b1b', bg: '#fee2e2', icon: '✗' },
  REVIEW:  { color: '#92400e', bg: '#fef3c7', icon: '⚠' },
  PENDING: { color: '#1e40af', bg: '#dbeafe', icon: '⏳' },
};

function ResultBadge({ result }) {
  const s = RS[result] ?? { color: '#374151', bg: '#f3f4f6', icon: '—' };
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
      color: s.color, background: s.bg,
    }}>
      {s.icon} {result}
    </span>
  );
}

export default function CorrigendumPage() {
  const [tenders, setTenders] = useState([]);
  const [selectedTenderId, setSelectedTenderId] = useState('');
  const [ruleType, setRuleType] = useState('TURNOVER');
  const [newThreshold, setNewThreshold] = useState('10.0');
  const [notes, setNotes] = useState('Corrigendum amendment to financial eligibility turnover requirements.');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    listTenders()
      .then(t => {
        setTenders(t);
        if (t.length > 0) setSelectedTenderId(t[0].id);
      })
      .catch(e => setError(e.message));
  }, []);

  async function handleAnalyze() {
    if (!selectedTenderId) {
      setError('Please select an active tender first');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const data = await runCorrigendumAnalysis({
        tender_id: selectedTenderId,
        changed_rule_type: ruleType,
        new_threshold_value: newThreshold,
        amendment_notes: notes,
      });
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Corrigendum analysis failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '28px 24px', fontFamily: 'inherit' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
          <span style={{ fontSize: 32 }}>📝</span>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: '#1e3a5f' }}>
              Corrigendum Impact Analyzer
            </h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>
              Simulate rule amendments and evaluate deterministic impact on submitted bids before issuing corrigendum
            </p>
          </div>
        </div>
      </div>

      {/* Tender & Rule Configuration Card */}
      <div style={{
        background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14,
        padding: '24px', boxShadow: '0 2px 8px rgba(0,0,0,0.04)', marginBottom: 24,
      }}>
        <div style={{ fontWeight: 800, fontSize: 14, color: '#1e3a5f', marginBottom: 16 }}>
          🛠️ Configure Corrigendum Simulation Parameters
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16, marginBottom: 16 }}>
          {/* Select Tender */}
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#475569', marginBottom: 6 }}>
              Target Tender
            </label>
            <select
              value={selectedTenderId}
              onChange={e => setSelectedTenderId(e.target.value)}
              style={{
                width: '100%', padding: '9px 12px', borderRadius: 8, border: '1px solid #cbd5e1',
                fontSize: 13, color: '#1e293b', background: '#fff',
              }}
            >
              {tenders.map(t => (
                <option key={t.id} value={t.id}>
                  {t.reference_number} — {t.title}
                </option>
              ))}
              {tenders.length === 0 && <option value="">No tenders found</option>}
            </select>
          </div>

          {/* Rule Type */}
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#475569', marginBottom: 6 }}>
              Rule to Amend
            </label>
            <select
              value={ruleType}
              onChange={e => setRuleType(e.target.value)}
              style={{
                width: '100%', padding: '9px 12px', borderRadius: 8, border: '1px solid #cbd5e1',
                fontSize: 13, color: '#1e293b', background: '#fff',
              }}
            >
              <option value="TURNOVER">Average Annual Turnover (₹ Crore)</option>
              <option value="MII_PERCENT">Make In India Local Content (%)</option>
              <option value="GST_ACTIVE">GST Registration Active Status</option>
            </select>
          </div>

          {/* New Threshold */}
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#475569', marginBottom: 6 }}>
              New Threshold Value
            </label>
            <input
              type="text"
              value={newThreshold}
              onChange={e => setNewThreshold(e.target.value)}
              placeholder="e.g. 10.0"
              style={{
                width: '100%', padding: '9px 12px', borderRadius: 8, border: '1px solid #cbd5e1',
                fontSize: 13, color: '#1e293b', boxSizing: 'border-box',
              }}
            />
          </div>
        </div>

        {/* Amendment Notes */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#475569', marginBottom: 6 }}>
            Corrigendum Justification / Notes
          </label>
          <input
            type="text"
            value={notes}
            onChange={e => setNotes(e.target.value)}
            style={{
              width: '100%', padding: '9px 12px', borderRadius: 8, border: '1px solid #cbd5e1',
              fontSize: 13, color: '#1e293b', boxSizing: 'border-box',
            }}
          />
        </div>

        <button
          onClick={handleAnalyze}
          disabled={loading || !selectedTenderId}
          id="btn-run-corrigendum-analysis"
          style={{
            background: loading ? '#94a3b8' : 'linear-gradient(135deg, #1e3a5f, #1e40af)',
            color: '#fff', border: 'none', borderRadius: 8,
            padding: '10px 24px', fontSize: 13, fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer',
            boxShadow: '0 2px 8px rgba(30,58,95,0.25)',
          }}
        >
          {loading ? '⏳ Analyzing Impact…' : '⚡ Simulate Corrigendum Impact'}
        </button>
      </div>

      {error && (
        <div style={{
          background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: 8,
          padding: '12px 16px', color: '#991b1b', fontSize: 13, marginBottom: 20,
        }}>
          ⚠ {error}
        </div>
      )}

      {/* Analysis Results Display */}
      {result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Summary stats */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
            <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, padding: 16, textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#1e3a5f' }}>{result.total_bids_analyzed}</div>
              <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', marginTop: 4 }}>Bids Analyzed</div>
            </div>
            <div style={{ background: '#fee2e2', border: '1px solid #fca5a5', borderRadius: 10, padding: 16, textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#991b1b' }}>{result.total_affected}</div>
              <div style={{ fontSize: 11, color: '#991b1b', fontWeight: 600, textTransform: 'uppercase', marginTop: 4 }}>Bidders Affected</div>
            </div>
            <div style={{ background: '#dcfce7', border: '1px solid #86efac', borderRadius: 10, padding: 16, textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#166534' }}>{result.total_unchanged}</div>
              <div style={{ fontSize: 11, color: '#166534', fontWeight: 600, textTransform: 'uppercase', marginTop: 4 }}>Unchanged Bidders</div>
            </div>
          </div>

          {/* Threshold Diff Card */}
          <div style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: '16px 20px',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12,
          }}>
            <div>
              <span style={{ fontSize: 11, color: '#64748b', textTransform: 'uppercase', fontWeight: 700 }}>Rule Amended: </span>
              <strong style={{ color: '#1e293b' }}>{result.changed_rule_type}</strong>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ background: '#f1f5f9', padding: '4px 10px', borderRadius: 6, fontSize: 12, color: '#64748b' }}>
                Previous: <strong>₹{result.old_threshold || '—'} Cr</strong>
              </span>
              <span>➔</span>
              <span style={{ background: '#dbeafe', padding: '4px 10px', borderRadius: 6, fontSize: 12, color: '#1e40af' }}>
                Revised: <strong>₹{result.new_threshold} Cr</strong>
              </span>
            </div>
          </div>

          {/* Bidder Impact Breakdown Table */}
          <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid #f1f5f9', fontWeight: 800, fontSize: 13, color: '#1e3a5f' }}>
              👥 Projected Bidder Compliance Shifts
            </div>
            {result.bidder_impacts.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
                No submitted bids found for this tender to analyze.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', textAlign: 'left', color: '#64748b' }}>
                    <th style={{ padding: '10px 16px' }}>Bidder Name</th>
                    <th style={{ padding: '10px 16px' }}>Declared Metric</th>
                    <th style={{ padding: '10px 16px' }}>Previous Status</th>
                    <th style={{ padding: '10px 16px' }}>Projected Status</th>
                    <th style={{ padding: '10px 16px' }}>Required Officer Action</th>
                  </tr>
                </thead>
                <tbody>
                  {result.bidder_impacts.map((item, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9', background: item.changed ? '#fffbeb' : '#fff' }}>
                      <td style={{ padding: '12px 16px', fontWeight: 600, color: '#1e293b' }}>
                        {item.bidder_name}
                      </td>
                      <td style={{ padding: '12px 16px', color: '#64748b' }}>
                        {item.metric_value != null ? `₹${item.metric_value} Cr` : '—'}
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <ResultBadge result={item.old_result} />
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <ResultBadge result={item.new_result} />
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <span style={{
                          padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 800,
                          background: item.action_required === 'DISQUALIFY' ? '#fee2e2' : (item.action_required === 'RE_EVALUATE' ? '#fef3c7' : '#f1f5f9'),
                          color: item.action_required === 'DISQUALIFY' ? '#991b1b' : (item.action_required === 'RE_EVALUATE' ? '#92400e' : '#64748b'),
                        }}>
                          {item.action_required}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Audit Note */}
          <div style={{
            background: '#f8fafc', borderRadius: 10, padding: '12px 16px',
            border: '1px solid #e2e8f0', fontSize: 11, color: '#64748b', lineHeight: 1.6,
          }}>
            🔐 <strong>Read-Only Simulation Notice:</strong> {result.analysis_note}
            Existing evaluations and official audit logs are never modified by simulation.
          </div>
        </div>
      )}
    </div>
  );
}
