import { useState, useEffect, useRef } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { logout, getToken, getMe } from '../api/client';
import { loginSuccess } from '../store/slices/authSlice';
import { setLang, selectLang, LANG_NAMES } from '../store/slices/i18nSlice';
import { useTranslation } from '../i18n/translations';

const ROLE_META = {
  PROCUREMENT_OFFICER: { label: 'Procurement Officer', icon: '🔐', color: '#10b981', bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.3)', short: 'OFFICER' },
  BIDDER:              { label: 'Bidder / Vendor',     icon: '🏢', color: '#06b6d4', bg: 'rgba(6,182,212,0.12)',  border: 'rgba(6,182,212,0.3)',  short: 'BIDDER'  },
};

function Tricolor() {
  return (
    <div style={{ display: 'flex', height: 2.5 }}>
      <div style={{ flex: 1, background: '#FF6600' }} />
      <div style={{ flex: 1, background: '#FFFFFF' }} />
      <div style={{ flex: 1, background: '#138808' }} />
    </div>
  );
}

export default function TopNav() {
  const navigate  = useNavigate();
  const dispatch  = useDispatch();
  const lang      = useSelector(selectLang);
  const t         = useTranslation(lang);
  const [user, setUser]         = useState(null);
  const [showLang, setShowLang] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(typeof window !== 'undefined' ? window.innerWidth <= 880 : false);
  const langRef = useRef(null);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth <= 880;
      setIsMobile(mobile);
      if (!mobile) setMobileMenuOpen(false);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    loadCurrentUser();
    const hs = () => loadCurrentUser();
    window.addEventListener('storage', hs);
    window.addEventListener('gemguard:persona_changed', hs);
    return () => {
      window.removeEventListener('storage', hs);
      window.removeEventListener('gemguard:persona_changed', hs);
    };
  }, []);

  useEffect(() => {
    function handler(e) {
      if (langRef.current && !langRef.current.contains(e.target)) setShowLang(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  async function loadCurrentUser() {
    const currentRole = localStorage.getItem('role') || 'PROCUREMENT_OFFICER';
    if (getToken()) {
      try {
        const me = await getMe();
        if (me) {
          setUser(me);
          if (me.role) {
            localStorage.setItem('role', me.role);
            if (me.name) localStorage.setItem('user_name', me.name);
            dispatch(loginSuccess({
              token: getToken(),
              role: me.role,
              name: me.name || me.company_name || 'User',
              email: me.username || me.email || '',
            }));
          }
          return;
        }
      } catch { /* fall through */ }
    }
    setUser({
      role: currentRole,
      name: localStorage.getItem('user_name') || ROLE_META[currentRole]?.label || 'Officer',
    });
  }

  function handleLogout() {
    setMobileMenuOpen(false);
    logout();
    navigate('/', { replace: true });
  }

  const role = user?.role || 'PROCUREMENT_OFFICER';
  const meta = ROLE_META[role] || ROLE_META['PROCUREMENT_OFFICER'];

  const NAV_ITEMS = [
    { to: '/dashboard',   label: t('nav_dashboard'),  icon: '🏠', roles: ['PROCUREMENT_OFFICER'] },
    { to: '/tenders',     label: t('nav_tenders'),    icon: '📋', roles: ['PROCUREMENT_OFFICER'] },
    { to: '/bids',        label: t('nav_bids'),       icon: '📦', roles: ['PROCUREMENT_OFFICER'] },
    { to: '/compliance',  label: t('nav_compliance'), icon: '⚖️', roles: ['PROCUREMENT_OFFICER'] },
    { to: '/financial',   label: t('nav_financial'),  icon: '💰', roles: ['PROCUREMENT_OFFICER'] },
    { to: '/my-bids',     label: t('nav_bids_mine'),  icon: '🏢', roles: ['BIDDER'] },
  ].filter(item => item.roles.includes(role));

  return (
    <div style={{ width: '100%', maxWidth: '100%', position: 'sticky', top: 0, zIndex: 900, boxSizing: 'border-box' }}>
      <Tricolor />
      <header
        role="navigation"
        aria-label="Main Navigation"
        style={{
          background: 'linear-gradient(90deg, #071120 0%, #0b1b36 50%, #071120 100%)',
          boxShadow: '0 4px 20px rgba(0,0,0,0.35)',
          borderBottom: '1px solid rgba(255,255,255,0.07)',
          minHeight: 54,
          padding: isMobile ? '0 12px' : '0 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxSizing: 'border-box',
          width: '100%',
        }}
      >
        {/* ── Left: Brand ───────────────────────────── */}
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div
            onClick={() => { setMobileMenuOpen(false); navigate(role === 'BIDDER' ? '/my-bids' : '/dashboard'); }}
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', userSelect: 'none' }}
          >
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: 'linear-gradient(135deg, #003366, #1a5276)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 2px 8px rgba(0,51,102,0.5)',
              border: '1px solid rgba(255,255,255,0.15)',
              flexShrink: 0,
            }}>
              <span style={{ fontSize: 16 }}>🛡️</span>
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ fontSize: isMobile ? 14 : 15, fontWeight: 800, color: '#F1F5F9', letterSpacing: '-0.02em', whiteSpace: 'nowrap' }}>
                  <span style={{ color: '#FF9900' }}>Rashtra</span>Bid
                </span>
                <span style={{ fontSize: 9, fontWeight: 800, color: '#FBBF24', background: 'rgba(255,153,0,0.15)', border: '1px solid rgba(251,191,36,0.3)', padding: '1px 4px', borderRadius: 4, letterSpacing: '0.04em' }}>
                  CPCL
                </span>
              </div>
              {!isMobile && (
                <div style={{ fontSize: 9, color: '#64748B', fontWeight: 500 }}>SIH26100 · Compliance Copilot</div>
              )}
            </div>
          </div>

          {/* Desktop Nav links */}
          {!isMobile && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 2, marginLeft: 22 }}>
              {NAV_ITEMS.map(item => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  style={({ isActive }) => ({
                    color: isActive ? '#FBBF24' : '#94A3B8',
                    borderBottom: isActive ? '2px solid #FF9900' : '2px solid transparent',
                    fontSize: 12,
                    fontWeight: isActive ? 700 : 500,
                    padding: '0 11px',
                    height: 54,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    textDecoration: 'none',
                    transition: 'all 0.15s',
                  })}
                >
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          )}
        </div>

        {/* ── Right: Language + Actions ───────────────────── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 6 : 9 }}>
          {/* Language picker */}
          <div ref={langRef} style={{ position: 'relative' }}>
            <button
              onClick={() => setShowLang(v => !v)}
              aria-label="Change language"
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.12)',
                color: '#94A3B8', cursor: 'pointer', padding: isMobile ? '4px 8px' : '5px 10px',
                borderRadius: 6, fontSize: 11, fontWeight: 700,
              }}
            >
              <span>🌐</span>
              <span>{isMobile ? lang.toUpperCase() : LANG_NAMES[lang]}</span>
              <span style={{ fontSize: 8 }}>{showLang ? '▲' : '▼'}</span>
            </button>
            {showLang && (
              <div style={{
                position: 'absolute', top: 'calc(100% + 6px)', right: 0,
                background: '#111827', border: '1px solid #1F2937', borderRadius: 8,
                overflow: 'hidden', boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
                zIndex: 1000, minWidth: 155,
              }}>
                {Object.entries(LANG_NAMES).map(([code, name]) => (
                  <button
                    key={code}
                    onClick={() => { dispatch(setLang(code)); setShowLang(false); }}
                    style={{
                      display: 'block', width: '100%', padding: '8px 14px', border: 'none',
                      background: lang === code ? 'rgba(0,51,102,0.5)' : 'transparent',
                      color: lang === code ? '#93C5FD' : '#D1D5DB', cursor: 'pointer',
                      fontSize: 12, textAlign: 'left', fontWeight: lang === code ? 700 : 400,
                      borderLeft: lang === code ? '3px solid #003366' : '3px solid transparent',
                    }}
                  >
                    {name}
                  </button>
                ))}
              </div>
            )}
          </div>

          {!isMobile && (
            <>
              {/* Desktop Role badge */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, background: meta.bg, border: `1px solid ${meta.border}`, borderRadius: 7, padding: '5px 11px' }}>
                <span style={{ fontSize: 13 }}>{meta.icon}</span>
                <div>
                  <div style={{ fontSize: 8, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>Signed in as</div>
                  <div style={{ fontSize: 11, fontWeight: 800, color: meta.color, lineHeight: 1.2 }}>{meta.label}</div>
                </div>
                <span style={{ fontSize: 9, fontWeight: 800, color: meta.color, background: meta.bg, border: `1px solid ${meta.border}`, padding: '2px 6px', borderRadius: 4 }}>
                  ● {meta.short}
                </span>
              </div>

              {/* Desktop Sign Out */}
              <button
                id="btn-logout"
                onClick={handleLogout}
                style={{ fontSize: 11, fontWeight: 700, padding: '6px 12px', borderRadius: 6, border: '1px solid rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.1)', color: '#F87171', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
              >
                ⏻ {t('nav_logout')}
              </button>
            </>
          )}

          {/* Mobile Hamburger Button */}
          {isMobile && (
            <button
              id="btn-mobile-menu-toggle"
              aria-label={mobileMenuOpen ? 'Close Menu' : 'Open Menu'}
              onClick={() => setMobileMenuOpen(v => !v)}
              style={{
                width: 36, height: 36, borderRadius: 8,
                background: mobileMenuOpen ? 'rgba(255,153,0,0.2)' : 'rgba(255,255,255,0.07)',
                border: mobileMenuOpen ? '1px solid #FF9900' : '1px solid rgba(255,255,255,0.15)',
                color: mobileMenuOpen ? '#FF9900' : '#F1F5F9',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 18, cursor: 'pointer', transition: 'all 0.15s',
              }}
            >
              {mobileMenuOpen ? '✕' : '☰'}
            </button>
          )}
        </div>
      </header>

      {/* ── Mobile Navigation Drawer / Dropdown ────────────────── */}
      {isMobile && mobileMenuOpen && (
        <div
          style={{
            background: 'linear-gradient(180deg, #071120 0%, #0a172e 100%)',
            borderBottom: '2px solid rgba(255,153,0,0.3)',
            boxShadow: '0 12px 30px rgba(0,0,0,0.8)',
            padding: '14px 16px',
            animation: 'slideDownFade 0.2s ease',
            boxSizing: 'border-box',
            width: '100%',
          }}
        >
          {/* User Profile Card */}
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            background: meta.bg, border: `1px solid ${meta.border}`,
            borderRadius: 8, padding: '9px 12px', marginBottom: 12,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <span style={{ fontSize: 18 }}>{meta.icon}</span>
              <div>
                <div style={{ fontSize: 12, fontWeight: 800, color: meta.color }}>{meta.label}</div>
                <div style={{ fontSize: 10, color: '#94A3B8' }}>{user?.name || 'Authorized Official'}</div>
              </div>
            </div>
            <span style={{ fontSize: 9, fontWeight: 800, color: meta.color, background: 'rgba(0,0,0,0.25)', padding: '2px 7px', borderRadius: 12 }}>
              ● {meta.short}
            </span>
          </div>

          {/* Navigation Links */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 14 }}>
            {NAV_ITEMS.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMobileMenuOpen(false)}
                style={({ isActive }) => ({
                  color: isActive ? '#FBBF24' : '#E2E8F0',
                  background: isActive ? 'rgba(255,153,0,0.12)' : 'rgba(255,255,255,0.03)',
                  border: isActive ? '1px solid rgba(251,191,36,0.35)' : '1px solid rgba(255,255,255,0.05)',
                  borderLeft: isActive ? '3px solid #FF9900' : '1px solid rgba(255,255,255,0.05)',
                  fontSize: 13,
                  fontWeight: isActive ? 800 : 500,
                  padding: '10px 14px',
                  borderRadius: 6,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  textDecoration: 'none',
                })}
              >
                <span style={{ fontSize: 16 }}>{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>

          {/* Mobile Sign Out Button */}
          <button
            id="btn-logout-mobile"
            onClick={handleLogout}
            style={{
              width: '100%', padding: '11px 14px', borderRadius: 8,
              border: '1px solid rgba(239,68,68,0.4)', background: 'rgba(239,68,68,0.15)',
              color: '#FCA5A5', fontSize: 13, fontWeight: 800, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            }}
          >
            <span>⏻</span>
            <span>{t('nav_logout')}</span>
          </button>
        </div>
      )}
    </div>
  );
}
