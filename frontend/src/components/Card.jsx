export function Card({ children, style, className = '' }) {
  return (
    <div className={`card ${className}`} style={style}>
      {children}
    </div>
  );
}

export function CardSection({ title, subtitle, children, action }) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '14px 18px 0', borderBottom: '1px solid #f1f5f9', marginBottom: 0 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: '13px', color: '#0f172a' }}>{title}</div>
          {subtitle && <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: 1 }}>{subtitle}</div>}
        </div>
        {action && <div>{action}</div>}
      </div>
      {children}
    </div>
  );
}

export function LoadingSpinner({ text = 'Loading...' }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '20px 0', color: '#64748b', fontSize: 13 }}>
      <div style={{
        width: 16, height: 16, border: '2px solid #e2e8f0',
        borderTopColor: '#1d4ed8', borderRadius: '50%',
        animation: 'spin 0.7s linear infinite'
      }} />
      {text}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  );
}

export function ErrorMessage({ message }) {
  return (
    <div style={{
      padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca',
      borderRadius: 4, color: '#b91c1c', fontSize: 13
    }}>
      {message}
    </div>
  );
}

export function EmptyState({ text }) {
  return (
    <div style={{ padding: '32px 0', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
      {text}
    </div>
  );
}
