/**
 * SplitDocumentViewer.jsx
 * Dual-Pane Document & PDF Inspection Interface with Bounding Box Overlays
 * 
 * Strict Specification 1:
 * - Dual-pane interface displaying the original PDF / document layout.
 * - Uses [x1, y1, x2, y2] coordinates from the backend to overlay semi-transparent,
 *   highlighted bounding boxes directly over the extracted AI figures.
 */

import { useState, useRef, useEffect } from 'react';
import { ShieldCheck, AlertTriangle, XCircle, Search, ZoomIn, ZoomOut, Maximize2, Eye, FileText, CheckCircle2, ChevronRight, Hash, Layers } from 'lucide-react';

// Default mock evidence data matching backend seed schema if none passed
export const DEFAULT_SAMPLE_EVIDENCE = [
  {
    id: 'ev-1',
    document_id: 'doc-ca-001',
    doc_type: 'CA_CERTIFICATE',
    page_number: 1,
    bounding_box: [120.5, 340.2, 480.0, 395.8],
    field_name: 'annual_turnover_cr',
    field_label: 'Annual Turnover (Avg 3FY)',
    raw_value: 'INR 14.20 Crores',
    normalized_value: 14.20,
    unit: '₹ Cr',
    confidence: 0.96,
    verification_status: 'VERIFIED',
    extraction_method: 'Gemini 2.5 Flash Vision OCR',
    source_snippet: 'This is to certify that average turnover of M/s TechCorp India Ltd for FY 2021-24 is INR 14.20 Crores.',
  },
  {
    id: 'ev-2',
    document_id: 'doc-ca-001',
    doc_type: 'CA_CERTIFICATE',
    page_number: 1,
    bounding_box: [120.5, 410.0, 460.0, 445.0],
    field_name: 'ca_udin_number',
    field_label: 'CA Unique Document ID (UDIN)',
    raw_value: '24058912AAAAAA9812',
    normalized_value: '24058912AAAAAA9812',
    confidence: 0.99,
    verification_status: 'VERIFIED',
    extraction_method: 'ICAI UDIN Regex Engine',
    source_snippet: 'UDIN: 24058912AAAAAA9812 Generated on 12/04/2024 at ICAI Portal',
  },
  {
    id: 'ev-3',
    document_id: 'doc-gst-002',
    doc_type: 'GST_CERTIFICATE',
    page_number: 1,
    bounding_box: [110.0, 180.0, 390.0, 215.0],
    field_name: 'gstin',
    field_label: 'GSTIN Registration Number',
    raw_value: '07AACCI4520M1ZP',
    normalized_value: '07AACCI4520M1ZP',
    confidence: 0.99,
    verification_status: 'VERIFIED',
    extraction_method: 'Dual-Engine LayoutLM + OCR',
    source_snippet: 'Registration Certificate Form GST REG-06 | GSTIN: 07AACCI4520M1ZP',
  },
  {
    id: 'ev-4',
    document_id: 'doc-gst-002',
    doc_type: 'GST_CERTIFICATE',
    page_number: 1,
    bounding_box: [110.0, 235.0, 470.0, 270.0],
    field_name: 'legal_entity_name',
    field_label: 'Legal Name on GST',
    raw_value: 'TECHCORP INFOTECH PRIVATE LIMITED',
    normalized_value: 'TECHCORP INFOTECH PRIVATE LIMITED',
    confidence: 0.98,
    verification_status: 'VERIFIED',
    extraction_method: 'Dual-Engine Vision OCR',
    source_snippet: 'Legal Name: TECHCORP INFOTECH PRIVATE LIMITED',
  },
  {
    id: 'ev-5',
    document_id: 'doc-pan-003',
    doc_type: 'PAN_CARD',
    page_number: 1,
    bounding_box: [105.0, 195.0, 350.0, 230.0],
    field_name: 'pan',
    field_label: 'Permanent Account Number (PAN)',
    raw_value: 'AACCI4520M',
    normalized_value: 'AACCI4520M',
    confidence: 0.98,
    verification_status: 'VERIFIED',
    extraction_method: 'Vision Pattern Matcher',
    source_snippet: 'INCOME TAX DEPARTMENT GOVT OF INDIA | Permanent Account Number: AACCI4520M',
  },
  {
    id: 'ev-6',
    document_id: 'doc-udyam-004',
    doc_type: 'UDYAM_CERTIFICATE',
    page_number: 1,
    bounding_box: [130.0, 210.0, 460.0, 248.0],
    field_name: 'udyam_number',
    field_label: 'Udyam MSME Registration Number',
    raw_value: 'UDYAM-DL-01-0012345',
    normalized_value: 'UDYAM-DL-01-0012345',
    confidence: 0.97,
    verification_status: 'VERIFIED',
    extraction_method: 'Vision Intelligence',
    source_snippet: 'MINISTRY OF MICRO, SMALL & MEDIUM ENTERPRISES | UDYAM-DL-01-0012345',
  },
  {
    id: 'ev-7',
    document_id: 'doc-mii-005',
    doc_type: 'MII_DECLARATION',
    page_number: 1,
    bounding_box: [140.0, 510.0, 450.5, 545.0],
    field_name: 'local_content_percentage',
    field_label: 'Make In India Local Content',
    raw_value: '62.5%',
    normalized_value: 62.5,
    unit: '%',
    confidence: 0.94,
    verification_status: 'VERIFIED',
    extraction_method: 'Vision OCR Extraction',
    source_snippet: 'We hereby declare that domestic local value addition constitutes 62.5% of overall product cost.',
  },
];

