/**
 * Stage 7 — Compliance Evidence Trace (Pure JavaScript)
 */

import { useState, useEffect } from 'react';
import { getComplianceTrace } from '../api/client';

const RESULT_STYLE = {
  PASS:           { color: '#166534', bg: '#dcfce7', border: '#86efac', icon: '✓' },
  FAIL:           { color: '#991b1b', bg: '#fee2e2', border: '#fca5a5', icon: '✗' },
  REVIEW:         { color: '#92400e', bg: '#fef3c7', border: '#fcd34d', icon: '⚠' },
  PENDING:        { color: '#1e40af', bg: '#dbeafe', border: '#93c5fd', icon: '⏳' },
  MISSING:        { color: '#6b21a8', bg: '#f3e8ff', border: '#c4b5fd', icon: '?' },
  EXPIRED:        { color: '#7f1d1d', bg: '#fef2f2', border: '#fca5a5', icon: '⏰' },
  NOT_APPLICABLE: { color: '#374151', bg: '#f3f4f6', border: '#d1d5db', icon: '—' },
};

const CONNECTOR_STYLE = {
  VERIFIED:        { color: '#166534', bg: '#dcfce7', icon: '✓' },
  NOT_VERIFIED:    { color: '#991b1b', bg: '#fee2e2', icon: '✗' },
  UNAVAILABLE:     { color: '#1e40af', bg: '#dbeafe', icon: '⏳' },
  STALE:           { color: '#92400e', bg: '#fef3c7', icon: '⚠' },
  UNAUTHORIZED:    { color: '#7f1d1d', bg: '#fee2e2', icon: '🔒' },
  MANUAL_REQUIRED: { color: '#92400e', bg: '#fef3c7', icon: '👤' },
};

const RULE_TYPE_LABELS = {
  TURNOVER:     'Annual Turnover',
  GST_STATUS:   'GST Registration',
  UDYAM:        'Udyam / MSME',
  CERT_VALIDITY:'Certificate Validity',
  NAME_MATCH:   'Entity Name Consistency',
};

function NodeBadge({ status, type = 'result' }) {
  const cfg = type === 'connector'
    ? (CONNECTOR_STYLE[status] ?? { color: '#374151', bg: '#f3f4f6', icon: '?' })
    : (RESULT_STYLE[status] ?? RESULT_STYLE.REVIEW);
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 9px', borderRadius: 20, fontSize: 11, fontWeight: 700,
      color: cfg.color, background: cfg.bg,
    }}>
      {cfg.icon} {status}
    </span>
  );
}

function ChainConnector({ label }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '2px 0' }}>
      <div style={{ width: 1, height: 10, background: '#cbd5e1' }} />
      <div style={{
        fontSize: 9, color: '#94a3b8', fontWeight: 700, letterSpacing: '0.06em',
        textTransform: 'uppercase', padding: '1px 6px', background: '#f8fafc',
        border: '1px solid #e2e8f0', borderRadius: 4,
      }}>
        {label}
      </div>
      <div style={{ width: 1, height: 10, background: '#cbd5e1' }} />
    </div>
  );
}

function TraceNode({
  icon, title, subtitle, badge, children, highlight = false, onClick, expanded = false,
}) {
  return (
    <div
      onClick={onClick}
      style={{
        border: `1.5px solid ${highlight ? '#fca5a5' : '#e2e8f0'}`,
        borderRadius: 10,
        background: highlight ? '#fff5f5' : '#fff',
        overflow: 'hidden',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'box-shadow 0.15s',
        boxShadow: expanded ? '0 2px 8px rgba(0,0,0,0.08)' : 'none',
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'flex-start', gap: 10, padding: '10px 14px',
      }}>
        <span style={{ fontSize: 18, flexShrink: 0, marginTop: 1 }}>{icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 700, fontSize: 12, color: '#1e3a5f' }}>{title}</span>
            {badge}
          </div>
          {subtitle && (
            <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{subtitle}</div>
          )}
        </div>
        {onClick && (
          <span style={{ fontSize: 12, color: '#94a3b8', flexShrink: 0 }}>
            {expanded ? '▲' : '▼'}
          </span>
        )}
      </div>
      {expanded && children && (
        <div style={{ borderTop: '1px solid #f1f5f9', padding: '10px 14px', background: '#fafbfc' }}>
          {children}
        </div>
      )}
    </div>
  );
}

