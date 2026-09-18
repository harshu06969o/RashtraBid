import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { login, registerBidder } from '../api/client';
import { loginSuccess } from '../store/slices/authSlice';

// Role → post-login destination
const ROLE_ROUTES = {
  PROCUREMENT_OFFICER: '/dashboard',
  BIDDER: '/my-bids',
};



const INPUT_STYLE = {
  width: '100%', padding: '10px 12px', borderRadius: 8, fontSize: 14,
  background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)',
  color: '#f1f5f9', outline: 'none', boxSizing: 'border-box',
};

const SMALL_INPUT_STYLE = {
  width: '100%', padding: '8px 10px', borderRadius: 6, fontSize: 12,
  background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)',
  color: '#f1f5f9', outline: 'none', boxSizing: 'border-box',
};

export default function LoginPage() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const [tab, setTab] = useState('LOGIN');

  // Login state
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  // Register state
  const [regUsername, setRegUsername] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regFullName, setRegFullName] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [gstin, setGstin] = useState('');
  const [pan, setPan] = useState('');
  const [category, setCategory] = useState('MSME');
  const [state, _setState] = useState('New Delhi');
  const [turnover, setTurnover] = useState('14.2');

  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleLogin(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await login(username.trim(), password);
      // Dispatch to Redux so TopNav and all components pick up role immediately
      dispatch(loginSuccess({
        token: res.token,
        role: res.role,
        name: res.name || res.user?.name,
        email: res.username || username.trim(),
        department: res.user?.department || '',
      }));
      // Role-based routing — strict workspace isolation
      const dest = ROLE_ROUTES[res.role] || '/dashboard';
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await registerBidder({
        username: regUsername.trim(),
        password: regPassword,
        name: regFullName.trim(),
        company_name: companyName.trim(),
        gstin: gstin.trim().toUpperCase(),
        pan: pan.trim().toUpperCase(),
        category,
        state,
        turnover_cr: parseFloat(turnover) || 0,
      });
      navigate('/my-bids', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e3a5f 40%, #0f172a 100%)',
      fontFamily: "'Inter', sans-serif", padding: '24px',
    }}>
      {/* Ambient glow */}
      <div style={{
        position: 'fixed', top: '15%', left: '50%', transform: 'translateX(-50%)',
        width: 600, height: 300, borderRadius: '50%', pointerEvents: 'none',
        background: 'radial-gradient(ellipse, rgba(59,130,246,0.12) 0%, transparent 70%)',
      }} />

      <div style={{
        background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 20, padding: '40px 36px', width: tab === 'REGISTER' ? 540 : 420,
        maxWidth: '100%', backdropFilter: 'blur(20px)',
        boxShadow: '0 32px 80px rgba(0,0,0,0.5)', transition: 'all 0.3s ease',
        position: 'relative',
      }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{
            width: 60, height: 60, borderRadius: 16,
            background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px', fontSize: 26,
            boxShadow: '0 8px 32px rgba(59,130,246,0.45)',
          }}>🛡️</div>
          <h1 style={{ color: '#f1f5f9', fontSize: 24, fontWeight: 800, margin: '0 0 6px', letterSpacing: '-0.5px' }}>
            RashtraBid
          </h1>
          <p style={{ color: '#64748b', fontSize: 12, margin: 0 }}>
            AI-Powered Bid Compliance Verification · SIH26100
          </p>
        </div>

        {/* Tab Switcher */}
        <div style={{
          display: 'flex', background: 'rgba(255,255,255,0.06)', borderRadius: 10,
          padding: 4, marginBottom: 24, border: '1px solid rgba(255,255,255,0.08)',
        }}>
          {['LOGIN', 'REGISTER'].map(t => (
            <button
              key={t}
              type="button"
              onClick={() => { setTab(t); setError(null); }}
              style={{
                flex: 1, padding: '9px', borderRadius: 8, border: 'none', fontSize: 13, fontWeight: 600,
                background: tab === t ? 'linear-gradient(135deg, #2563eb, #1d4ed8)' : 'transparent',
                color: tab === t ? '#fff' : '#64748b', cursor: 'pointer',
                transition: 'all 0.2s',
                boxShadow: tab === t ? '0 4px 12px rgba(37,99,235,0.4)' : 'none',
              }}
            >
              {t === 'LOGIN' ? '🔐 Officer & Bidder Login' : '📝 Register Bidder'}
            </button>
          ))}
        </div>

        {error && (
          <div style={{
            background: 'rgba(220,38,38,0.15)', border: '1px solid rgba(220,38,38,0.4)',
            borderRadius: 10, padding: '12px 16px', marginBottom: 20,
            color: '#fca5a5', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8,
          }}>
            ⚠️ {error}
          </div>
        )}

        {/* LOGIN FORM */}
        {tab === 'LOGIN' ? (
          <form onSubmit={handleLogin}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', color: '#94a3b8', fontSize: 11, fontWeight: 600, marginBottom: 6, letterSpacing: '0.05em' }}>
                USERNAME / EMAIL
              </label>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="officer@gem.gov.in"
                required
                autoFocus
                style={INPUT_STYLE}
              />
            </div>

            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'block', color: '#94a3b8', fontSize: 11, fontWeight: 600, marginBottom: 6, letterSpacing: '0.05em' }}>
                PASSWORD
              </label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                style={INPUT_STYLE}
              />
            </div>

            <button
              id="login-submit"
              type="submit"
              disabled={loading}
              style={{
                width: '100%', padding: '12px', borderRadius: 10, border: 'none',
                cursor: loading ? 'not-allowed' : 'pointer',
                background: loading ? '#374151' : 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                color: '#fff', fontWeight: 700, fontSize: 15,
                boxShadow: loading ? 'none' : '0 4px 16px rgba(59,130,246,0.4)',
                transition: 'all 0.2s',
              }}
            >
              {loading ? '⏳ Authenticating…' : '→ Sign In to RashtraBid'}
            </button>
          </form>
        ) : (
          /* REGISTER FORM */
          <form onSubmit={handleRegister}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: 11, fontWeight: 600, marginBottom: 4 }}>COMPANY LEGAL NAME</label>
                <input type="text" required placeholder="Infralink Tech Ltd"
                  value={companyName} onChange={e => setCompanyName(e.target.value)} style={SMALL_INPUT_STYLE} />
              </div>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: 11, fontWeight: 600, marginBottom: 4 }}>AUTHORIZED REP</label>
                <input type="text" required placeholder="Rajesh Kumar"
                  value={regFullName} onChange={e => setRegFullName(e.target.value)} style={SMALL_INPUT_STYLE} />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: 11, fontWeight: 600, marginBottom: 4 }}>GSTIN (15 chars)</label>
                <input type="text" required placeholder="07AACCI4520M1ZP" maxLength={15}
                  value={gstin} onChange={e => setGstin(e.target.value.toUpperCase())}
                  style={{ ...SMALL_INPUT_STYLE, fontFamily: 'monospace' }} />
              </div>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: 11, fontWeight: 600, marginBottom: 4 }}>PAN (10 chars)</label>
                <input type="text" required placeholder="AACCI4520M" maxLength={10}
                  value={pan} onChange={e => setPan(e.target.value.toUpperCase())}
                  style={{ ...SMALL_INPUT_STYLE, fontFamily: 'monospace' }} />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: 11, fontWeight: 600, marginBottom: 4 }}>ENTERPRISE CATEGORY</label>
                <select value={category} onChange={e => setCategory(e.target.value)}
                  style={{ ...SMALL_INPUT_STYLE, background: '#1e293b' }}>
                  <option value="MSME">MSME (Udyam Verified)</option>
                  <option value="STARTUP">DPIIT Recognized Startup</option>
                  <option value="LARGE">Large Commercial Enterprise</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: 11, fontWeight: 600, marginBottom: 4 }}>ANNUAL TURNOVER (₹ Cr)</label>
                <input type="number" step="0.1" required placeholder="14.2"
                  value={turnover} onChange={e => setTurnover(e.target.value)} style={SMALL_INPUT_STYLE} />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: 11, fontWeight: 600, marginBottom: 4 }}>LOGIN USERNAME</label>
                <input type="text" required placeholder="infralink_bidder"
                  value={regUsername} onChange={e => setRegUsername(e.target.value)} style={SMALL_INPUT_STYLE} />
              </div>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: 11, fontWeight: 600, marginBottom: 4 }}>PASSWORD</label>
                <input type="password" required placeholder="••••••••"
                  value={regPassword} onChange={e => setRegPassword(e.target.value)} style={SMALL_INPUT_STYLE} />
              </div>
            </div>

            <button type="submit" disabled={loading}
              style={{
                width: '100%', padding: '12px', borderRadius: 10, border: 'none',
                cursor: loading ? 'not-allowed' : 'pointer',
                background: loading ? '#374151' : 'linear-gradient(135deg, #10b981, #059669)',
                color: '#fff', fontWeight: 700, fontSize: 14,
                boxShadow: loading ? 'none' : '0 4px 16px rgba(16,185,129,0.4)',
              }}>
              {loading ? '⏳ Creating Organization Profile…' : '✓ Register Bidder & Enter Portal'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