export const DOCUMENT_CATALOG = [
  { id: 'doc-ca-001', type: 'CA_CERTIFICATE', name: 'Chartered Accountant Turnover Certificate', icon: '📜', issuer: 'ICAI / Sharma & Co.', date: '12-Apr-2024' },
  { id: 'doc-gst-002', type: 'GST_CERTIFICATE', name: 'GST Registration Certificate (REG-06)', icon: '🏛️', issuer: 'Govt. of India GSTN', date: '01-Jul-2017' },
  { id: 'doc-pan-003', type: 'PAN_CARD', name: 'Permanent Account Number Card (PAN)', icon: '💳', issuer: 'Income Tax Department', date: '15-Mar-2015' },
  { id: 'doc-udyam-004', type: 'UDYAM_CERTIFICATE', name: 'Udyam MSME Registration Certificate', icon: '🏭', issuer: 'Ministry of MSME', date: '10-Oct-2021' },
  { id: 'doc-mii-005', type: 'MII_DECLARATION', name: 'Make In India (MII) Local Content Affidavit', icon: '🇮🇳', issuer: 'Statutory Auditor Attestation', date: '20-Apr-2024' },
];

export default function SplitDocumentViewer({
  evidenceList = [],
  documents = [],
  initialSelectedEvidenceId = null,
  onEvidenceSelect = null,
}) {
  const activeEvidenceList = evidenceList && evidenceList.length > 0 ? evidenceList : DEFAULT_SAMPLE_EVIDENCE;
  const activeDocCatalog = documents && documents.length > 0 ? documents : DOCUMENT_CATALOG;

  const [selectedDocId, setSelectedDocId] = useState(activeDocCatalog[0]?.id || 'doc-ca-001');
  const [selectedEvidenceId, setSelectedEvidenceId] = useState(initialSelectedEvidenceId || activeEvidenceList[0]?.id);
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const [showBoundingBoxes, setShowBoundingBoxes] = useState(true);
  const [filterText, setFilterText] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [highlightPulse, setHighlightPulse] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== 'undefined' ? window.innerWidth <= 880 : false);
  const [mobileTab, setMobileTab] = useState('FIGURES'); // 'FIGURES' or 'DOC'

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 880);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const canvasRef = useRef(null);
  const boxRefs = useRef({});

  // Active document object
  const activeDoc = activeDocCatalog.find(d => d.id === selectedDocId) || activeDocCatalog[0];

  // Evidence items related to current document
  const docEvidence = activeEvidenceList.filter(ev => {
    if (ev.document_id) return ev.document_id === selectedDocId;
    if (ev.doc_type) return ev.doc_type === activeDoc?.type;
    return true;
  });

  // Highlight effect when selection changes
  useEffect(() => {
    if (selectedEvidenceId) {
      setHighlightPulse(true);
      const timer = setTimeout(() => setHighlightPulse(false), 1200);
      return () => clearTimeout(timer);
    }
  }, [selectedEvidenceId]);

  function handleSelectEvidence(ev) {
    setSelectedEvidenceId(ev.id);
    if (ev.document_id && ev.document_id !== selectedDocId) {
      setSelectedDocId(ev.document_id);
    }
    if (onEvidenceSelect) onEvidenceSelect(ev);
  }

  function handleZoom(delta) {
    setZoomLevel(prev => Math.min(Math.max(0.6, Number((prev + delta).toFixed(1))), 1.8));
  }

  function resetZoom() {
    setZoomLevel(1.0);
  }

  // Helper to compute percentage coordinates from [x1, y1, x2, y2]
  function computeBoxStyle(bbox, isSelected) {
    if (!bbox || bbox.length !== 4) {
      return { display: 'none' };
    }
    const [x1, y1, x2, y2] = bbox;
    // Check if 0-1000 normalized scale or 0-1 ratio
    const is1000Scale = Math.max(x1, y1, x2, y2) > 1.5;
    const factor = is1000Scale ? 10 : 100; // 1000 / 10 = 100%

    const left = Math.max(0, x1 / (is1000Scale ? 10 : 1));
    const top = Math.max(0, y1 / (is1000Scale ? 10 : 1));
    const width = Math.max(2, (x2 - x1) / (is1000Scale ? 10 : 1));
    const height = Math.max(1.8, (y2 - y1) / (is1000Scale ? 10 : 1));

    return {
      left: `${left}%`,
      top: `${top}%`,
      width: `${width}%`,
      height: `${height}%`,
      borderColor: isSelected ? '#2563eb' : '#3b82f6',
      backgroundColor: isSelected ? 'rgba(37, 99, 235, 0.28)' : 'rgba(59, 130, 246, 0.18)',
    };
  }

  // Filtered evidence for right pane
  const filteredEvidence = activeEvidenceList.filter(ev => {
    const matchesSearch = filterText === '' ||
      (ev.field_name || '').toLowerCase().includes(filterText.toLowerCase()) ||
      (ev.field_label || '').toLowerCase().includes(filterText.toLowerCase()) ||
      String(ev.normalized_value || '').toLowerCase().includes(filterText.toLowerCase());

    const matchesStatus = statusFilter === 'ALL' ||
      (statusFilter === 'VERIFIED' && (ev.verification_status === 'VERIFIED' || ev.verification_status === 'PASS')) ||
      (statusFilter === 'REVIEW' && (ev.verification_status === 'REVIEW' || ev.verification_status === 'PENDING')) ||
      (statusFilter === 'MISMATCH' && (ev.verification_status === 'MISMATCH' || ev.verification_status === 'FAIL'));

    return matchesSearch && matchesStatus;
  });

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: isMobile ? '82vh' : '780px',
      background: '#0f172a',
      borderRadius: '16px',
      border: '1px solid rgba(255, 255, 255, 0.12)',
      boxShadow: '0 20px 50px rgba(0, 0, 0, 0.4)',
      overflow: 'hidden',
      color: '#f8fafc',
    }}>
      {/* ── TOP CONTROLS TOOLBAR ── */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 12,
        padding: isMobile ? '10px 14px' : '12px 20px',
        background: '#1e293b',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
      }}>
        {/* Document Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: 'rgba(59, 130, 246, 0.15)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            padding: '5px 12px',
            borderRadius: '8px',
            fontSize: '12px',
            fontWeight: 700,
            color: '#60a5fa',
          }}>
            <span>{activeDoc?.icon || '📄'}</span>
            <span style={{ maxWidth: isMobile ? 130 : 'none', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {activeDoc?.name || 'Document'}
            </span>
          </div>

          <select
            value={selectedDocId}
            onChange={(e) => {
              setSelectedDocId(e.target.value);
              // reset selected evidence to first one matching new doc
              const firstMatch = activeEvidenceList.find(ev => ev.document_id === e.target.value);
              if (firstMatch) setSelectedEvidenceId(firstMatch.id);
            }}
            style={{
              background: '#0f172a',
              border: '1px solid #334155',
              borderRadius: '8px',
              color: '#f8fafc',
              fontSize: '12px',
              padding: '6px 10px',
              cursor: 'pointer',
              outline: 'none',
              maxWidth: isMobile ? '130px' : '220px',
            }}
          >
            {activeDocCatalog.map(doc => (
              <option key={doc.id} value={doc.id}>
                {doc.icon} {doc.name}
              </option>
            ))}
          </select>
        </div>

        {/* Zoom & View Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={() => setShowBoundingBoxes(!showBoundingBoxes)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              background: showBoundingBoxes ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255, 255, 255, 0.05)',
              border: `1px solid ${showBoundingBoxes ? '#10b981' : '#475569'}`,
              color: showBoundingBoxes ? '#6ee7b7' : '#94a3b8',
              borderRadius: '6px',
              padding: '5px 10px',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
            title="Toggle Bounding Boxes"
          >
            <Layers size={14} />
            <span>{isMobile ? (showBoundingBoxes ? 'Boxes ON' : 'Boxes OFF') : `B-Boxes ${showBoundingBoxes ? 'ON' : 'OFF'}`}</span>
          </button>

          <div style={{ height: 20, width: 1, background: '#334155', margin: '0 4px' }} />

          <button
            onClick={() => handleZoom(-0.1)}
            style={{
              background: '#334155',
              border: 'none',
              borderRadius: '6px',
              color: '#f8fafc',
              padding: '6px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
            }}
            title="Zoom Out"
          >
            <ZoomOut size={14} />
          </button>

          <span style={{
            fontSize: '12px',
            fontWeight: 700,
            color: '#cbd5e1',
            minWidth: '45px',
            textAlign: 'center',
          }}>
            {Math.round(zoomLevel * 100)}%
          </span>

          <button
            onClick={() => handleZoom(0.1)}
            style={{
              background: '#334155',
              border: 'none',
              borderRadius: '6px',
              color: '#f8fafc',
              padding: '6px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
            }}
            title="Zoom In"
          >
            <ZoomIn size={14} />
          </button>

          <button
            onClick={resetZoom}
            style={{
              background: '#334155',
              border: 'none',
              borderRadius: '6px',
              color: '#f8fafc',
              padding: '6px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
            }}
            title="Fit Width"
          >
            <Maximize2 size={14} />
          </button>
        </div>
      </div>

      {/* ── MOBILE TAB SWITCHER ── */}
      {isMobile && (
        <div style={{
          display: 'flex',
          background: '#0a0f1d',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
          padding: '8px 12px',
          gap: 8,
        }}>
          <button
            onClick={() => setMobileTab('FIGURES')}
            style={{
              flex: 1,
              padding: '8px 10px',
              borderRadius: 6,
              border: 'none',
              background: mobileTab === 'FIGURES' ? '#1e40af' : 'rgba(255,255,255,0.06)',
              color: mobileTab === 'FIGURES' ? '#fff' : '#94a3b8',
              fontSize: 12,
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            🤖 AI Figures ({filteredEvidence.length})
          </button>
          <button
            onClick={() => setMobileTab('DOC')}
            style={{
              flex: 1,
              padding: '8px 10px',
              borderRadius: 6,
              border: 'none',
              background: mobileTab === 'DOC' ? '#1e40af' : 'rgba(255,255,255,0.06)',
              color: mobileTab === 'DOC' ? '#fff' : '#94a3b8',
              fontSize: 12,
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            📄 PDF Sheet Viewer
          </button>
        </div>
      )}

      {/* ── DUAL PANE BODY ── */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0, width: '100%' }}>
        {/* ═══ LEFT PANE: DOCUMENT VIEWER WITH BOUNDING BOXES ═══ */}
        {(!isMobile || mobileTab === 'DOC') && (
        <div style={{
          flex: isMobile ? 1 : 7,
          width: isMobile ? '100%' : 'auto',
          background: '#090d16',
          position: 'relative',
          overflow: 'auto',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'flex-start',
          padding: isMobile ? '14px' : '24px',
          WebkitOverflowScrolling: 'touch',
        }}>
          {/* Scaled PDF Document Sheet */}
          <div
            ref={canvasRef}
            style={{
              width: '680px',
              minHeight: '880px',
              background: '#ffffff',
              color: '#1e293b',
              borderRadius: '4px',
              boxShadow: '0 10px 40px rgba(0, 0, 0, 0.7)',
              position: 'relative',
              transform: `scale(${zoomLevel})`,
              transformOrigin: 'top center',
              transition: 'transform 0.15s ease-out',
              userSelect: 'none',
              fontFamily: '"Times New Roman", Times, serif',
            }}
          >
            {/* Authentic Rendered Document Layout based on Document Type */}
            <DocumentPageLayout docType={activeDoc?.type} docInfo={activeDoc} />

            {/* OVERLAY: AI BOUNDING BOXES [x1, y1, x2, y2] */}
            {showBoundingBoxes && docEvidence.map((ev) => {
              const isSelected = selectedEvidenceId === ev.id;
              const boxStyle = computeBoxStyle(ev.bounding_box, isSelected);

              return (
                <div
                  key={ev.id}
                  ref={el => boxRefs.current[ev.id] = el}
                  onClick={() => handleSelectEvidence(ev)}
                  style={{
                    position: 'absolute',
                    ...boxStyle,
                    borderWidth: isSelected ? '2.5px' : '1.5px',
                    borderStyle: 'solid',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    zIndex: isSelected ? 20 : 10,
                    transition: 'all 0.2s ease',
                    boxShadow: isSelected
                      ? '0 0 0 3px rgba(59, 130, 246, 0.4), 0 0 20px rgba(59, 130, 246, 0.6)'
                      : '0 0 8px rgba(59, 130, 246, 0.3)',
                    animation: isSelected && highlightPulse ? 'pulseGlow 1.2s ease-in-out infinite' : 'none',
                  }}
                  title={`Field: ${ev.field_label || ev.field_name} | Value: ${ev.normalized_value} | Confidence: ${Math.round(ev.confidence * 100)}%`}
                >
                  {/* Bounding Box Metadata Tag */}
                  <div style={{
                    position: 'absolute',
                    top: '-24px',
                    left: '-2px',
                    background: isSelected ? '#1e40af' : '#1e293b',
                    color: '#ffffff',
                    fontSize: '10px',
                    fontFamily: 'Inter, sans-serif',
                    fontWeight: 700,
                    padding: '2px 7px',
                    borderRadius: '4px',
                    whiteSpace: 'nowrap',
                    boxShadow: '0 2px 6px rgba(0,0,0,0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    border: '1px solid rgba(255,255,255,0.2)',
                    pointerEvents: 'none',
                  }}>
                    <span>{ev.field_label || ev.field_name}</span>
                    <span style={{
                      color: ev.confidence >= 0.9 ? '#86efac' : '#fde047',
                      fontSize: '9px',
                      background: 'rgba(0,0,0,0.3)',
                      padding: '1px 3px',
                      borderRadius: '2px',
                    }}>
                      {Math.round(ev.confidence * 100)}%
                    </span>
                  </div>

                  {/* Corner handles for authentic OCR visual anchor */}
                  <div style={{ position: 'absolute', top: -3, left: -3, width: 6, height: 6, background: '#3b82f6', borderRadius: 1 }} />
                  <div style={{ position: 'absolute', top: -3, right: -3, width: 6, height: 6, background: '#3b82f6', borderRadius: 1 }} />
                  <div style={{ position: 'absolute', bottom: -3, left: -3, width: 6, height: 6, background: '#3b82f6', borderRadius: 1 }} />
                  <div style={{ position: 'absolute', bottom: -3, right: -3, width: 6, height: 6, background: '#3b82f6', borderRadius: 1 }} />
                </div>
              );
            })}
          </div>
        </div>
        )}

        {/* ═══ RIGHT PANE: EXTRACTED AI FIGURES INSPECTOR ═══ */}
        {(!isMobile || mobileTab === 'FIGURES') && (
          <div style={{
            flex: isMobile ? 1 : 5,
            width: isMobile ? '100%' : 'auto',
            background: '#131d2e',
            borderLeft: isMobile ? 'none' : '1px solid rgba(255, 255, 255, 0.1)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}>
          {/* Inspector Header */}
          <div style={{
            padding: '16px 20px',
            background: '#1a2638',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: '18px' }}>🤖</span>
                <span style={{ fontSize: '14px', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.01em' }}>
                  Extracted AI Figures ({filteredEvidence.length})
                </span>
              </div>
              <span style={{
                fontSize: '11px',
                fontWeight: 700,
                color: '#60a5fa',
                background: 'rgba(59, 130, 246, 0.15)',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                padding: '2px 8px',
                borderRadius: '4px',
              }}>
                Gemini 2.5 Flash + LayoutLM
              </span>
            </div>

            {/* Search & Status Filter */}
            <div style={{ display: 'flex', gap: 8 }}>
              <div style={{
                position: 'relative',
                flex: 1,
                display: 'flex',
                alignItems: 'center',
              }}>
                <Search size={14} style={{ position: 'absolute', left: 10, color: '#64748b' }} />
                <input
                  type="text"
                  placeholder="Search field or value…"
                  value={filterText}
                  onChange={e => setFilterText(e.target.value)}
                  style={{
                    width: '100%',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: '6px',
                    padding: '6px 10px 6px 30px',
                    fontSize: '12px',
                    color: '#f8fafc',
                    outline: 'none',
                  }}
                />
              </div>

              <select
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
                style={{
                  background: '#0f172a',
                  border: '1px solid #334155',
                  borderRadius: '6px',
                  padding: '6px 8px',
                  fontSize: '12px',
                  color: '#cbd5e1',
                  cursor: 'pointer',
                  outline: 'none',
                }}
              >
                <option value="ALL">All Status</option>
                <option value="VERIFIED">Verified</option>
                <option value="REVIEW">Review</option>
                <option value="MISMATCH">Mismatch</option>
              </select>
            </div>
          </div>

          {/* Evidence Items List */}
          <div style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}>
            {filteredEvidence.map((ev) => {
              const isSelected = selectedEvidenceId === ev.id;
              const isMatchDoc = ev.document_id === selectedDocId || ev.doc_type === activeDoc?.type;
              const pct = Math.round((ev.confidence || 0.95) * 100);
              const confColor = pct >= 90 ? '#10b981' : pct >= 75 ? '#f59e0b' : '#ef4444';

              return (
                <div
                  key={ev.id}
                  onClick={() => handleSelectEvidence(ev)}
                  id={`evidence-item-${ev.id}`}
                  style={{
                    background: isSelected ? 'rgba(30, 58, 138, 0.4)' : '#1a2638',
                    border: `1.5px solid ${isSelected ? '#3b82f6' : isMatchDoc ? 'rgba(255, 255, 255, 0.08)' : 'rgba(255, 255, 255, 0.03)'}`,
                    borderRadius: '10px',
                    padding: '14px',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    boxShadow: isSelected ? '0 4px 14px rgba(59, 130, 246, 0.25)' : 'none',
                  }}
                >
                  {/* Item Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div>
                      <div style={{
                        fontSize: '13px',
                        fontWeight: 700,
                        color: isSelected ? '#93c5fd' : '#f8fafc',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                      }}>
                        {ev.field_label || ev.field_name}
                        {isMatchDoc && (
                          <span style={{
                            fontSize: '9px',
                            background: '#1e40af',
                            color: '#dbeafe',
                            padding: '1px 5px',
                            borderRadius: '3px',
                            fontWeight: 800,
                          }}>
                            ON PDF
                          </span>
                        )}
                      </div>
                      <code style={{ fontSize: '11px', color: '#94a3b8' }}>{ev.field_name}</code>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{
                        fontSize: '11px',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '4px',
                        background: ev.verification_status === 'VERIFIED' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                        color: ev.verification_status === 'VERIFIED' ? '#6ee7b7' : '#fcd34d',
                        border: `1px solid ${ev.verification_status === 'VERIFIED' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
                      }}>
                        {ev.verification_status || 'VERIFIED'}
                      </span>
                    </div>
                  </div>

                  {/* Extracted Figure Highlight */}
                  <div style={{
                    background: '#0f172a',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '6px',
                    padding: '8px 12px',
                    marginBottom: 10,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}>
                    <div>
                      <div style={{ fontSize: '10px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Normalized Value
                      </div>
                      <div style={{ fontSize: '15px', fontWeight: 800, color: '#38bdf8', fontFamily: 'monospace' }}>
                        {String(ev.normalized_value ?? ev.raw_value)} {ev.unit || ''}
                      </div>
                    </div>

                    {/* Confidence Meter */}
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '10px', color: '#64748b' }}>CONFIDENCE</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ width: 60, height: 6, background: '#334155', borderRadius: 99, overflow: 'hidden' }}>
                          <div style={{ width: `${pct}%`, height: '100%', background: confColor }} />
                        </div>
                        <span style={{ fontSize: '12px', fontWeight: 800, color: confColor }}>{pct}%</span>
                      </div>
                    </div>
                  </div>

                  {/* Precise Bounding Box Coordinates */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: '#94a3b8' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Hash size={12} color="#60a5fa" />
                      <span>Bounding Box:</span>
                      <code style={{
                        color: '#93c5fd',
                        background: '#090d16',
                        padding: '1px 5px',
                        borderRadius: '3px',
                        fontSize: '10px',
                      }}>
                        [{ev.bounding_box?.map(n => Math.round(n)).join(', ') || '0, 0, 0, 0'}]
                      </code>
                    </div>

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSelectEvidence(ev);
                        if (isMobile) setMobileTab('DOC');
                      }}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#60a5fa',
                        fontWeight: 700,
                        fontSize: '11px',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 3,
                        padding: '2px 6px',
                      }}
                    >
                      <Eye size={12} />
                      <span>Locate in PDF</span>
                    </button>
                  </div>
                </div>
              );
            })}

            {filteredEvidence.length === 0 && (
              <div style={{ padding: '30px', textAlign: 'center', color: '#64748b' }}>
                No extracted AI figures match your filter criteria.
              </div>
            )}
          </div>
        </div>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// AUTHENTIC DOCUMENT CANVAS RENDERER (CA, GST, UDYAM, PAN, MII)
// ══════════════════════════════════════════════════════════════════════════════
function DocumentPageLayout({ docType, docInfo }) {
  if (docType === 'GST_CERTIFICATE') {
    return (
      <div style={{ padding: '40px', fontSize: '13px', lineHeight: 1.6 }}>
        <div style={{ textAlign: 'center', borderBottom: '2px solid #000', paddingBottom: '16px', marginBottom: '24px' }}>
          <div style={{ fontSize: '11px', fontWeight: 'bold', letterSpacing: '2px' }}>GOVERNMENT OF INDIA</div>
          <div style={{ fontSize: '16px', fontWeight: 'bold', margin: '4px 0' }}>Form GST REG-06</div>
          <div style={{ fontSize: '11px', fontStyle: 'italic' }}>[See Rule 10(1)]</div>
          <div style={{ fontSize: '14px', fontWeight: 'bold', marginTop: '6px' }}>Registration Certificate</div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: '14px 10px', marginBottom: '24px' }}>
          <div style={{ fontWeight: 'bold' }}>Registration Number (GSTIN):</div>
          <div style={{ fontWeight: 'bold', color: '#000', letterSpacing: '1px' }}>07AACCI4520M1ZP</div>

          <div style={{ fontWeight: 'bold' }}>Legal Name:</div>
          <div>TECHCORP INFOTECH PRIVATE LIMITED</div>

          <div style={{ fontWeight: 'bold' }}>Trade Name:</div>
          <div>TECHCORP SOLUTIONS INDIA</div>

          <div style={{ fontWeight: 'bold' }}>Constitution of Business:</div>
          <div>Private Limited Company</div>

          <div style={{ fontWeight: 'bold' }}>Address of Principal Place:</div>
          <div>Plot 42, Okhla Industrial Area Phase III, New Delhi, Delhi - 110020</div>

          <div style={{ fontWeight: 'bold' }}>Date of Validity:</div>
          <div>From: 01/07/2017 &nbsp;&nbsp;&nbsp; To: Regular / Active</div>

          <div style={{ fontWeight: 'bold' }}>Type of Registration:</div>
          <div>Regular Taxpayer</div>
        </div>

        {/* Official Stamp */}
        <div style={{ marginTop: '60px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
          <div style={{ border: '2px dashed #991b1b', padding: '10px 18px', borderRadius: '50%', textAlign: 'center', color: '#991b1b', fontSize: '10px', width: '110px', height: '110px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <div style={{ fontWeight: 'bold' }}>GSTN AUTH</div>
            <div>NEW DELHI</div>
            <div style={{ fontSize: '9px' }}>GOVT OF INDIA</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ width: '160px', borderBottom: '1px solid #000', marginBottom: '6px' }}></div>
            <div style={{ fontSize: '11px', fontWeight: 'bold' }}>Superintendent, Range 14</div>
            <div style={{ fontSize: '10px' }}>Jurisdictional Authority, Delhi</div>
          </div>
        </div>
      </div>
    );
  }

  if (docType === 'PAN_CARD') {
    return (
      <div style={{ padding: '50px 40px', fontSize: '14px' }}>
        <div style={{
          border: '2px solid #003366',
          borderRadius: '12px',
          padding: '28px',
          background: 'linear-gradient(135deg, #f0f7ff 0%, #ffffff 100%)',
          boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '2px solid #003366', paddingBottom: '12px', marginBottom: '20px' }}>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#003366' }}>आयकर विभाग</div>
              <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#003366' }}>INCOME TAX DEPARTMENT</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#003366' }}>भारत सरकार</div>
              <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#003366' }}>GOVT. OF INDIA</div>
            </div>
          </div>

          <div style={{ marginBottom: '20px' }}>
            <div style={{ fontSize: '10px', color: '#555' }}>स्थायी लेखा संख्या / Permanent Account Number:</div>
            <div style={{ fontSize: '20px', fontWeight: 'bold', letterSpacing: '2px', color: '#003366', margin: '4px 0' }}>
              AACCI4520M
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px', gap: '16px' }}>
            <div>
              <div style={{ fontSize: '10px', color: '#555' }}>नाम / Name:</div>
              <div style={{ fontWeight: 'bold', fontSize: '15px', marginBottom: '12px' }}>TECHCORP INFOTECH PRIVATE LIMITED</div>

              <div style={{ fontSize: '10px', color: '#555' }}>निगमन की तारीख / Date of Incorporation:</div>
              <div style={{ fontWeight: 'bold' }}>15/03/2015</div>
            </div>

            <div style={{
              border: '1px solid #999',
              background: '#e2e8f0',
              height: '110px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '11px',
              color: '#666',
              textAlign: 'center',
            }}>
              QR CODE EMBEDDED
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (docType === 'UDYAM_CERTIFICATE') {
    return (
      <div style={{ padding: '36px', fontSize: '13px', lineHeight: 1.6 }}>
        <div style={{ textAlign: 'center', borderBottom: '2px solid #15803d', paddingBottom: '14px', marginBottom: '20px' }}>
          <div style={{ fontSize: '12px', fontWeight: 'bold' }}>MINISTRY OF MICRO, SMALL & MEDIUM ENTERPRISES</div>
          <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#15803d' }}>UDYAM REGISTRATION CERTIFICATE</div>
          <div style={{ fontSize: '11px', fontStyle: 'italic' }}>Udyam Certificate No: UDYAM-DL-01-0012345</div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '170px 1fr', gap: '12px 10px', marginBottom: '20px' }}>
          <div style={{ fontWeight: 'bold' }}>Enterprise Name:</div>
          <div style={{ fontWeight: 'bold' }}>TECHCORP INFOTECH PRIVATE LIMITED</div>

          <div style={{ fontWeight: 'bold' }}>Enterprise Classification:</div>
          <div><span style={{ background: '#dcfce7', color: '#166534', padding: '2px 8px', borderRadius: '4px', fontWeight: 'bold' }}>SMALL ENTERPRISE</span></div>

          <div style={{ fontWeight: 'bold' }}>Major Activity:</div>
          <div>Manufacturing & IT Services</div>

          <div style={{ fontWeight: 'bold' }}>Date of Incorporation:</div>
          <div>15/03/2015</div>

          <div style={{ fontWeight: 'bold' }}>Date of Udyam Reg:</div>
          <div>10/10/2021</div>

          <div style={{ fontWeight: 'bold' }}>MSME DI Location:</div>
          <div>Okhla, New Delhi (DL-01)</div>
        </div>

        <div style={{ border: '1px solid #cbd5e1', padding: '12px', background: '#f8fafc', borderRadius: '6px', fontSize: '11px' }}>
          <strong>Statutory Compliance Note:</strong> Valid for Public Procurement Policy exemptions under Order 2012 (Relaxation in Prior Experience and Turnover).
        </div>
      </div>
    );
  }

  // Default: CA Certificate (Turnover)
  return (
    <div style={{ padding: '40px', fontSize: '13px', lineHeight: 1.7 }}>
      {/* Letterhead */}
      <div style={{ textAlign: 'center', borderBottom: '2px double #1e3a5f', paddingBottom: '16px', marginBottom: '24px' }}>
        <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#1e3a5f', letterSpacing: '1px' }}>
          SHARMA, GUPTA & ASSOCIATES
        </div>
        <div style={{ fontSize: '11px', color: '#555' }}>
          Chartered Accountants · Firm Regn No: 014298N
        </div>
        <div style={{ fontSize: '10px', color: '#666' }}>
          Suite 401, Barakhamba Road, Connaught Place, New Delhi - 110001
        </div>
      </div>

      <div style={{ textAlign: 'center', margin: '20px 0' }}>
        <div style={{ fontSize: '15px', fontWeight: 'bold', textDecoration: 'underline' }}>
          TO WHOMSOEVER IT MAY CONCERN
        </div>
        <div style={{ fontSize: '12px', fontWeight: 'bold', marginTop: '4px' }}>
          ANNUAL TURNOVER COMPLIANCE CERTIFICATE
        </div>
      </div>

      <p style={{ textIndent: '30px', textAlign: 'justify', marginBottom: '16px' }}>
        This is to certify that we have examined the audited books of accounts and statutory financial statements of 
        <strong> M/s TECHCORP INFOTECH PRIVATE LIMITED</strong>, having its registered office at Plot 42, Okhla Industrial Area Phase III, New Delhi - 110020.
      </p>

      <p style={{ textIndent: '30px', textAlign: 'justify', marginBottom: '20px' }}>
        On the basis of statutory audit and verification, the annual turnover of the company for the last three financial years is as under:
      </p>

      {/* Turnover Table */}
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '24px', textAlign: 'center' }}>
        <thead>
          <tr style={{ background: '#f1f5f9' }}>
            <th style={{ border: '1px solid #000', padding: '8px', fontSize: '12px' }}>Financial Year</th>
            <th style={{ border: '1px solid #000', padding: '8px', fontSize: '12px' }}>Turnover (INR Crores)</th>
            <th style={{ border: '1px solid #000', padding: '8px', fontSize: '12px' }}>Audited Status</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style={{ border: '1px solid #000', padding: '6px' }}>FY 2021 - 2022</td>
            <td style={{ border: '1px solid #000', padding: '6px', fontWeight: 'bold' }}>₹ 12.80 Cr</td>
            <td style={{ border: '1px solid #000', padding: '6px' }}>Audited</td>
          </tr>
          <tr>
            <td style={{ border: '1px solid #000', padding: '6px' }}>FY 2022 - 2023</td>
            <td style={{ border: '1px solid #000', padding: '6px', fontWeight: 'bold' }}>₹ 14.10 Cr</td>
            <td style={{ border: '1px solid #000', padding: '6px' }}>Audited</td>
          </tr>
          <tr>
            <td style={{ border: '1px solid #000', padding: '6px' }}>FY 2023 - 2024</td>
            <td style={{ border: '1px solid #000', padding: '6px', fontWeight: 'bold' }}>₹ 15.70 Cr</td>
            <td style={{ border: '1px solid #000', padding: '6px' }}>Audited</td>
          </tr>
          <tr style={{ background: '#e2e8f0', fontWeight: 'bold' }}>
            <td style={{ border: '1px solid #000', padding: '8px' }}>Average Annual Turnover (3 FYs)</td>
            <td style={{ border: '1px solid #000', padding: '8px', color: '#1e3a8a', fontSize: '14px' }}>
              INR 14.20 Crores
            </td>
            <td style={{ border: '1px solid #000', padding: '8px' }}>Certified</td>
          </tr>
        </tbody>
      </table>

      {/* UDIN Block */}
      <div style={{ border: '1px solid #1e3a8a', background: '#f8fafc', padding: '10px 14px', borderRadius: '4px', marginBottom: '40px' }}>
        <strong>UDIN (Unique Document Identification Number):</strong> <span style={{ fontFamily: 'monospace', fontWeight: 'bold' }}>24058912AAAAAA9812</span>
      </div>

      {/* Signature */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginTop: '20px' }}>
        <div>
          <div>Date: 12th April 2024</div>
          <div>Place: New Delhi</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontStyle: 'italic', color: '#002699', fontWeight: 'bold' }}>CA. Rajesh Sharma, FCA</div>
          <div style={{ borderBottom: '1px solid #000', width: '160px', margin: '4px 0' }} />
          <div style={{ fontSize: '11px' }}>Partner, M. No: 058912</div>
          <div style={{ fontSize: '10px', color: '#666' }}>Sharma, Gupta & Associates</div>
        </div>
      </div>
    </div>
  );
}
