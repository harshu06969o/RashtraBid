/**
 * ClauseEvidenceGraph.jsx
 * Visual Node-Link Decision Flow Component (USP of GeM-Guard)
 * 
 * Strict Specification 2:
 * - Constructs a visual node-link component charting the exact decision flow:
 *   Tender Clause -> Requirement Rule -> Document Value -> Verification Source -> Result
 * - Highlights paths in green (pass), red (fail), or amber (review).
 */

import { useState, useRef, useEffect, useMemo } from 'react';
import { 
  FileCode2, Scale, FileText, Database, CheckCircle2, 
  AlertTriangle, XCircle, ArrowRight, Sparkles, Filter, 
  Info, RefreshCw, ZoomIn, ZoomOut, Check, ChevronRight
} from 'lucide-react';

// Benchmark Decision Flow Data representing standard GeM tender compliance checks
export const DEFAULT_FLOW_ITEMS = [
  {
    id: 'flow-turnover',
    status: 'PASS', // 'PASS' | 'FAIL' | 'REVIEW'
    confidence: 0.96,
    stage1_clause: {
      clause_id: '4.1.2',
      title: 'Clause 4.1.2',
      subtitle: 'Financial Capacity',
      description: 'Average annual financial turnover during last 3 years shall be at least ₹5.00 Cr.',
      mandatory: true,
    },
    stage2_rule: {
      rule_type: 'TURNOVER',
      rule_expr: 'turnover >= 5.0 Cr',
      description: 'Minimum 3-Year Audited Average Turnover threshold',
      threshold: '₹ 5.00 Cr',
      operator: '>=',
    },
    stage3_evidence: {
      field_name: 'annual_turnover_cr',
      label: 'Turnover (Avg 3FY)',
      extracted_value: '₹ 14.20 Cr',
      doc_name: 'CA Turnover Certificate',
      doc_type: 'CA_CERTIFICATE',
      raw_snippet: 'Average turnover of M/s TechCorp India Ltd for FY 2021-24 is INR 14.20 Crores',
      confidence: 0.96,
    },
    stage4_verification: {
      connector: 'ICAI UDIN Portal + Dual-OCR',
      source: 'ICAI UDIN Registry',
      auth_type: 'Live Cryptographic Check',
      timestamp: '2026-09-10T14:22:18Z',
      status: 'VERIFIED',
      details: 'UDIN 24058912AAAAAA9812 verified active on ICAI portal. CA membership valid.',
    },
    stage5_result: {
      outcome: 'PASS',
      code: 'COMPLIANT',
      summary: 'Turnover ₹14.20 Cr exceeds ₹5.00 Cr requirement by 184%. UDIN verified.',
      readiness_impact: '+25.0 Pts',
    },
  },
  {
    id: 'flow-gst',
    status: 'PASS',
    confidence: 0.99,
    stage1_clause: {
      clause_id: '3.2.1',
      title: 'Clause 3.2.1',
      subtitle: 'Tax Registration',
      description: 'Bidder must possess valid and active GSTIN registration in relevant State/UT.',
      mandatory: true,
    },
    stage2_rule: {
      rule_type: 'GST_STATUS',
      rule_expr: 'gstin.status == "ACTIVE"',
      description: 'Live GSTIN Active Taxpayer Status & Return Filing Verification',
      threshold: 'ACTIVE / REGULAR',
      operator: '==',
    },
    stage3_evidence: {
      field_name: 'gstin',
      label: 'GSTIN Registration',
      extracted_value: '07AACCI4520M1ZP',
      doc_name: 'GST REG-06 Certificate',
      doc_type: 'GST_CERTIFICATE',
      raw_snippet: 'Form GST REG-06 Registration Certificate | GSTIN: 07AACCI4520M1ZP',
      confidence: 0.99,
    },
    stage4_verification: {
      connector: 'GSTN Govt API (Live)',
      source: 'Govt GSTN System',
      auth_type: 'Statutory API Query',
      timestamp: '2026-09-10T14:22:19Z',
      status: 'VERIFIED',
      details: 'GSTIN 07AACCI4520M1ZP is ACTIVE. Taxpayer type: Regular. Last return: GSTR-3B filed on time.',
    },
    stage5_result: {
      outcome: 'PASS',
      code: 'ACTIVE',
      summary: 'Active GST taxpayer verified directly via Govt GSTN API. Zero tax defaults.',
      readiness_impact: '+20.0 Pts',
    },
  },
  {
    id: 'flow-pan-match',
    status: 'PASS',
    confidence: 0.97,
    stage1_clause: {
      clause_id: '2.1.0',
      title: 'Clause 2.1.0',
      subtitle: 'Legal Identity',
      description: 'Legal entity name must be strictly consistent across PAN, GST, and Bank records.',
      mandatory: true,
    },
    stage2_rule: {
      rule_type: 'NAME_MATCH',
      rule_expr: 'pan.legal_name == gst.legal_name',
      description: 'Cross-document Entity Identity & PAN validation',
      threshold: 'Levenshtein Match >= 90%',
      operator: '~=',
    },
    stage3_evidence: {
      field_name: 'pan',
      label: 'PAN & Entity Name',
      extracted_value: 'AACCI4520M · TECHCORP',
      doc_name: 'PAN Card & Form 26AS',
      doc_type: 'PAN_CARD',
      raw_snippet: 'Permanent Account Number: AACCI4520M | TECHCORP INFOTECH PRIVATE LIMITED',
      confidence: 0.98,
    },
    stage4_verification: {
      connector: 'ITD e-Filing API + Pandas Cross-Doc',
      source: 'Income Tax Dept Connector',
      auth_type: 'Cross-Document Integrity',
      timestamp: '2026-09-10T14:22:20Z',
      status: 'VERIFIED',
      details: 'PAN AACCI4520M active. Legal name matches GST Registration with 100% token similarity.',
    },
    stage5_result: {
      outcome: 'PASS',
      code: 'CONSISTENT',
      summary: 'Deterministic cross-check passed. Zero entity identity discrepancies.',
      readiness_impact: '+20.0 Pts',
    },
  },
  {
    id: 'flow-udyam',
    status: 'PASS',
    confidence: 0.95,
    stage1_clause: {
      clause_id: '7.4.0',
      title: 'Clause 7.4.0',
      subtitle: 'MSME Policy',
      description: 'Relaxation in prior turnover & experience for valid registered Micro & Small Enterprises.',
      mandatory: false,
    },
    stage2_rule: {
      rule_type: 'UDYAM',
      rule_expr: 'udyam.status == "VALID"',
      description: 'Valid Udyam Registration & Enterprise Category verification',
      threshold: 'MICRO / SMALL',
      operator: 'IN',
    },
    stage3_evidence: {
      field_name: 'udyam_number',
      label: 'Udyam Registration',
      extracted_value: 'UDYAM-DL-01-0012345',
      doc_name: 'Udyam Certificate',
      doc_type: 'UDYAM_CERTIFICATE',
      raw_snippet: 'UDYAM REGISTRATION CERTIFICATE | Number: UDYAM-DL-01-0012345 | SMALL',
      confidence: 0.97,
    },
    stage4_verification: {
      connector: 'Ministry of MSME Portal (NIC)',
      source: 'National MSME Database',
      auth_type: 'Govt Registry Query',
      timestamp: '2026-09-10T14:22:21Z',
      status: 'VERIFIED',
      details: 'Registered as SMALL enterprise. Entitled to EMD exemption and tender fee waiver under PPP Order.',
    },
    stage5_result: {
      outcome: 'PASS',
      code: 'MSME_EXEMPTION_APPLIED',
      summary: 'Valid MSME Small enterprise status. EMD fee waived under Govt procurement policy.',
      readiness_impact: '+15.0 Pts',
    },
  },
  {
    id: 'flow-local-content',
    status: 'PASS',
    confidence: 0.94,
    stage1_clause: {
      clause_id: '8.1.0',
      title: 'Clause 8.1.0',
      subtitle: 'Make In India (MII)',
      description: 'Preference to Class-I Local Suppliers having local value addition >= 50%.',
      mandatory: true,
    },
    stage2_rule: {
      rule_type: 'LOCAL_CONTENT',
      rule_expr: 'local_content_pct >= 50.0%',
      description: 'Domestic Local Value Addition Certification threshold',
      threshold: '>= 50.0%',
      operator: '>=',
    },
    stage3_evidence: {
      field_name: 'local_content_percentage',
      label: 'Domestic Content %',
      extracted_value: '62.5% (Class-I)',
      doc_name: 'MII Auditor Declaration',
      doc_type: 'MII_DECLARATION',
      raw_snippet: 'Domestic local value addition constitutes 62.5% of overall product bill of materials.',
      confidence: 0.94,
    },
    stage4_verification: {
      connector: 'Auditor Digital Signature (DSC)',
      source: 'Statutory DSC Attestation',
      auth_type: 'Cryptographic Signature',
      timestamp: '2026-09-10T14:22:22Z',
      status: 'VERIFIED',
      details: 'Affidavit verified signed with valid Class-3 DSC by Statutory Auditor.',
    },
    stage5_result: {
      outcome: 'PASS',
      code: 'CLASS_I_LOCAL',
      summary: 'Bidder qualifies as Class-I Local Supplier (62.5% >= 50%). Purchase preference granted.',
      readiness_impact: '+20.0 Pts',
    },
  },
];