function TraceChain({ chain, defaultExpanded = false }) {
  const [expandedNodes, setExpandedNodes] = useState(
    defaultExpanded ? new Set(['clause', 'rule', 'evidence', 'verification', 'result']) : new Set()
  );

  const toggle = (node) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(node)) next.delete(node);
      else next.add(node);
      return next;
    });
  };

  const r = chain.result;
  const rs = RESULT_STYLE[r.result] ?? RESULT_STYLE.REVIEW;
  const isException = ['FAIL', 'MISSING', 'EXPIRED'].includes(r.result);

  return (
    <div style={{
      border: `2px solid ${isException ? '#fca5a5' : r.result === 'REVIEW' ? '#fcd34d' : r.result === 'PENDING' ? '#93c5fd' : '#e2e8f0'}`,
      borderRadius: 12,
      overflow: 'hidden',
      background: '#fff',
    }}>
      {/* Chain header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
        background: isException ? '#fff5f5' : r.result === 'REVIEW' ? '#fffbeb' : r.result === 'PENDING' ? '#f0f9ff' : '#f8fafc',
        borderBottom: '1px solid #f1f5f9',
      }}>
        <span style={{ fontSize: 20, fontWeight: 900, color: rs.color }}>{rs.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 800, fontSize: 13, color: '#1e3a5f' }}>
            {RULE_TYPE_LABELS[chain.rule.rule_type] ?? chain.rule.rule_type}
            {chain.rule.is_mandatory && (
              <span style={{ marginLeft: 6, fontSize: 10, color: '#dc2626', fontWeight: 700 }}>MANDATORY</span>
            )}
          </div>
          {chain.clause_number && (
            <div style={{ fontSize: 11, color: '#94a3b8' }}>
              Clause {chain.clause_number} — {chain.clause_title}
            </div>
          )}
        </div>
        <NodeBadge status={r.result} />
      </div>

      {/* Vertical chain */}
      <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 0 }}>

        {/* 1. Tender Clause */}
        {chain.clause_text && (
          <>
            <TraceNode
              icon="📜"
              title={`Clause ${chain.clause_number ?? ''}: ${chain.clause_title ?? 'Tender Clause'}`}
              subtitle={chain.clause_text.length > 100
                ? chain.clause_text.slice(0, 100) + '…'
                : chain.clause_text}
              onClick={() => toggle('clause')}
              expanded={expandedNodes.has('clause')}
            >
              <p style={{ margin: 0, fontSize: 12, color: '#374151', lineHeight: 1.6 }}>
                {chain.clause_text}
              </p>
            </TraceNode>
            <ChainConnector label="defines" />
          </>
        )}

        {/* 2. Requirement Rule */}
        <TraceNode
          icon="⚖️"
          title={`Rule: ${chain.rule.metric ?? chain.rule.rule_type}`}
          subtitle={chain.rule.description.length > 80
            ? chain.rule.description.slice(0, 80) + '…'
            : chain.rule.description}
          onClick={() => toggle('rule')}
          expanded={expandedNodes.has('rule')}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
            <div><span style={{ color: '#94a3b8' }}>Type:</span> {chain.rule.rule_type}</div>
            <div><span style={{ color: '#94a3b8' }}>Metric:</span> <code style={{ background: '#f1f5f9', padding: '1px 5px', borderRadius: 4 }}>{chain.rule.metric}</code></div>
            {chain.rule.operator && (
              <div><span style={{ color: '#94a3b8' }}>Condition:</span>{' '}
                <code style={{ background: '#f1f5f9', padding: '1px 5px', borderRadius: 4 }}>
                  {chain.rule.metric} {chain.rule.operator} {chain.rule.threshold_value}{chain.rule.threshold_unit ? ` ${chain.rule.threshold_unit}` : ''}
                </code>
              </div>
            )}
            <div><span style={{ color: '#94a3b8' }}>Mandatory:</span> {chain.rule.is_mandatory ? '✓ Yes' : 'No'}</div>
          </div>
        </TraceNode>

        <ChainConnector label="evaluated against" />

        {/* 3. Evidence */}
        <TraceNode
          icon="📄"
          title={`Evidence (${chain.evidence.length} item${chain.evidence.length !== 1 ? 's' : ''})`}
          subtitle={chain.evidence.length === 0
            ? 'No evidence found for this requirement'
            : chain.evidence.slice(0, 2).map(e => `${e.normalized_value ?? e.raw_value ?? '—'}`).join(' · ')}
          onClick={() => toggle('evidence')}
          expanded={expandedNodes.has('evidence')}
          highlight={chain.evidence.length === 0 && chain.rule.is_mandatory}
        >
          {chain.evidence.length === 0 ? (
            <div style={{ color: '#991b1b', fontSize: 12 }}>⚠ No evidence found for this mandatory requirement.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {chain.evidence.map((ev, i) => (
                <div key={i} style={{
                  background: '#f8fafc', borderRadius: 8, padding: '8px 10px',
                  border: '1px solid #e2e8f0', fontSize: 12,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                    <div>
                      <div style={{ fontWeight: 700, color: '#1e3a5f', marginBottom: 3 }}>{ev.field}</div>
                      <div><span style={{ color: '#94a3b8' }}>Raw:</span> {ev.raw_value ?? '—'}</div>
                      <div><span style={{ color: '#94a3b8' }}>Normalized:</span>{' '}
                        <strong style={{ color: '#1e3a5f' }}>{ev.normalized_value ?? '—'}</strong>
                      </div>
                      {ev.document_filename && (
                        <div style={{ color: '#64748b', marginTop: 3 }}>
                          📎 {ev.document_filename}
                          {ev.source_page && ` · Page ${ev.source_page}`}
                        </div>
                      )}
                    </div>
                    {ev.confidence !== null && (
                      <div style={{ textAlign: 'right', flexShrink: 0 }}>
                        <div style={{ fontSize: 10, color: '#94a3b8' }}>Confidence</div>
                        <div style={{ fontWeight: 700, color: '#1e3a5f' }}>
                          {Math.round((ev.confidence ?? 0) * 100)}%
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </TraceNode>

        <ChainConnector label="cross-checked via" />

        {/* 4. Verification Source */}
        <TraceNode
          icon="🔍"
          title="Verification Source"
          subtitle={chain.verifications.length === 0
            ? 'No verification performed'
            : chain.verifications.map(v => v.source_label).join(', ')}
          onClick={() => toggle('verification')}
          expanded={expandedNodes.has('verification')}
        >
          {chain.verifications.length === 0 ? (
            <div style={{ fontSize: 12, color: '#64748b' }}>No external verification was performed for this rule.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {chain.verifications.map((v, i) => (
                <div key={i} style={{ background: '#f8fafc', borderRadius: 8, padding: '8px 10px', border: '1px solid #e2e8f0', fontSize: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <div>
                      <div style={{ fontWeight: 700, color: '#1e3a5f', marginBottom: 2 }}>{v.source}</div>
                      <div style={{
                        fontSize: 10, color: '#64748b', background: '#e2e8f0',
                        display: 'inline-block', padding: '1px 6px', borderRadius: 3, marginBottom: 4,
                      }}>
                        {v.source_label}
                      </div>
                      {v.message && <div style={{ color: '#64748b' }}>{v.message}</div>}
                      {v.fields_verified && (
                        <div style={{ marginTop: 3 }}>
                          {Object.entries(v.fields_verified).map(([k, val]) => (
                            <span key={k} style={{ marginRight: 8 }}>
                              <span style={{ color: '#94a3b8' }}>{k}:</span>{' '}
                              <strong>{String(val)}</strong>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <NodeBadge status={v.connector_status} type="connector" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </TraceNode>

        <ChainConnector label="rule evaluates to" />

        {/* 5. Rule Result */}
        <TraceNode
          icon={rs.icon}
          title="Deterministic Rule Evaluation"
          subtitle={r.explanation ?? 'No explanation available'}
          highlight={isException}
          onClick={() => toggle('result')}
          expanded={expandedNodes.has('result')}
          badge={<NodeBadge status={r.result} />}
        >
          <div style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div><span style={{ color: '#94a3b8' }}>Result:</span> <NodeBadge status={r.result} /></div>
            <div><span style={{ color: '#94a3b8' }}>Explanation:</span> {r.explanation ?? '—'}</div>
            {r.confidence !== null && (
              <div><span style={{ color: '#94a3b8' }}>Evidence Confidence:</span> {Math.round((r.confidence ?? 0) * 100)}%</div>
            )}
            <div style={{ marginTop: 6, padding: '6px 10px', background: '#f1f5f9', borderRadius: 6, fontSize: 11, color: '#64748b' }}>
              ⚙ Generated by deterministic rule engine — not AI/LLM scoring
            </div>
          </div>
        </TraceNode>

        {/* 6. Officer Action (if any) */}
        {chain.officer_actions.length > 0 && (
          <>
            <ChainConnector label="officer reviewed" />
            <TraceNode
              icon="👤"
              title={`Officer: ${chain.officer_actions[0].action}`}
              subtitle={chain.officer_actions[0].comment ?? `By ${chain.officer_actions[0].officer_id}`}
            />
          </>
        )}
      </div>
    </div>
  );
}

export default function ComplianceTraceView({ bidId, bidderName }) {
  const [trace, setTrace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeChain, setActiveChain] = useState(null);
  const [filter, setFilter] = useState('ALL');

  useEffect(() => {
    setLoading(true);
    setError(null);
    getComplianceTrace(String(bidId))
      .then((data) => {
        setTrace(data);
        const firstException = data.chains?.find(c =>
          ['FAIL', 'MISSING', 'EXPIRED', 'REVIEW'].includes(c.result.result)
        );
        if (firstException) setActiveChain(firstException.chain_id);
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [bidId]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 120, color: '#94a3b8', fontSize: 13 }}>
        <span style={{ marginRight: 8 }}>⏳</span> Loading compliance trace…
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ background: '#fee2e2', borderRadius: 8, padding: '10px 14px', color: '#991b1b', fontSize: 13 }}>
        Failed to load trace: {error}
      </div>
    );
  }

  if (!trace) return null;

  const FILTERS = [
    { key: 'ALL', label: 'All' },
    { key: 'FAIL', label: '⛔ Fail' },
    { key: 'REVIEW', label: '⚠ Review' },
    { key: 'PENDING', label: '⏳ Pending' },
    { key: 'PASS', label: '✓ Pass' },
  ];

  const filtered = filter === 'ALL'
    ? trace.chains
    : trace.chains.filter(c => c.result.result === filter);

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 14 }}>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 800, color: '#1e3a5f' }}>
          📋 Compliance Trace — {bidderName}
        </h3>
        <p style={{ margin: '4px 0 0', fontSize: 11, color: '#64748b' }}>
          {trace.tender_reference} · Clause → Rule → Evidence → Verification → Result
        </p>
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
        {FILTERS.map(f => (
          <button
            key={f.key}
            id={`trace-filter-${f.key.toLowerCase()}`}
            onClick={() => setFilter(f.key)}
            style={{
              padding: '4px 12px', borderRadius: 20, fontSize: 11, fontWeight: 700,
              border: filter === f.key ? '1.5px solid #1e3a5f' : '1.5px solid #e2e8f0',
              background: filter === f.key ? '#1e3a5f' : '#fff',
              color: filter === f.key ? '#fff' : '#64748b',
              cursor: 'pointer',
            }}
          >
            {f.label}
          </button>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#94a3b8', alignSelf: 'center' }}>
          {filtered.length} chain{filtered.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Chains */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {filtered.map(chain => (
          <div
            key={chain.chain_id}
            id={`chain-${chain.chain_id}`}
            onClick={() => setActiveChain(activeChain === chain.chain_id ? null : chain.chain_id)}
            style={{ cursor: 'pointer' }}
          >
            <TraceChain
              chain={chain}
              defaultExpanded={activeChain === chain.chain_id}
            />
          </div>
        ))}
        {filtered.length === 0 && (
          <div style={{ textAlign: 'center', padding: 24, color: '#94a3b8', fontSize: 13 }}>
            No chains match this filter.
          </div>
        )}
      </div>

      {/* Footer note */}
      <div style={{
        marginTop: 14, padding: '8px 12px', background: '#f8fafc',
        borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 11, color: '#64748b',
      }}>
        🔒 All verification sources labelled "Simulation / Authorized Adapter" — not live government APIs.
        Results are generated by deterministic code. AI/LLM does not determine PASS or FAIL.
      </div>
    </div>
  );
}
