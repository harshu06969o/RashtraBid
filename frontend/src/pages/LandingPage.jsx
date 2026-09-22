/**
 * RashtraBid — LandingPage v4 (AICTE-Portal Style)
 * Fluid · Blazing Fast · Government-Grade Design
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { loginSuccess } from '../store/slices/authSlice';
import { setLang as setGlobalLang, selectLang, LANG_NAMES } from '../store/slices/i18nSlice';
import { useTranslation } from '../i18n/translations';
import { login, registerBidder } from '../api/client';

const C = {
  saffron: '#FF6600', saffronL: '#FF9100', saffronD: '#E55A00',
  green: '#138808', greenL: '#16A34A', greenD: '#0F6906',
  navy: '#00337A', navyL: '#1A4A8F', navyD: '#001F52', navyMid: '#004494',
  gray50: '#F8FAFC', gray100: '#F1F5F9', gray200: '#E2E8F0',
  gray400: '#94A3B8', gray500: '#64748B', gray700: '#334155', gray900: '#0F172A',
};
const FONT = "'Inter','Segoe UI',system-ui,sans-serif";

function AshokaEmblem({ size = 44 }) {
  return (
    <svg viewBox="0 0 100 114" width={size} height={size + 14} xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
      <rect x="18" y="93" width="64" height="6" rx="2" fill="#7C5A10" />
      <rect x="14" y="97" width="72" height="5" rx="1.5" fill="#9B7215" />
      <circle cx="50" cy="72" r="13" fill="none" stroke={C.navy} strokeWidth="2.5" />
      <circle cx="50" cy="72" r="3.5" fill={C.navy} />
      {Array.from({ length: 24 }, (_, i) => {
        const a = (i * 15) * Math.PI / 180;
        return <line key={i} x1={50 + 3.5 * Math.cos(a)} y1={72 + 3.5 * Math.sin(a)} x2={50 + 12 * Math.cos(a)} y2={72 + 12 * Math.sin(a)} stroke={C.navy} strokeWidth="0.9" />;
      })}
      <ellipse cx="36" cy="60" rx="11" ry="9" fill="#C8940A" />
      <circle cx="33" cy="49" r="8" fill="#C8940A" />
      <circle cx="33" cy="47" r="10" fill="none" stroke="#8B6000" strokeWidth="2.8" />
      <circle cx="31" cy="47" r="1.8" fill="#2A1200" />
      <ellipse cx="64" cy="60" rx="11" ry="9" fill="#C8940A" />
      <circle cx="67" cy="49" r="8" fill="#C8940A" />
      <circle cx="67" cy="47" r="10" fill="none" stroke="#8B6000" strokeWidth="2.8" />
      <circle cx="69" cy="47" r="1.8" fill="#2A1200" />
      <path d="M25 60 Q20 52 24 44" stroke="#C8940A" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      <path d="M75 60 Q80 52 76 44" stroke="#C8940A" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      <text x="50" y="112" textAnchor="middle" fontSize="6" fill="#111827" fontFamily="serif" fontWeight="700" letterSpacing="0.5">सत्यमेव जयते</text>
    </svg>
  );
}

function Tricolor({ h = 3 }) {
  return (
    <div style={{ display: 'flex', height: h }}>
      <div style={{ flex: 1, background: C.saffron }} />
      <div style={{ flex: 1, background: '#FFF', borderTop: '0.5px solid #e5e7eb', borderBottom: '0.5px solid #e5e7eb' }} />
      <div style={{ flex: 1, background: C.green }} />
    </div>
  );
}

function useLiveMetrics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const fetch_ = useCallback(async () => {
    try {
      const token = localStorage.getItem('rashtrabid_token') || localStorage.getItem('gemguard_token') || '';
      const h = token ? { Authorization: `Bearer ${token}` } : {};
      const [bR, tR] = await Promise.allSettled([
        fetch('/api/v1/bids', { headers: h }).then(r => r.ok ? r.json() : []),
        fetch('/api/v1/tenders', { headers: h }).then(r => r.ok ? r.json() : []),
      ]);
      const bids = bR.status === 'fulfilled' ? (Array.isArray(bR.value) ? bR.value : bR.value?.bids ?? []) : [];
      const tenders = tR.status === 'fulfilled' ? (Array.isArray(tR.value) ? tR.value : tR.value?.tenders ?? []) : [];
      const total = bids.length;
      const approved = bids.filter(b => ['APPROVED', 'PASS', 'COMPLIANT'].includes(b.overall_status ?? b.status ?? '')).length;
      const pending = bids.filter(b => ['PENDING', 'UNDER_REVIEW'].includes(b.overall_status ?? b.status ?? '')).length;
      const flagged = bids.filter(b => ['FAIL', 'NON_COMPLIANT', 'REJECTED'].includes(b.overall_status ?? b.status ?? '')).length;
      const score = total > 0 ? Math.round((approved / total) * 1000) / 10 : 0;
      const activeTenders = tenders.filter(t => ['ACTIVE', 'PUBLISHED'].includes((t.status ?? 'ACTIVE').toUpperCase())).length || tenders.length;
      setData({ total, approved, pending, flagged, score, activeTenders, tenders, bids });
    } catch {
      setData({ total: 0, approved: 0, pending: 0, flagged: 0, score: 0, activeTenders: 0, tenders: [], bids: [] });
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { fetch_(); const id = setInterval(fetch_, 30000); return () => clearInterval(id); }, [fetch_]);
  return { data, loading };
}

function AnimCounter({ to }) {
  const [val, setVal] = useState(0);
  const raf = useRef(null);
  useEffect(() => {
    if (!to) { setVal(0); return; }
    const start = Date.now(); const dur = 800;
    const tick = () => {
      const p = Math.min((Date.now() - start) / dur, 1);
      setVal(Math.round((1 - Math.pow(1 - p, 3)) * to));
      if (p < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [to]);
  return <>{val}</>;
}

function TopRibbon({ t, lang, onLangChange, dark, onDarkToggle, textScale, onScaleChange }) {
  const [showLang, setShowLang] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const fn = (e) => { if (ref.current && !ref.current.contains(e.target)) setShowLang(false); };
    document.addEventListener('mousedown', fn);
    return () => document.removeEventListener('mousedown', fn);
  }, []);
  return (
    <div style={{ background: '#001338', position: 'sticky', top: 0, zIndex: 1000 }}>
      <Tricolor h={2.5} />
      <div style={{ maxWidth: 1440, margin: '0 auto', padding: '5px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: '#E2E8F0', letterSpacing: '0.04em' }}>{t('ribbon_gov')}</span>
          <div style={{ width: 1, height: 11, background: '#1E3A5F' }} />
          <span style={{ fontSize: 9, color: '#4B5563' }}>{t('ribbon_portal')}</span>
          <div style={{ width: 1, height: 11, background: '#1E3A5F' }} />
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 9, fontWeight: 800, padding: '1px 8px', borderRadius: 20, background: 'rgba(16,185,129,0.12)', color: '#34D399', border: '1px solid rgba(16,185,129,0.3)' }}>
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#34D399', display: 'inline-block', animation: 'rbpulse 1.8s infinite' }} /> LIVE
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ display: 'flex', gap: 1, background: '#0D1B2A', borderRadius: 4, padding: '2px 3px' }}>
            {['A-', 'A', 'A+'].map((s, i) => (
              <button key={i} onClick={() => onScaleChange(i)} style={{ background: textScale === i ? C.navyMid : 'transparent', border: 'none', color: textScale === i ? '#FFF' : '#4B5563', cursor: 'pointer', padding: '1px 5px', borderRadius: 3, fontSize: i === 0 ? 9 : i === 1 ? 10 : 12, fontWeight: 800 }}>{s}</button>
            ))}
          </div>
          <button onClick={onDarkToggle} style={{ background: dark ? 'rgba(59,130,246,0.15)' : '#0D1B2A', border: `1px solid ${dark ? 'rgba(59,130,246,0.3)' : '#1E3A5F'}`, color: dark ? '#93C5FD' : '#4B5563', cursor: 'pointer', padding: '2px 7px', borderRadius: 4, fontSize: 9, fontWeight: 700 }}>{dark ? '☀' : '◑'}</button>
          <div ref={ref} style={{ position: 'relative' }}>
            <button onClick={() => setShowLang(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: 4, background: '#0D1B2A', border: '1px solid #1E3A5F', color: '#4B5563', cursor: 'pointer', padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700 }}>
              🌐 {LANG_NAMES[lang]} <span style={{ fontSize: 8 }}>{showLang ? '▲' : '▼'}</span>
            </button>
            {showLang && (
              <div style={{ position: 'absolute', top: 'calc(100% + 5px)', right: 0, background: '#0D1117', border: '1px solid #1E3A5F', borderRadius: 8, overflow: 'hidden', boxShadow: '0 8px 32px rgba(0,0,0,0.6)', zIndex: 2000, minWidth: 155 }}>
                {Object.entries(LANG_NAMES).map(([code, name]) => (
                  <button key={code} onClick={() => { onLangChange(code); setShowLang(false); }} style={{ display: 'block', width: '100%', padding: '8px 14px', border: 'none', background: lang === code ? 'rgba(0,68,148,0.35)' : 'transparent', color: lang === code ? '#93C5FD' : '#CBD5E1', cursor: 'pointer', fontSize: 12, textAlign: 'left', fontWeight: lang === code ? 700 : 400, borderLeft: lang === code ? `3px solid ${C.navyMid}` : '3px solid transparent' }}>{name}</button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function MainHeader({ t, dark, onOfficer, onBidder }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', fn, { passive: true });
    return () => window.removeEventListener('scroll', fn);
  }, []);
  const bg = scrolled ? (dark ? 'rgba(7,9,20,0.92)' : 'rgba(255,255,255,0.95)') : (dark ? '#07090F' : '#FFF');
  return (
    <header style={{ background: bg, backdropFilter: scrolled ? 'blur(16px)' : 'none', WebkitBackdropFilter: scrolled ? 'blur(16px)' : 'none', borderBottom: `1px solid ${dark ? '#111827' : C.gray200}`, boxShadow: scrolled ? '0 4px 24px rgba(0,0,0,0.08)' : 'none', transition: 'all 0.25s', position: 'sticky', top: 32, zIndex: 900 }}>
      <div style={{ maxWidth: 1440, margin: '0 auto', padding: '12px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
          <AshokaEmblem size={40} />
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 20, fontWeight: 900, letterSpacing: '-0.5px', background: `linear-gradient(135deg, ${C.navyD}, ${C.navy} 60%, ${C.navyL})`, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>RashtraBid</span>
              <span style={{ fontSize: 8, fontWeight: 800, padding: '2px 7px', borderRadius: 3, background: `linear-gradient(90deg, ${C.saffron}, ${C.saffronL})`, color: '#FFF', letterSpacing: '0.08em' }}>GeM VERIFIED</span>
            </div>
            <div style={{ fontSize: 10, color: C.gray400, marginTop: 1 }}>{t('app_subtitle')}</div>
          </div>
        </div>
        <nav style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button id="btn-bidder-portal" onClick={onBidder}
            style={{ padding: '7px 16px', borderRadius: 7, border: `1.5px solid ${C.green}`, background: 'transparent', color: C.green, fontWeight: 700, fontSize: 12, cursor: 'pointer', transition: 'all 0.18s', fontFamily: FONT }}
            onMouseEnter={e => { e.currentTarget.style.background = C.green; e.currentTarget.style.color = '#FFF'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = C.green; }}>
            👤 {t('btn_bidder')}
          </button>
          <button id="btn-officer-login" onClick={onOfficer}
            style={{ padding: '7px 18px', borderRadius: 7, border: 'none', background: `linear-gradient(135deg, ${C.navyD}, ${C.navy})`, color: '#FFF', fontWeight: 700, fontSize: 12, cursor: 'pointer', transition: 'all 0.18s', boxShadow: '0 2px 10px rgba(0,51,122,0.35)', fontFamily: FONT }}
            onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 20px rgba(0,51,122,0.55)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
            onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 2px 10px rgba(0,51,122,0.35)'; e.currentTarget.style.transform = 'none'; }}>
            🔐 {t('btn_officer')}
          </button>
        </nav>
      </div>
    </header>
  );
}

function HeroSection({ t, dark, data, onOfficer, onBidder }) {
  const [sloganIdx, setSloganIdx] = useState(0);
  const slogans = ['slogan1', 'slogan2', 'slogan3'];
  useEffect(() => { const id = setInterval(() => setSloganIdx(i => (i + 1) % 3), 4000); return () => clearInterval(id); }, []);
  const heroBg = dark ? '#07090F' : 'linear-gradient(160deg, #F0F6FF 0%, #FAFBFF 50%, #EEF4FC 100%)';

  return (
    <section style={{ background: heroBg, position: 'relative', overflow: 'hidden' }}>
      <div aria-hidden style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
        <div style={{ position: 'absolute', top: -100, left: -80, width: 500, height: 500, borderRadius: '50%', background: 'radial-gradient(circle, rgba(0,68,148,0.07) 0%, transparent 70%)' }} />
        <div style={{ position: 'absolute', top: 60, right: -80, width: 350, height: 350, borderRadius: '50%', background: 'radial-gradient(circle, rgba(255,102,0,0.06) 0%, transparent 70%)' }} />
        <div style={{ position: 'absolute', bottom: -60, left: '40%', width: 400, height: 400, borderRadius: '50%', background: 'radial-gradient(circle, rgba(19,136,8,0.05) 0%, transparent 70%)' }} />
      </div>
      <div style={{ maxWidth: 1440, margin: '0 auto', padding: '52px 20px 60px', position: 'relative', display: 'grid', gridTemplateColumns: '1fr auto', gap: 40, alignItems: 'center' }}>
        <div style={{ maxWidth: 680 }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 18, padding: '5px 14px', borderRadius: 30, background: 'rgba(19,136,8,0.08)', border: '1px solid rgba(19,136,8,0.2)' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: C.green, display: 'inline-block', animation: 'rbpulse 2s infinite', boxShadow: `0 0 6px ${C.green}` }} />
            <span style={{ fontSize: 11, fontWeight: 800, color: C.green, letterSpacing: '0.07em' }}>{t('live_badge')}</span>
            {data?.activeTenders > 0 && <span style={{ fontSize: 10, color: C.gray400 }}>· {data.activeTenders} active tenders</span>}
          </div>
          <div style={{ fontSize: 13, color: C.saffron, fontWeight: 700, letterSpacing: '0.04em', marginBottom: 12, height: 20, overflow: 'hidden', position: 'relative' }}>
            {slogans.map((s, i) => (
              <div key={s} style={{ position: 'absolute', transition: 'all 0.55s cubic-bezier(0.4,0,0.2,1)', opacity: i === sloganIdx ? 1 : 0, transform: `translateY(${i === sloganIdx ? 0 : i < sloganIdx ? '-100%' : '100%'})`, width: '100%' }}>{t(s)}</div>
            ))}
          </div>
          <h1 style={{ margin: '0 0 16px', fontSize: 'clamp(24px, 4vw, 42px)', fontWeight: 900, color: dark ? '#F1F5F9' : C.gray900, lineHeight: 1.2, letterSpacing: '-0.5px' }}>{t('hero_title')}</h1>
          <p style={{ margin: '0 0 32px', fontSize: 15, color: dark ? '#94A3B8' : C.gray500, lineHeight: 1.75, maxWidth: 580 }}>{t('hero_sub')}</p>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 28 }}>
            <button onClick={onBidder}
              style={{ padding: '13px 28px', borderRadius: 10, border: 'none', background: `linear-gradient(135deg, ${C.greenD}, ${C.green})`, color: '#FFF', fontWeight: 800, fontSize: 14, cursor: 'pointer', boxShadow: '0 6px 20px rgba(19,136,8,0.35)', transition: 'all 0.2s', fontFamily: FONT, display: 'flex', alignItems: 'center', gap: 8 }}
              onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 10px 30px rgba(19,136,8,0.5)'; }}
              onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = '0 6px 20px rgba(19,136,8,0.35)'; }}>
              <span style={{ fontSize: 16 }}>👤</span> {t('portal_bidder_title')}
              <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 20, background: 'rgba(255,255,255,0.2)' }}>{t('portal_bidder_tag')}</span>
            </button>
            <button onClick={onOfficer}
              style={{ padding: '13px 28px', borderRadius: 10, border: 'none', background: `linear-gradient(135deg, ${C.navyD}, ${C.navy})`, color: '#FFF', fontWeight: 800, fontSize: 14, cursor: 'pointer', boxShadow: '0 6px 20px rgba(0,51,122,0.35)', transition: 'all 0.2s', fontFamily: FONT, display: 'flex', alignItems: 'center', gap: 8 }}
              onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 10px 30px rgba(0,51,122,0.5)'; }}
              onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = '0 6px 20px rgba(0,51,122,0.35)'; }}>
              <span style={{ fontSize: 16 }}>🔐</span> {t('portal_officer_title')}
              <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 20, background: 'rgba(255,166,0,0.25)', color: '#FCD34D' }}>{t('portal_officer_tag')}</span>
            </button>
          </div>
          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
            {['GIGW 3.0 Certified', 'GFR Rule 173', 'WCAG 2.1 AA', 'SHA-256 Audit'].map(tag => (
              <div key={tag} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: dark ? '#64748B' : C.gray500 }}>
                <span style={{ color: C.green, fontWeight: 700 }}>✓</span>{tag}
              </div>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 215, maxWidth: 250 }}>
          <div style={{ background: dark ? 'rgba(255,255,255,0.04)' : '#FFF', border: `1px solid ${dark ? 'rgba(255,255,255,0.07)' : C.gray200}`, borderRadius: 14, padding: '16px 18px', boxShadow: '0 2px 16px rgba(0,0,0,0.05)' }}>
            <div style={{ fontSize: 9, color: C.gray400, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Compliance Standards</div>
            <div style={{ fontSize: 13, fontWeight: 800, color: dark ? '#E2E8F0' : C.navy, marginBottom: 10, lineHeight: 1.3 }}>GeM-GFR Procurement Framework</div>
            {['GIGW 3.0', 'WCAG 2.1 AA', 'GFR Rule 173', 'RTI Act 2005'].map(s => (
              <div key={s} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 11, color: dark ? '#94A3B8' : C.gray700 }}>{s}</span>
                <div style={{ width: 18, height: 18, borderRadius: '50%', background: '#DCFCE7', border: '1px solid #86EFAC', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, color: C.green, fontWeight: 900 }}>✓</div>
              </div>
            ))}
          </div>
          <div style={{ background: dark ? 'rgba(255,255,255,0.04)' : '#FFF', border: `1px solid ${dark ? 'rgba(255,255,255,0.07)' : C.gray200}`, borderRadius: 14, padding: '14px 18px', boxShadow: '0 2px 16px rgba(0,0,0,0.05)' }}>
            <div style={{ fontSize: 9, color: C.gray400, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Registry Sync</div>
            {[['GSTN', '#22C55E'], ['UDYAM', '#22C55E'], ['CBDT-PAN', '#22C55E'], ['EPFO', '#FBBF24'], ['MCA21', '#22C55E']].map(([r, clr]) => (
              <div key={r} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 11, color: dark ? '#94A3B8' : C.gray700, fontFamily: 'monospace' }}>{r}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: clr, boxShadow: `0 0 5px ${clr}` }} />
                  <span style={{ fontSize: 9, color: clr, fontWeight: 700 }}>{clr === '#22C55E' ? 'LIVE' : 'SYNC'}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function MetricsSection({ t, dark, data, loading }) {
  const metrics = data ? [
    { icon: '📋', val: data.total, label: t('metric_total'), sub: 'Total submissions processed', color: C.navy },
    { icon: '🏛', val: data.activeTenders, label: t('metric_tenders'), sub: 'Government tenders open', color: C.navyMid },
    { icon: '✅', val: data.approved, label: t('metric_approved'), sub: 'Officer-verified decisions', color: '#059669' },
    { icon: '⏱', val: data.pending, label: t('metric_pending'), sub: 'Awaiting registry check', color: '#D97706' },
    { icon: '🔍', val: data.flagged, label: t('metric_flagged'), sub: 'Mandatory scrutiny queue', color: '#DC2626' },
    { icon: '🏆', val: data.score, suffix: '%', label: t('metric_score'), sub: 'Compliance rate · ≥80% target', color: C.navy },
  ] : [];
  return (
    <section style={{ background: dark ? '#0B0F19' : C.gray50, borderTop: `1px solid ${dark ? '#111827' : C.gray200}`, borderBottom: `1px solid ${dark ? '#111827' : C.gray200}` }}>
      <div style={{ maxWidth: 1440, margin: '0 auto', padding: '36px 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: dark ? '#F1F5F9' : C.gray900 }}>{t('metrics_heading')}</h2>
            <p style={{ margin: '4px 0 0', fontSize: 12, color: C.gray400 }}>Real-time data from GeM procurement pipeline</p>
          </div>
          <span style={{ fontSize: 9, color: C.gray400, fontFamily: 'monospace', background: dark ? 'rgba(255,255,255,0.04)' : C.gray100, padding: '4px 10px', borderRadius: 4, border: `1px solid ${dark ? '#1F2937' : C.gray200}` }}>AUTO-REFRESH 30s</span>
        </div>
        {loading ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(185px, 1fr))', gap: 14 }}>
            {Array.from({ length: 6 }).map((_, i) => <div key={i} style={{ height: 110, borderRadius: 12, background: dark ? 'rgba(255,255,255,0.04)' : C.gray100, animation: 'rbpulse 1.5s infinite' }} />)}
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(185px, 1fr))', gap: 14 }}>
            {metrics.map((m, i) => (
              <div key={i}
                style={{ background: dark ? 'rgba(255,255,255,0.04)' : '#FFF', border: `1px solid ${dark ? 'rgba(255,255,255,0.07)' : C.gray200}`, borderTop: `3px solid ${m.color}`, borderRadius: 12, padding: '16px 18px', transition: 'transform 0.2s, box-shadow 0.2s', cursor: 'default' }}
                onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.08)'; }}
                onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}>
                <div style={{ fontSize: 20, marginBottom: 10 }}>{m.icon}</div>
                <div style={{ fontSize: 30, fontWeight: 900, color: dark ? '#F1F5F9' : C.gray900, lineHeight: 1, letterSpacing: '-1px' }}>
                  <AnimCounter to={typeof m.val === 'number' ? m.val : 0} />{m.suffix || ''}
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: dark ? '#CBD5E1' : C.gray700, marginTop: 4 }}>{m.label}</div>
                <div style={{ fontSize: 10, color: C.gray400, marginTop: 3 }}>{m.sub}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

const FEATURES = [
  { icon: '🏛️', title: 'GSTN Verification', desc: 'Real-time GSTN portal validation — active status, state code, registration date cross-checked against tender eligibility.' },
  { icon: '🏭', title: 'Udyam / MSME Check', desc: 'Enterprise category, NIC classification, Udyam certificate validity verified against MoMSME registry.' },
  { icon: '🪪', title: 'PAN & Turnover Audit', desc: '3-year turnover via CBDT e-Filing, UDIN cross-check, name consistency across all documents.' },
  { icon: '👷', title: 'EPFO Compliance', desc: 'ECR filing compliance, ESIC registration validated for manpower service bids.' },
  { icon: '🇮🇳', title: 'Make in India (MII)', desc: 'Local content ≥50% per DPIIT PPP-MII Order 2020 — Class-I/II preference verified.' },
  { icon: '🔗', title: 'SHA-256 Audit Chain', desc: 'Tamper-evident, append-only audit log with hash-chained events for every compliance decision.' },
  { icon: '📊', title: 'L1 Financial Ranking', desc: 'Sealed envelopes, automated L1 identification with full price-adjusted bid ranking.' },
  { icon: '📋', title: 'Corrigendum Analyzer', desc: 'Amendment PDF impact analysis — auto-detects rule changes and flags affected bids.' },
];

function FeaturesSection({ dark }) {
  return (
    <section style={{ background: dark ? '#07090F' : '#FFF' }}>
      <div style={{ maxWidth: 1440, margin: '0 auto', padding: '52px 20px' }}>
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <span style={{ fontSize: 11, fontWeight: 800, color: C.saffron, letterSpacing: '0.12em', textTransform: 'uppercase', display: 'block', marginBottom: 10 }}>Platform Capabilities</span>
          <h2 style={{ margin: '0 0 12px', fontSize: 'clamp(20px, 3vw, 30px)', fontWeight: 900, color: dark ? '#F1F5F9' : C.gray900 }}>AI Reads. Rules Verify. Evidence Explains.</h2>
          <p style={{ margin: '0 auto', fontSize: 14, color: C.gray400, maxWidth: 540 }}>Complete statutory compliance automation for GeM procurement</p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
          {FEATURES.map((f, i) => (
            <div key={i}
              style={{ background: dark ? 'rgba(255,255,255,0.03)' : C.gray50, border: `1px solid ${dark ? 'rgba(255,255,255,0.07)' : C.gray200}`, borderRadius: 14, padding: '20px 22px', transition: 'all 0.2s', cursor: 'default' }}
              onMouseEnter={e => { e.currentTarget.style.background = dark ? 'rgba(0,68,148,0.12)' : '#EFF6FF'; e.currentTarget.style.borderColor = dark ? 'rgba(0,68,148,0.35)' : '#BFDBFE'; e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,51,122,0.09)'; }}
              onMouseLeave={e => { e.currentTarget.style.background = dark ? 'rgba(255,255,255,0.03)' : C.gray50; e.currentTarget.style.borderColor = dark ? 'rgba(255,255,255,0.07)' : C.gray200; e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}>
              <div style={{ width: 44, height: 44, borderRadius: 12, background: dark ? 'rgba(0,68,148,0.2)' : '#EFF6FF', border: `1px solid ${dark ? 'rgba(0,68,148,0.35)' : '#BFDBFE'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, marginBottom: 12 }}>{f.icon}</div>
              <div style={{ fontSize: 14, fontWeight: 800, color: dark ? '#E2E8F0' : C.gray900, marginBottom: 6 }}>{f.title}</div>
              <div style={{ fontSize: 12, color: C.gray400, lineHeight: 1.65 }}>{f.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PipelineStrip({ dark }) {
  const steps = ['PDF Upload', 'AI Extraction', 'Rule Compilation', 'Registry Verify', 'Evidence Trace', 'Officer Decision', 'Audit Sealed'];
  return (
    <section style={{ background: '#001338', borderTop: '1px solid #001F52' }}>
      <div style={{ maxWidth: 1440, margin: '0 auto', padding: '18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', overflowX: 'auto', scrollbarWidth: 'none', gap: 0 }}>
          {steps.map((s, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 6, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.07)' }}>
                <div style={{ width: 20, height: 20, borderRadius: '50%', background: `linear-gradient(135deg, ${C.saffron}, ${C.saffronL})`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 900, color: '#FFF' }}>{i + 1}</div>
                <span style={{ fontSize: 11, fontWeight: 600, color: '#94A3B8', whiteSpace: 'nowrap' }}>{s}</span>
              </div>
              {i < steps.length - 1 && <div style={{ width: 22, height: 1, background: 'rgba(255,255,255,0.1)', flexShrink: 0 }} />}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PortalModal({ dark, t, mode, onClose, onSuccess }) {
  const [tab, setTab] = useState(mode === 'BIDDER' ? 'BIDDER' : 'OFFICER');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [company, setCompany] = useState('');
  const [regName, setRegName] = useState('');
  const [gstin, setGstin] = useState('');
  const [pan, setPan] = useState('');
  const [category, setCategory] = useState('MSME');
  const [turnover, setTurnover] = useState('');
  const [regUsername, setRegUsername] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const bg = dark ? '#0D1117' : '#FFF';
  const border = dark ? '#1E3A5F' : C.gray200;
  const text = dark ? '#F1F5F9' : C.gray900;
  const sub = dark ? '#64748B' : C.gray500;
  const inp = { width: '100%', padding: '9px 12px', borderRadius: 7, border: `1px solid ${border}`, background: dark ? '#0B1628' : '#F8FAFC', color: text, fontSize: 13, fontFamily: FONT, outline: 'none', transition: 'border-color 0.18s', boxSizing: 'border-box' };
  const lbl = { display: 'block', fontSize: 11, fontWeight: 700, color: sub, marginBottom: 4 };

  async function handleLogin(e) {
    e.preventDefault(); setErr(''); setLoading(true);
    try { const res = await login(username, password); onSuccess(res); }
    catch (ex) { setErr(ex?.message || 'Login failed. Check credentials.'); }
    finally { setLoading(false); }
  }

  async function handleRegister(e) {
    e.preventDefault(); setErr(''); setLoading(true);
    try {
      const res = await registerBidder({ company_name: company, name: regName, gstin, pan, category, turnover_cr: parseFloat(turnover) || 0, username: regUsername, password: regPassword, role: 'BIDDER' });
      onSuccess(res);
    } catch (ex) { setErr(ex?.message || 'Registration failed.'); }
    finally { setLoading(false); }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 2000, padding: 16 }}
      onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{ background: bg, borderRadius: 18, width: '100%', maxWidth: 480, maxHeight: '90vh', overflowY: 'auto', boxShadow: '0 30px 80px rgba(0,0,0,0.35)', border: `1px solid ${border}` }}>
        <Tricolor h={3} />
        <div style={{ padding: '20px 24px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <AshokaEmblem size={32} />
            <div>
              <div style={{ fontSize: 15, fontWeight: 900, color: text }}>RashtraBid Portal</div>
              <div style={{ fontSize: 10, color: sub }}>Government Procurement Access</div>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', fontSize: 18, cursor: 'pointer', color: sub, padding: 4 }}>✕</button>
        </div>
        <div style={{ display: 'flex', margin: '16px 24px 0', borderRadius: 8, background: dark ? '#0B1628' : C.gray100, padding: 3, gap: 3 }}>
          {[['OFFICER', '🔐', t('btn_officer')], ['BIDDER', '👤', t('btn_bidder')]].map(([m, icon, lbText]) => (
            <button key={m} onClick={() => setTab(m)}
              style={{ flex: 1, padding: '8px 0', borderRadius: 6, border: 'none', background: tab === m ? (m === 'OFFICER' ? C.navy : C.green) : 'transparent', color: tab === m ? '#FFF' : sub, fontWeight: 700, fontSize: 12, cursor: 'pointer', transition: 'all 0.18s', fontFamily: FONT }}>
              {icon} {lbText}
            </button>
          ))}
        </div>
        <div style={{ padding: '20px 24px 24px' }}>
          {err && <div style={{ background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 8, padding: '10px 14px', marginBottom: 14, fontSize: 12, color: '#DC2626' }}>⚠ {err}</div>}
          {(tab === 'OFFICER' || tab === 'BIDDER') ? (
            <form onSubmit={handleLogin}>
              <div style={{ marginBottom: 12 }}>
                <label style={lbl}>{t('field_username')}</label>
                <input required placeholder={tab === 'OFFICER' ? 'officer@gem.gov.in' : 'your_username'} value={username} onChange={e => setUsername(e.target.value)} style={inp}
                  onFocus={e => { e.target.style.borderColor = tab === 'OFFICER' ? C.navy : C.green; }} onBlur={e => { e.target.style.borderColor = border; }} />
              </div>
              <div style={{ marginBottom: 18 }}>
                <label style={lbl}>{t('field_password')}</label>
                <input type="password" required placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} style={inp}
                  onFocus={e => { e.target.style.borderColor = tab === 'OFFICER' ? C.navy : C.green; }} onBlur={e => { e.target.style.borderColor = border; }} />
              </div>
              <button type="submit" disabled={loading}
                style={{ width: '100%', padding: '12px', borderRadius: 9, border: 'none', background: loading ? '#94A3B8' : (tab === 'OFFICER' ? `linear-gradient(135deg, ${C.navyD}, ${C.navy})` : `linear-gradient(135deg, ${C.greenD}, ${C.green})`), color: '#FFF', fontWeight: 800, fontSize: 14, cursor: loading ? 'not-allowed' : 'pointer', fontFamily: FONT }}>
                {loading ? '⏳ Signing in…' : `${tab === 'OFFICER' ? '🔐' : '👤'} ${t('btn_login')}`}
              </button>
              {tab === 'BIDDER' && (
                <button type="button" onClick={() => setTab('BIDDER_REG')}
                  style={{ width: '100%', marginTop: 10, padding: '10px', borderRadius: 9, border: `1.5px solid ${C.green}`, background: 'transparent', color: C.green, fontWeight: 700, fontSize: 13, cursor: 'pointer', fontFamily: FONT }}>
                  {t('btn_register')}
                </button>
              )}
            </form>
          ) : (
            <form onSubmit={handleRegister}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
                <div><label style={lbl}>{t('field_company')}</label><input required placeholder="Bharat Safety Pvt. Ltd" value={company} onChange={e => setCompany(e.target.value)} style={inp} onFocus={e => e.target.style.borderColor = C.green} onBlur={e => e.target.style.borderColor = border} /></div>
                <div><label style={lbl}>{t('field_rep')}</label><input required placeholder="Rajesh Kumar" value={regName} onChange={e => setRegName(e.target.value)} style={inp} onFocus={e => e.target.style.borderColor = C.green} onBlur={e => e.target.style.borderColor = border} /></div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
                <div><label style={lbl}>{t('field_gstin')}</label><input required placeholder="33AABCA1234F1Z5" maxLength={15} value={gstin} onChange={e => setGstin(e.target.value.toUpperCase())} style={{ ...inp, fontFamily: 'monospace' }} onFocus={e => e.target.style.borderColor = C.green} onBlur={e => e.target.style.borderColor = border} /></div>
                <div><label style={lbl}>{t('field_pan')}</label><input required placeholder="AABCA1234F" maxLength={10} value={pan} onChange={e => setPan(e.target.value.toUpperCase())} style={{ ...inp, fontFamily: 'monospace' }} onFocus={e => e.target.style.borderColor = C.green} onBlur={e => e.target.style.borderColor = border} /></div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
                <div><label style={lbl}>{t('field_category')}</label>
                  <select value={category} onChange={e => setCategory(e.target.value)} style={{ ...inp, background: dark ? '#0B1628' : '#F8FAFC' }}>
                    <option value="MSME">MSME (Udyam)</option>
                    <option value="STARTUP">DPIIT Startup</option>
                    <option value="LARGE">Large Enterprise</option>
                  </select>
                </div>
                <div><label style={lbl}>{t('field_turnover')} (₹ Cr)</label><input type="number" step="0.1" required placeholder="18.5" value={turnover} onChange={e => setTurnover(e.target.value)} style={inp} onFocus={e => e.target.style.borderColor = C.green} onBlur={e => e.target.style.borderColor = border} /></div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
                <div><label style={lbl}>{t('field_username')}</label><input required placeholder="bharat_safety_26" value={regUsername} onChange={e => setRegUsername(e.target.value)} style={inp} onFocus={e => e.target.style.borderColor = C.green} onBlur={e => e.target.style.borderColor = border} /></div>
                <div><label style={lbl}>{t('field_password')}</label><input type="password" required placeholder="••••••••" value={regPassword} onChange={e => setRegPassword(e.target.value)} style={inp} onFocus={e => e.target.style.borderColor = C.green} onBlur={e => e.target.style.borderColor = border} /></div>
              </div>
              <button type="submit" disabled={loading}
                style={{ width: '100%', padding: '12px', borderRadius: 9, border: 'none', background: loading ? '#94A3B8' : `linear-gradient(135deg, ${C.greenD}, ${C.green})`, color: '#FFF', fontWeight: 800, fontSize: 14, cursor: loading ? 'not-allowed' : 'pointer', fontFamily: FONT }}>
                {loading ? t('btn_registering') : t('btn_register')}
              </button>
              <button type="button" onClick={() => setTab('BIDDER')}
                style={{ width: '100%', marginTop: 8, padding: '9px', borderRadius: 9, border: `1px solid ${border}`, background: 'transparent', color: sub, fontWeight: 600, fontSize: 12, cursor: 'pointer', fontFamily: FONT }}>
                ← Back to Login
              </button>
            </form>
          )}
        </div>
        <Tricolor h={2.5} />
      </div>
    </div>
  );
}

function GovFooter({ t }) {
  return (
    <footer style={{ background: '#001338', borderTop: '1px solid #002266', marginTop: 'auto' }}>
      <Tricolor h={2.5} />
      <div style={{ maxWidth: 1440, margin: '0 auto', padding: '36px 20px 20px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(195px, 1fr))', gap: 28, marginBottom: 24 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <AshokaEmblem size={32} />
              <div>
                <div style={{ color: '#F9FAFB', fontWeight: 800, fontSize: 15 }}>RashtraBid</div>
                <div style={{ color: '#374151', fontSize: 10 }}>SIH 2026 — PS 26100</div>
              </div>
            </div>
            <div style={{ color: '#374151', fontSize: 11, lineHeight: 1.8 }}>AI-Powered Bid Compliance<br />CPCL / GeM Integration<br />Ministry of Petroleum &amp; Natural Gas</div>
            <div style={{ marginTop: 14, padding: '9px 12px', background: 'rgba(255,102,0,0.07)', borderLeft: `3px solid ${C.saffron}`, borderRadius: '0 8px 8px 0' }}>
              <div style={{ color: C.saffron, fontSize: 12, fontWeight: 700 }}>जय हिंद! जय भारत!</div>
              <div style={{ color: '#4B5563', fontSize: 10, marginTop: 2 }}>One Nation · One Portal · Zero Corruption</div>
            </div>
          </div>
          <div>
            <div style={{ color: '#9CA3AF', fontWeight: 700, fontSize: 11, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.07em' }}>Registry Links</div>
            {['GeM — gem.gov.in', 'GSTN — gstn.gov.in', 'Udyam — udyamregistration.gov.in', 'CBDT — incometax.gov.in', 'EPFO — epfindia.gov.in', 'MCA21 — mca.gov.in'].map(r => (
              <div key={r} style={{ color: '#4B5563', fontSize: 11, marginBottom: 5 }}>› {r}</div>
            ))}
          </div>
          <div>
            <div style={{ color: '#9CA3AF', fontWeight: 700, fontSize: 11, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.07em' }}>Compliance</div>
            {[['GIGW 3.0', 'Certified'], ['WCAG 2.1 AA', 'Accessible'], ['GFR Rule 173', 'Financial'], ['IT Act 2000', 'Cyber Law'], ['RTI Act 2005', 'Transparency'], ['DPDP Act 2023', 'Privacy'], ['PPP-MII 2020', 'Make-in-India']].map(([l, s]) => (
              <div key={l} style={{ display: 'flex', gap: 5, marginBottom: 4, alignItems: 'center' }}>
                <span style={{ color: '#22C55E', fontSize: 9, fontWeight: 700 }}>✓</span>
                <span style={{ color: '#6B7280', fontSize: 10 }}>{l} — {s}</span>
              </div>
            ))}
          </div>
          <div>
            <div style={{ color: '#9CA3AF', fontWeight: 700, fontSize: 11, marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.07em' }}>Security</div>
            {['SHA-256 Audit Chain', 'AES-256 Encryption', 'TLS 1.3 Transport', 'JWT Authentication', 'Rate Limiting Active', 'CORS Policy Enforced'].map(s => (
              <div key={s} style={{ display: 'flex', gap: 6, marginBottom: 4, alignItems: 'center' }}>
                <span style={{ color: '#3B82F6', fontSize: 9 }}>🔒</span>
                <span style={{ color: '#6B7280', fontSize: 10 }}>{s}</span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ borderTop: '1px solid #0A1A35', paddingTop: 14, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <div style={{ fontSize: 10, color: '#374151' }}>{t('footer_copy')}</div>
          <div style={{ fontSize: 10, color: '#374151' }}>{t('footer_contact')}</div>
        </div>
      </div>
    </footer>
  );
}

export default function LandingPage() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const lang = useSelector(selectLang);
  const t = useTranslation(lang);
  const [dark, setDark] = useState(() => localStorage.getItem('gg_theme') === 'dark');
  const [textScale, setTextScale] = useState(1);
  const [modal, setModal] = useState(null);
  const { data, loading } = useLiveMetrics();
  const fontSize = textScale === 0 ? 13 : textScale === 2 ? 17 : 15;
  const toggleDark = () => setDark(d => { const n = !d; localStorage.setItem('gg_theme', n ? 'dark' : 'light'); return n; });
  const changeLang = useCallback((code) => dispatch(setGlobalLang(code)), [dispatch]);
  function handleSuccess(res) {
    if (res.token) dispatch(loginSuccess({ token: res.token, role: res.role, name: res.name || res.user?.name, email: res.username, department: res.user?.department || '' }));
    navigate(res.role === 'BIDDER' ? '/my-bids' : '/dashboard', { replace: true });
  }
  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        html { scroll-behavior: smooth; }
        body { font-family: ${FONT}; }
        @keyframes rbpulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        :focus-visible { outline: 2px solid ${C.navy}; outline-offset: 2px; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
      `}</style>
      <div style={{ minHeight: '100vh', background: dark ? '#07090F' : '#FFF', color: dark ? '#F1F5F9' : C.gray900, fontFamily: FONT, fontSize, display: 'flex', flexDirection: 'column', transition: 'background 0.25s, color 0.25s' }}>
        <TopRibbon t={t} lang={lang} onLangChange={changeLang} dark={dark} onDarkToggle={toggleDark} textScale={textScale} onScaleChange={setTextScale} />
        <MainHeader t={t} dark={dark} onOfficer={() => setModal('OFFICER')} onBidder={() => setModal('BIDDER')} />
        <main id="main-content" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <HeroSection t={t} dark={dark} data={data} onOfficer={() => setModal('OFFICER')} onBidder={() => setModal('BIDDER')} />
          <MetricsSection t={t} dark={dark} data={data} loading={loading} />
          <FeaturesSection dark={dark} />
          <PipelineStrip dark={dark} />
        </main>
        <GovFooter t={t} />
        {modal && <PortalModal dark={dark} t={t} mode={modal} onClose={() => setModal(null)} onSuccess={handleSuccess} />}
      </div>
    </>
  );
}