const STATUS_THEMES = {
  PASS: {
    stroke: '#10b981',
    glow: 'rgba(16, 185, 129, 0.45)',
    bg: '#064e3b',
    border: '#059669',
    badgeBg: 'rgba(16, 185, 129, 0.15)',
    badgeText: '#6ee7b7',
    icon: CheckCircle2,
    label: 'PASS',
  },
  REVIEW: {
    stroke: '#f59e0b',
    glow: 'rgba(245, 158, 11, 0.45)',
    bg: '#78350f',
    border: '#d97706',
    badgeBg: 'rgba(245, 158, 11, 0.15)',
    badgeText: '#fcd34d',
    icon: AlertTriangle,
    label: 'REVIEW',
  },
  FAIL: {
    stroke: '#ef4444',
    glow: 'rgba(239, 68, 68, 0.45)',
    bg: '#7f1d1d',
    border: '#dc2626',
    badgeBg: 'rgba(239, 68, 68, 0.15)',
    badgeText: '#fca5a5',
    icon: XCircle,
    label: 'FAIL',
  },
};

export default function ClauseEvidenceGraph({
  flowData = null,
  tenderReference = 'GEM/2026/B/891245',
  bidderName = 'TechCorp Infotech Pvt Ltd',
}) {
  const flows = flowData && flowData.length > 0 ? flowData : DEFAULT_FLOW_ITEMS;

  const [activeFlowId, setActiveFlowId] = useState(flows[0]?.id || null);
  const [hoveredFlowId, setHoveredFlowId] = useState(null);
  const [filterStatus, setFilterStatus] = useState('ALL');
  const [nodePositions, setNodePositions] = useState({});

  const containerRef = useRef(null);
  const stageColRefs = useRef([null, null, null, null, null]);
  const nodeDomRefs = useRef({});

  // Compute filtered flows
  const displayedFlows = useMemo(() => {
    if (filterStatus === 'ALL') return flows;
    return flows.filter(f => f.status === filterStatus);
  }, [flows, filterStatus]);

  // Active flow item
  const selectedFlow = flows.find(f => f.id === (hoveredFlowId || activeFlowId)) || flows[0];

  // Measure DOM positions of nodes to draw exact SVG spline links
  const updatePositions = () => {
    if (!containerRef.current) return;
    const containerRect = containerRef.current.getBoundingClientRect();
    const posMap = {};

    displayedFlows.forEach((flow) => {
      ['stage1', 'stage2', 'stage3', 'stage4', 'stage5'].forEach((stg) => {
        const key = `${flow.id}-${stg}`;
        const el = nodeDomRefs.current[key];
        if (el) {
          const r = el.getBoundingClientRect();
          posMap[key] = {
            leftX: r.left - containerRect.left,
            rightX: r.right - containerRect.left,
            centerY: r.top + r.height / 2 - containerRect.top,
          };
        }
      });
    });

    setNodePositions(posMap);
  };

  useEffect(() => {
    updatePositions();
    window.addEventListener('resize', updatePositions);
    const timer = setTimeout(updatePositions, 100);
    return () => {
      window.removeEventListener('resize', updatePositions);
      clearTimeout(timer);
    };
  }, [displayedFlows, activeFlowId]);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      background: '#090d16',
      borderRadius: '16px',
      border: '1px solid rgba(255, 255, 255, 0.12)',
      boxShadow: '0 25px 60px rgba(0, 0, 0, 0.5)',
      overflow: 'hidden',
      color: '#f8fafc',
    }}>
      {/* ── TOP HEADER & FILTER BAR ── */}
      <div style={{
        padding: '16px 24px',
        background: '#131b2c',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 16,
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
              padding: '6px 10px',
              borderRadius: '8px',
              fontSize: '16px',
              boxShadow: '0 2px 8px rgba(59, 130, 246, 0.4)',
            }}>
              🕸️
            </span>
            <div>
              <h2 style={{ margin: 0, fontSize: '17px', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.02em' }}>
                Clause-to-Evidence Decision Graph
              </h2>
              <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: 2 }}>
                RashtraBid USP: <strong style={{ color: '#93c5fd' }}>AI reads. Rules verify. Evidence explains. Officers decide.</strong>
              </div>
            </div>
          </div>
        </div>

        {/* Filter Badges & Status summary */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>
            Filter Trajectories:
          </span>

          <div style={{
            display: 'flex',
            background: '#0f172a',
            border: '1px solid #334155',
            borderRadius: '8px',
            padding: '2px',
          }}>
            {[
              { id: 'ALL', label: `All (${flows.length})` },
              { id: 'PASS', label: `Passed (${flows.filter(f => f.status === 'PASS').length})`, color: '#10b981' },
              { id: 'REVIEW', label: `Review (${flows.filter(f => f.status === 'REVIEW').length})`, color: '#f59e0b' },
              { id: 'FAIL', label: `Failed (${flows.filter(f => f.status === 'FAIL').length})`, color: '#ef4444' },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setFilterStatus(tab.id)}
                style={{
                  background: filterStatus === tab.id ? '#1e293b' : 'transparent',
                  color: filterStatus === tab.id ? (tab.color || '#f8fafc') : '#94a3b8',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '5px 12px',
                  fontSize: '12px',
                  fontWeight: filterStatus === tab.id ? 700 : 500,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <button
            onClick={updatePositions}
            style={{
              background: '#1e293b',
              border: '1px solid #334155',
              color: '#cbd5e1',
              borderRadius: '8px',
              padding: '6px 10px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontSize: '12px',
            }}
            title="Recalculate Graph Links"
          >
            <RefreshCw size={13} />
            <span>Align</span>
          </button>
        </div>
      </div>

      {/* ── 5 STAGE GRAPH CONTAINER (Horizontally scrollable on mobile) ── */}
      <div className="responsive-table-wrapper" style={{ width: '100%', overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
        <div style={{ minWidth: '960px' }}>
          {/* ── 5 STAGE COLUMN TITLES ── */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(5, 1fr)',
            padding: '12px 20px',
            background: '#0d1524',
            borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
            gap: '16px',
          }}>
        {[
          { icon: FileCode2, label: '1. Tender Clause', color: '#60a5fa', sub: 'Procurement Specs' },
          { icon: Scale, label: '2. Requirement Rule', color: '#a78bfa', sub: 'Deterministic Logic' },
          { icon: FileText, label: '3. Document Value', color: '#38bdf8', sub: 'AI Extracted Figures' },
          { icon: Database, label: '4. Verification Source', color: '#f472b6', sub: 'Govt API & Registry' },
          { icon: CheckCircle2, label: '5. Rule Result', color: '#34d399', sub: 'Final Verdict' },
        ].map((col, idx) => (
          <div key={idx} style={{ textAlign: 'center' }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: col.color, fontSize: '13px', fontWeight: 800 }}>
              <col.icon size={15} />
              <span>{col.label}</span>
            </div>
            <div style={{ fontSize: '10px', color: '#64748b', marginTop: 1 }}>{col.sub}</div>
          </div>
        ))}
      </div>

      {/* ── MAIN INTERACTIVE GRAPH CANVAS ── */}
      <div
        ref={containerRef}
        style={{
          position: 'relative',
          padding: '24px 20px',
          minHeight: '420px',
          background: 'radial-gradient(ellipse at 50% 0%, #152238 0%, #090d16 80%)',
          overflow: 'hidden',
        }}
      >
        {/* SVG BEZIER SPLINES LAYER */}
        <svg
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            pointerEvents: 'none',
            zIndex: 1,
          }}
        >
          <defs>
            {/* SVG Glowing Filters for Green, Red, Amber Paths */}
            <filter id="glow-green" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#10b981" floodOpacity="0.8" />
            </filter>
            <filter id="glow-amber" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#f59e0b" floodOpacity="0.8" />
            </filter>
            <filter id="glow-red" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#ef4444" floodOpacity="0.8" />
            </filter>
          </defs>

          {displayedFlows.map((flow) => {
            const isSelected = (hoveredFlowId || activeFlowId) === flow.id;
            const isAnyHovered = hoveredFlowId !== null || activeFlowId !== null;
            const theme = STATUS_THEMES[flow.status] || STATUS_THEMES.REVIEW;

            // Opacity & Stroke Width
            const strokeOpacity = isSelected ? 1 : isAnyHovered ? 0.12 : 0.45;
            const strokeWidth = isSelected ? 3.5 : 1.8;
            const filterId = isSelected ? `url(#glow-${flow.status.toLowerCase()})` : undefined;

            // Generate 4 bezier spline segments connecting 5 stages
            const segments = ['stage1-stage2', 'stage2-stage3', 'stage3-stage4', 'stage4-stage5'];

            return segments.map((seg, sIdx) => {
              const [stA, stB] = seg.split('-');
              const posA = nodePositions[`${flow.id}-${stA}`];
              const posB = nodePositions[`${flow.id}-${stB}`];

              if (!posA || !posB) return null;

              const x1 = posA.rightX;
              const y1 = posA.centerY;
              const x2 = posB.leftX;
              const y2 = posB.centerY;
              const dx = Math.max(30, (x2 - x1) * 0.45);

              // Smooth Cubic Bezier
              const pathD = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

              return (
                <g key={`${flow.id}-${seg}`}>
                  {/* Subtle Background Track */}
                  <path
                    d={pathD}
                    fill="none"
                    stroke={isSelected ? theme.stroke : '#1e293b'}
                    strokeWidth={strokeWidth}
                    strokeOpacity={strokeOpacity}
                    filter={filterId}
                    style={{ transition: 'stroke-opacity 0.2s, stroke-width 0.2s' }}
                  />

                  {/* Pulsing Dot moving along active trajectory */}
                  {isSelected && (
                    <circle r={3.5} fill={theme.stroke} filter={filterId}>
                      <animateMotion
                        path={pathD}
                        dur="2.4s"
                        repeatCount="indefinite"
                        begin={`${sIdx * 0.55}s`}
                      />
                    </circle>
                  )}
                </g>
              );
            });
          })}
        </svg>

        {/* 5 HORIZONTAL COLUMNS OF CARDS */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(5, 1fr)',
          gap: '24px',
          position: 'relative',
          zIndex: 2,
        }}>
          {/* ══ COLUMN 1: TENDER CLAUSE ══ */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {displayedFlows.map((flow) => {
              const isSelected = (hoveredFlowId || activeFlowId) === flow.id;
              const theme = STATUS_THEMES[flow.status];

              return (
                <div
                  key={flow.id}
                  ref={el => nodeDomRefs.current[`${flow.id}-stage1`] = el}
                  onMouseEnter={() => setHoveredFlowId(flow.id)}
                  onMouseLeave={() => setHoveredFlowId(null)}
                  onClick={() => setActiveFlowId(flow.id)}
                  style={{
                    background: isSelected ? 'rgba(30, 58, 138, 0.45)' : '#111927',
                    border: `1.5px solid ${isSelected ? theme.stroke : 'rgba(255, 255, 255, 0.1)'}`,
                    borderRadius: '10px',
                    padding: '12px 14px',
                    cursor: 'pointer',
                    boxShadow: isSelected ? `0 4px 20px ${theme.glow}` : '0 2px 6px rgba(0,0,0,0.3)',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: '11px', fontWeight: 800, color: '#60a5fa' }}>
                      {flow.stage1_clause.title}
                    </span>
                    {flow.stage1_clause.mandatory && (
                      <span style={{ fontSize: '9px', background: '#3b82f6', color: '#fff', padding: '1px 5px', borderRadius: 3, fontWeight: 700 }}>
                        MANDATORY
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc', marginBottom: 4 }}>
                    {flow.stage1_clause.subtitle}
                  </div>
                  <div style={{ fontSize: '10px', color: '#94a3b8', lineHeight: 1.4, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {flow.stage1_clause.description}
                  </div>
                </div>
              );
            })}
          </div>

          {/* ══ COLUMN 2: REQUIREMENT RULE ══ */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {displayedFlows.map((flow) => {
              const isSelected = (hoveredFlowId || activeFlowId) === flow.id;
              const theme = STATUS_THEMES[flow.status];

              return (
                <div
                  key={flow.id}
                  ref={el => nodeDomRefs.current[`${flow.id}-stage2`] = el}
                  onMouseEnter={() => setHoveredFlowId(flow.id)}
                  onMouseLeave={() => setHoveredFlowId(null)}
                  onClick={() => setActiveFlowId(flow.id)}
                  style={{
                    background: isSelected ? 'rgba(88, 28, 135, 0.4)' : '#111927',
                    border: `1.5px solid ${isSelected ? theme.stroke : 'rgba(255, 255, 255, 0.1)'}`,
                    borderRadius: '10px',
                    padding: '12px 14px',
                    cursor: 'pointer',
                    boxShadow: isSelected ? `0 4px 20px ${theme.glow}` : '0 2px 6px rgba(0,0,0,0.3)',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div style={{ fontSize: '10px', color: '#c084fc', fontWeight: 800, textTransform: 'uppercase', marginBottom: 4 }}>
                    {flow.stage2_rule.rule_type}
                  </div>
                  <code style={{
                    display: 'block',
                    fontSize: '11px',
                    color: '#e2e8f0',
                    background: '#090d16',
                    padding: '4px 6px',
                    borderRadius: '4px',
                    marginBottom: 6,
                    fontWeight: 700,
                  }}>
                    {flow.stage2_rule.rule_expr}
                  </code>
                  <div style={{ fontSize: '10px', color: '#94a3b8' }}>
                    Threshold: <strong style={{ color: '#cbd5e1' }}>{flow.stage2_rule.threshold}</strong>
                  </div>
                </div>
              );
            })}
          </div>

          {/* ══ COLUMN 3: DOCUMENT VALUE ══ */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {displayedFlows.map((flow) => {
              const isSelected = (hoveredFlowId || activeFlowId) === flow.id;
              const theme = STATUS_THEMES[flow.status];

              return (
                <div
                  key={flow.id}
                  ref={el => nodeDomRefs.current[`${flow.id}-stage3`] = el}
                  onMouseEnter={() => setHoveredFlowId(flow.id)}
                  onMouseLeave={() => setHoveredFlowId(null)}
                  onClick={() => setActiveFlowId(flow.id)}
                  style={{
                    background: isSelected ? 'rgba(3, 105, 161, 0.35)' : '#111927',
                    border: `1.5px solid ${isSelected ? theme.stroke : 'rgba(255, 255, 255, 0.1)'}`,
                    borderRadius: '10px',
                    padding: '12px 14px',
                    cursor: 'pointer',
                    boxShadow: isSelected ? `0 4px 20px ${theme.glow}` : '0 2px 6px rgba(0,0,0,0.3)',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 700, marginBottom: 4 }}>
                    {flow.stage3_evidence.doc_name}
                  </div>
                  <div style={{ fontSize: '13px', fontWeight: 800, color: '#f8fafc', marginBottom: 4 }}>
                    {flow.stage3_evidence.extracted_value}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '10px', color: '#94a3b8' }}>
                    <span>Conf: <strong style={{ color: '#6ee7b7' }}>{Math.round(flow.stage3_evidence.confidence * 100)}%</strong></span>
                    <span style={{ background: '#1e293b', padding: '1px 5px', borderRadius: 3 }}>OCR Validated</span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* ══ COLUMN 4: VERIFICATION SOURCE ══ */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {displayedFlows.map((flow) => {
              const isSelected = (hoveredFlowId || activeFlowId) === flow.id;
              const theme = STATUS_THEMES[flow.status];

              return (
                <div
                  key={flow.id}
                  ref={el => nodeDomRefs.current[`${flow.id}-stage4`] = el}
                  onMouseEnter={() => setHoveredFlowId(flow.id)}
                  onMouseLeave={() => setHoveredFlowId(null)}
                  onClick={() => setActiveFlowId(flow.id)}
                  style={{
                    background: isSelected ? 'rgba(157, 23, 77, 0.35)' : '#111927',
                    border: `1.5px solid ${isSelected ? theme.stroke : 'rgba(255, 255, 255, 0.1)'}`,
                    borderRadius: '10px',
                    padding: '12px 14px',
                    cursor: 'pointer',
                    boxShadow: isSelected ? `0 4px 20px ${theme.glow}` : '0 2px 6px rgba(0,0,0,0.3)',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div style={{ fontSize: '11px', fontWeight: 800, color: '#f472b6', marginBottom: 4 }}>
                    {flow.stage4_verification.connector}
                  </div>
                  <div style={{ fontSize: '10px', color: '#e2e8f0', marginBottom: 6 }}>
                    {flow.stage4_verification.auth_type}
                  </div>
                  <div style={{
                    fontSize: '9px',
                    color: '#86efac',
                    background: 'rgba(16, 185, 129, 0.15)',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                  }}>
                    <span>✓</span> {flow.stage4_verification.status}
                  </div>
                </div>
              );
            })}
          </div>

          {/* ══ COLUMN 5: RESULT ══ */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {displayedFlows.map((flow) => {
              const isSelected = (hoveredFlowId || activeFlowId) === flow.id;
              const theme = STATUS_THEMES[flow.status];
              const IconComp = theme.icon;

              return (
                <div
                  key={flow.id}
                  ref={el => nodeDomRefs.current[`${flow.id}-stage5`] = el}
                  onMouseEnter={() => setHoveredFlowId(flow.id)}
                  onMouseLeave={() => setHoveredFlowId(null)}
                  onClick={() => setActiveFlowId(flow.id)}
                  style={{
                    background: isSelected ? theme.bg : '#111927',
                    border: `1.5px solid ${theme.border}`,
                    borderRadius: '10px',
                    padding: '12px 14px',
                    cursor: 'pointer',
                    boxShadow: isSelected ? `0 4px 25px ${theme.glow}` : '0 2px 6px rgba(0,0,0,0.3)',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <IconComp size={15} color={theme.stroke} />
                      <span style={{ fontSize: '12px', fontWeight: 800, color: theme.badgeText }}>
                        {flow.stage5_result.outcome}
                      </span>
                    </div>
                    <span style={{ fontSize: '10px', color: '#93c5fd', fontWeight: 700 }}>
                      {flow.stage5_result.readiness_impact}
                    </span>
                  </div>

                  <div style={{ fontSize: '10px', color: '#e2e8f0', lineHeight: 1.4 }}>
                    {flow.stage5_result.summary}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
        </div>
      </div>

      {/* ── BOTTOM DECISION TRACE AUDIT STRIP ── */}
      {selectedFlow && (
        <div style={{
          padding: '16px 24px',
          background: '#101827',
          borderTop: '1px solid rgba(255, 255, 255, 0.1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 16,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              background: STATUS_THEMES[selectedFlow.status].badgeBg,
              border: `1px solid ${STATUS_THEMES[selectedFlow.status].border}`,
              color: STATUS_THEMES[selectedFlow.status].badgeText,
              padding: '6px 14px',
              borderRadius: '8px',
              fontWeight: 800,
              fontSize: '13px',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}>
              <span>{selectedFlow.status === 'PASS' ? '✓' : '⚠'}</span>
              <span>{selectedFlow.stage1_clause.title} Verdict: {selectedFlow.status}</span>
            </div>

            <div style={{ fontSize: '12px', color: '#cbd5e1' }}>
              <strong>Deterministic Flow:</strong> {selectedFlow.stage1_clause.subtitle} ➜ {selectedFlow.stage2_rule.rule_expr} ➜ <span style={{ color: '#38bdf8' }}>{selectedFlow.stage3_evidence.extracted_value}</span> ➜ Verified by {selectedFlow.stage4_verification.source}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>
              Audit Trace Ready · Officer Override Allowed
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
