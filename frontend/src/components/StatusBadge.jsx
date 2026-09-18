const STATUS_MAP = {
  PASS:                 { label: 'PASS',                 className: 'badge badge-pass', icon: '✓' },
  COMPLIANT:            { label: 'COMPLIANT',            className: 'badge badge-pass', icon: '✓' },
  FAIL:                 { label: 'FAIL',                 className: 'badge badge-fail', icon: '✕' },
  NON_COMPLIANT:        { label: 'NON-COMPLIANT',        className: 'badge badge-fail', icon: '✕' },
  'NON-COMPLIANT':      { label: 'NON-COMPLIANT',        className: 'badge badge-fail', icon: '✕' },
  REVIEW:               { label: 'REVIEW',               className: 'badge badge-review', icon: '⚠' },
  UNDER_REVIEW:         { label: 'UNDER REVIEW',         className: 'badge badge-review', icon: '⚠' },
  PARTIAL:              { label: 'PARTIAL',              className: 'badge badge-review', icon: '⚠' },
  PARTIALLY_COMPLIANT:  { label: 'PARTIAL',              className: 'badge badge-review', icon: '⚠' },
  PENDING:              { label: 'PENDING',              className: 'badge badge-pending', icon: '⏳' },
  PENDING_VERIFICATION: { label: 'PENDING',              className: 'badge badge-pending', icon: '⏳' },
  ACTIVE:               { label: 'ACTIVE',               className: 'badge badge-pass', icon: '●' },
  CLOSED:               { label: 'CLOSED',               className: 'badge badge-pending', icon: '●' },
  AWARDED:              { label: 'AWARDED',              className: 'badge badge-pass', icon: '★' },
  APPROVED:             { label: 'APPROVED',             className: 'badge badge-pass', icon: '✓' },
  REJECTED:             { label: 'REJECTED',             className: 'badge badge-fail', icon: '✕' },
  FLAGGED:              { label: 'FLAGGED',              className: 'badge badge-review', icon: '🚩' },
  LOW:                  { label: 'LOW RISK',             className: 'badge badge-pass', icon: '🛡️' },
  MEDIUM:               { label: 'MEDIUM RISK',          className: 'badge badge-review', icon: '⚡' },
  HIGH:                 { label: 'HIGH RISK',            className: 'badge badge-fail', icon: '⚠' },
  CRITICAL:             { label: 'CRITICAL RISK',        className: 'badge badge-fail', icon: '🚨' },
  MSME:                 { label: 'MSME',                 className: 'badge badge-pending', icon: '🏢' },
  LARGE:                { label: 'LARGE',                className: 'badge badge-pending', icon: '🏭' },
  STARTUP:              { label: 'STARTUP',              className: 'badge badge-pending', icon: '🚀' },
};

export default function StatusBadge({ status, showIcon = true }) {
  if (!status) return <span className="badge badge-pending">—</span>;
  const key = String(status).toUpperCase().trim();
  const cfg = STATUS_MAP[key] ?? {
    label: status,
    className: 'badge badge-pending',
    icon: '•',
  };

  return (
    <span className={cfg.className} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      {showIcon && <span style={{ fontSize: 10 }}>{cfg.icon}</span>}
      <span>{cfg.label}</span>
    </span>
  );
}

