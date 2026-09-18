/**
 * GeM-Guard LandingPage v3 — Elite Government Portal
 * Features: Live API metrics, 8 Indian languages, Tricolor, Patriotic,
 *           Fluid glass-morphism animations, Elite modal w/ slider
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { loginSuccess } from '../store/slices/authSlice';
import { setLang as setGlobalLang, selectLang, LANG_NAMES } from '../store/slices/i18nSlice';
import { useTranslation } from '../i18n/translations';
import { login, registerBidder } from '../api/client';

// ── Design Constants ─────────────────────────────────────────────────────────
const GOV = {
  saffron: '#FF6600', saffronLight: '#FF9900',
  white: '#FFFFFF',
  green: '#138808', greenLight: '#16A34A',
  navy: '#003366', navyDark: '#001F4E',
  red: '#B91C1C', amber: '#B45309', blue: '#1D4ED8',
};

function theme(dark) {
  return {
    bg: dark ? '#07090F' : '#EEF1F6',
    card: dark ? '#111827' : '#FFFFFF',
    border: dark ? '#1F2937' : '#E5E9F0',
    header: dark ? '#0B0F19' : '#FFFFFF',
    inputBg: dark ? '#0F172A' : '#F8FAFC',
    inputBorder: dark ? '#1F2937' : '#D1D5DB',
    inputText: dark ? '#E5E7EB' : '#111827',
    text: dark ? '#F1F5F9' : '#0F172A',
    textSub: dark ? '#94A3B8' : '#374151',
    textMuted: dark ? '#4B5563' : '#9CA3AF',
    sectionBg: dark ? '#0B0F19' : '#F8FAFC',
    glass: dark ? 'rgba(17,24,39,0.85)' : 'rgba(255,255,255,0.92)',
    glassBorder: dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.08)',
  };
}

// ── Ashoka Emblem (SVG glow) ─────────────────────────────────────────────────
function AshokaEmblem({ size = 60, glow = false }) {
  return (
    <div style={{
      width: size, height: size + 14, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
      filter: glow
        ? 'drop-shadow(0 0 10px rgba(255,140,0,0.7)) drop-shadow(0 0 24px rgba(255,102,0,0.4)) drop-shadow(0 0 2px rgba(255,200,0,0.9))'
        : 'none',
      transition: 'filter 0.4s ease',
    }}>
      <svg viewBox="0 0 100 114" width={size} height={size + 14} xmlns="http://www.w3.org/2000/svg">
        {/* Base bar */}
        <rect x="18" y="93" width="64" height="6" rx="2" fill="#7C5A10" />
        <rect x="14" y="97" width="72" height="5" rx="1.5" fill="#9B7215" />
        {/* Wheel */}
        <circle cx="50" cy="72" r="13" fill="none" stroke={GOV.navy} strokeWidth="2.5" />
        <circle cx="50" cy="72" r="3.5" fill={GOV.navy} />
        {Array.from({length:24},(_,i)=>{
          const a=(i*15)*Math.PI/180;
          return <line key={i} x1={50+3.5*Math.cos(a)} y1={72+3.5*Math.sin(a)} x2={50+12*Math.cos(a)} y2={72+12*Math.sin(a)} stroke={GOV.navy} strokeWidth="0.9" />;
        })}
        {/* Left lion body */}
        <ellipse cx="36" cy="60" rx="11" ry="9" fill="#C8940A" />
        <circle cx="33" cy="49" r="8" fill="#C8940A" />
        <circle cx="33" cy="47" r="10" fill="none" stroke="#8B6000" strokeWidth="2.8" />
        <circle cx="31" cy="47" r="1.8" fill="#2A1200" />
        <path d="M30 52 Q33 55 36 52" stroke="#8B6000" strokeWidth="1" fill="none" />
        {/* Right lion body */}
        <ellipse cx="64" cy="60" rx="11" ry="9" fill="#C8940A" />
        <circle cx="67" cy="49" r="8" fill="#C8940A" />
        <circle cx="67" cy="47" r="10" fill="none" stroke="#8B6000" strokeWidth="2.8" />
        <circle cx="69" cy="47" r="1.8" fill="#2A1200" />
        <path d="M70 52 Q67 55 64 52" stroke="#8B6000" strokeWidth="1" fill="none" />
        {/* Tails */}
        <path d="M25 60 Q20 52 24 44" stroke="#C8940A" strokeWidth="2.5" fill="none" strokeLinecap="round" />
        <path d="M75 60 Q80 52 76 44" stroke="#C8940A" strokeWidth="2.5" fill="none" strokeLinecap="round" />
        {/* Satyameva Jayate */}
        <text x="50" y="112" textAnchor="middle" fontSize="6" fill="#111827" fontFamily="serif" fontWeight="700" letterSpacing="0.5">सत्यमेव जयते</text>
      </svg>
    </div>
  );
}

// ── Tricolor ─────────────────────────────────────────────────────────────────
function Tricolor({ h = 3 }) {
  return <div style={{ display: 'flex', height: h }}><div style={{ flex:1, background:GOV.saffron }} /><div style={{ flex:1, background:GOV.white, borderTop:`0.5px solid #e5e7eb`, borderBottom:`0.5px solid #e5e7eb` }} /><div style={{ flex:1, background:GOV.green }} /></div>;
}

// ── Live Metrics Hook ─────────────────────────────────────────────────────────
function useLiveMetrics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const token = localStorage.getItem('rashtrabid_token') || localStorage.getItem('gemguard_token') || localStorage.getItem('token') || '';
      const headers = token ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };

      const [bRes, tRes] = await Promise.allSettled([
        fetch('/api/v1/bids', { headers }).then(r => r.ok ? r.json() : Promise.reject()),
        fetch('/api/v1/tenders', { headers }).then(r => r.ok ? r.json() : Promise.reject()),
      ]);

      const bids = bRes.status === 'fulfilled'
        ? (Array.isArray(bRes.value) ? bRes.value : (bRes.value?.bids ?? bRes.value?.items ?? []))
        : [];

      const tenders = tRes.status === 'fulfilled'
        ? (Array.isArray(tRes.value) ? tRes.value : (tRes.value?.tenders ?? tRes.value?.items ?? []))
        : [];

      const total = bids.length;
      const approved = bids.filter(b => ['APPROVED','PASS','COMPLIANT'].includes(b.overall_status ?? b.compliance_status ?? b.status ?? '')).length;
      const pending = bids.filter(b => ['PENDING','PENDING_VERIFICATION','UNDER_REVIEW','IN_PROGRESS'].includes(b.overall_status ?? b.compliance_status ?? b.status ?? '')).length;
      const flagged = bids.filter(b => ['FAIL','NON_COMPLIANT','REVIEW','FLAGGED','REJECTED'].includes(b.overall_status ?? b.compliance_status ?? b.status ?? '')).length;
      const score = total > 0 ? (Math.round((approved / total) * 1000) / 10) : 0;
      const activeTenders = tenders.filter(t => ['ACTIVE','PUBLISHED','OPEN'].includes((t.status ?? 'ACTIVE').toUpperCase())).length || tenders.length;

      setData({ total, approved, pending, flagged, score, activeTenders, tenders, bids });
    } catch {
      setData({ total: 0, approved: 0, pending: 0, flagged: 0, score: 0, activeTenders: 0, tenders: [], bids: [] });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 30000); // refresh every 30s
    return () => clearInterval(id);
  }, [fetchData]);

  return { data, loading };
}

// ── Top Ribbon ────────────────────────────────────────────────────────────────
function TopRibbon({ t, lang, onLangChange, dark, onDarkToggle, textScale, onScaleChange }) {
  const langList = Object.entries(LANG_NAMES);
  const [showLangs, setShowLangs] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function click(e) { if (ref.current && !ref.current.contains(e.target)) setShowLangs(false); }
    document.addEventListener('mousedown', click);
    return () => document.removeEventListener('mousedown', click);
  }, []);

  return (
    <div style={{ background:'#0B0F19', position:'sticky', top:0, zIndex:1000, width:'100%', maxWidth:'100vw', boxSizing:'border-box' }}>
      <Tricolor h={2.5} />
      <div style={{ maxWidth:1400, margin:'0 auto', padding:'5px 12px', display:'flex', justifyContent:'space-between', alignItems:'center', gap:8, flexWrap:'wrap' }}>
        <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
          <span style={{ fontSize:10, fontWeight:700, color:'#F8FAFC', letterSpacing:'0.04em' }}>{t('ribbon_gov')}</span>
          <div style={{ width:1, height:12, background:'#1F2937' }} />
          <span style={{ fontSize:9, color:'#6B7280' }}>{t('ribbon_portal')}</span>
          <div style={{ width:1, height:12, background:'#1F2937' }} />
          <span style={{ fontSize:9, padding:'1px 6px', borderRadius:20, background:'rgba(19,136,8,0.18)', color:'#4ADE80', border:'1px solid rgba(19,136,8,0.35)', fontWeight:700, letterSpacing:'0.06em', display:'flex', alignItems:'center', gap:4 }}>
            <span style={{ width:5, height:5, borderRadius:'50%', background:'#4ADE80', display:'inline-block', animation:'ggpulse 1.8s infinite' }} />
            LIVE
          </span>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:6, flexWrap:'wrap' }}>
          {/* Text size */}
          <div style={{ display:'flex', gap:1, background:'#1F2937', borderRadius:4, padding:'2px 3px' }}>
            {['−','','+'].map((s,i) => (
              <button key={i} onClick={() => onScaleChange(i)} aria-pressed={textScale===i}
                style={{ background:textScale===i?GOV.navy:'transparent', border:'none', color:textScale===i?'#FFF':'#6B7280', cursor:'pointer', padding:'2px 5px', borderRadius:3, fontSize:i===0?9:i===1?10:12, fontWeight:800, lineHeight:1 }}>
                {i===0?'A-':i===1?'A':'A+'}
              </button>
            ))}
          </div>
          <button onClick={onDarkToggle} aria-pressed={dark}
            style={{ display:'flex', alignItems:'center', gap:3, background:dark?'rgba(59,130,246,0.15)':'#1F2937', border:`1px solid ${dark?'rgba(59,130,246,0.4)':'#374151'}`, color:dark?'#93C5FD':'#9CA3AF', cursor:'pointer', padding:'3px 7px', borderRadius:4, fontSize:9, fontWeight:700 }}>
            {dark ? '☀' : '◑'}
          </button>
          {/* Language picker */}
          <div ref={ref} style={{ position:'relative' }}>
            <button onClick={() => setShowLangs(v => !v)}
              style={{ display:'flex', alignItems:'center', gap:4, background:'#1F2937', border:'1px solid #374151', color:'#9CA3AF', cursor:'pointer', padding:'3px 8px', borderRadius:4, fontSize:10, fontWeight:700 }}>
              🌐 {LANG_NAMES[lang]} <span style={{ fontSize:8 }}>{showLangs?'▲':'▼'}</span>
            </button>
            {showLangs && (
              <div style={{ position:'absolute', top:'calc(100% + 6px)', right:0, background:'#111827', border:'1px solid #1F2937', borderRadius:8, overflow:'hidden', boxShadow:'0 8px 32px rgba(0,0,0,0.5)', zIndex:1500, minWidth:160 }}>
                {langList.map(([code, name]) => (
                  <button key={code} onClick={() => { onLangChange(code); setShowLangs(false); }}
                    style={{ display:'block', width:'100%', padding:'8px 14px', border:'none', background:lang===code?'rgba(0,51,102,0.4)':'transparent', color:lang===code?'#93C5FD':'#D1D5DB', cursor:'pointer', fontSize:12, textAlign:'left', fontWeight:lang===code?700:400, borderLeft:lang===code?`3px solid ${GOV.navy}`:'3px solid transparent' }}>
                    {name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main Header ───────────────────────────────────────────────────────────────
function MainHeader({ t, tk, onOfficer, onBidder }) {
  const [srch, setSrch] = useState('');
  return (
    <header style={{ background:tk.header, borderBottom:`1px solid ${tk.border}`, boxShadow:'0 2px 12px rgba(0,0,0,0.07)', width:'100%', maxWidth:'100vw', boxSizing:'border-box' }}>
      <div style={{ maxWidth:1400, margin:'0 auto', padding:'10px 14px', display:'flex', alignItems:'center', gap:12, flexWrap:'wrap', justifyContent:'space-between' }}>
        {/* Brand */}
        <div style={{ display:'flex', alignItems:'center', gap:10, flexShrink:0 }}>
          <AshokaEmblem size={44} glow />
          <div>
            <div style={{ display:'flex', alignItems:'center', gap:6 }}>
              <span style={{ fontSize:18, fontWeight:900, letterSpacing:'-0.5px', background:`linear-gradient(135deg, ${GOV.navyDark}, ${GOV.navy} 60%, #1a5276)`, WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent', backgroundClip:'text' }}>{t('app_name')}</span>
              <span style={{ fontSize:8, fontWeight:800, padding:'2px 6px', borderRadius:3, background:`linear-gradient(90deg, ${GOV.saffron}, ${GOV.saffronLight})`, color:'#FFF', letterSpacing:'0.08em', boxShadow:`0 2px 6px rgba(255,102,0,0.4)` }}>GEM VERIFICATION</span>
            </div>
            <div style={{ fontSize:10, color:tk.textSub, marginTop:1 }}>{t('app_subtitle')}</div>
          </div>
        </div>

        {/* Portal Action Buttons */}
        <div style={{ display:'flex', gap:8, alignItems:'center', flexWrap:'wrap' }}>
          <button id="btn-bidder-portal" onClick={onBidder}
            style={{ padding:'7px 14px', borderRadius:6, border:`1.5px solid ${GOV.greenLight}`, background:'transparent', color:GOV.greenLight, fontWeight:700, fontSize:12, cursor:'pointer', display:'flex', alignItems:'center', gap:5, transition:'all 0.2s', flexShrink:0 }}
            onMouseEnter={e=>{e.currentTarget.style.background=GOV.greenLight;e.currentTarget.style.color='#FFF';}}
            onMouseLeave={e=>{e.currentTarget.style.background='transparent';e.currentTarget.style.color=GOV.greenLight;}}>
            👤 {t('btn_bidder')}
          </button>
          <button id="btn-officer-login" onClick={onOfficer}
            style={{ padding:'7px 16px', borderRadius:6, border:`1.5px solid ${GOV.navy}`, background:GOV.navy, color:'#FFF', fontWeight:700, fontSize:12, cursor:'pointer', display:'flex', alignItems:'center', gap:5, transition:'all 0.2s', boxShadow:`0 2px 8px rgba(0,51,102,0.35)`, flexShrink:0 }}
            onMouseEnter={e=>{e.currentTarget.style.background=GOV.navyDark;e.currentTarget.style.boxShadow=`0 4px 16px rgba(0,51,102,0.55)`;}}
            onMouseLeave={e=>{e.currentTarget.style.background=GOV.navy;e.currentTarget.style.boxShadow=`0 2px 8px rgba(0,51,102,0.35)`;}}>
            🔐 {t('btn_officer')}
          </button>
        </div>
      </div>
    </header>
  );
}

// ── Hero Section ──────────────────────────────────────────────────────────────
function HeroSection({ t, tk, data, onOfficer, onBidder }) {
  const activeTender = data?.tenders?.[0];
  const [sloganIdx, setSloganIdx] = useState(0);
  const slogans = ['slogan1','slogan2','slogan3'];

  useEffect(() => {
    const id = setInterval(() => setSloganIdx(i => (i+1) % 3), 4000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ background:tk.header, borderBottom:`1px solid ${tk.border}`, width:'100%', maxWidth:'100vw', boxSizing:'border-box' }}>
      <div style={{ maxWidth:1400, margin:'0 auto', padding:'20px 14px', display:'flex', gap:18, flexWrap:'wrap', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div style={{ flex:'1 1 300px', minWidth:0, maxWidth:'100%' }}>
          {/* Live badge */}
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10, flexWrap:'wrap' }}>
            <span style={{ display:'inline-flex', alignItems:'center', gap:5, fontSize:10, fontWeight:800, padding:'3px 10px', borderRadius:20, background:'rgba(19,136,8,0.1)', color:GOV.green, border:`1px solid rgba(19,136,8,0.25)`, letterSpacing:'0.06em' }}>
              <span style={{ width:6, height:6, borderRadius:'50%', background:GOV.green, display:'inline-block', boxShadow:`0 0 5px ${GOV.green}`, animation:'ggpulse 2s infinite' }} />
              {t('live_badge')}
            </span>
            {activeTender && (
              <span style={{ fontSize:10, color:tk.textMuted, fontStyle:'italic' }}>
                {activeTender.title?.substring(0,36)}...
              </span>
            )}
          </div>

          {/* Rotating slogan */}
          <div style={{ fontSize:12, color:GOV.saffron, fontWeight:700, letterSpacing:'0.04em', marginBottom:8, height:20, overflow:'hidden', position:'relative' }}>
            {slogans.map((s,i) => (
              <div key={s} style={{ position:'absolute', transition:'all 0.6s cubic-bezier(0.4,0,0.2,1)', opacity:i===sloganIdx?1:0, transform:`translateY(${i===sloganIdx?0:i<sloganIdx?'-100%':'100%'})`, width:'100%' }}>
                {t(s)}
              </div>
            ))}
          </div>

          <h1 style={{ margin:'0 0 10px', fontSize:22, fontWeight:800, color:tk.text, lineHeight:1.3, letterSpacing:'-0.3px' }}>
            {t('hero_title')}
          </h1>
          <p style={{ margin:'0 0 18px', fontSize:13, color:tk.textSub, lineHeight:1.7, maxWidth:560 }}>{t('hero_sub')}</p>

          {/* Portal CTAs */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(220px, 1fr))', gap:12, maxWidth:560, marginBottom:12 }}>
            {/* Bidder */}
            <div onClick={onBidder} style={{ background:`linear-gradient(135deg, #0D6E08, ${GOV.green})`, borderRadius:10, padding:'14px 16px', cursor:'pointer', position:'relative', overflow:'hidden', boxShadow:'0 6px 20px rgba(19,136,8,0.28)', transition:'transform 0.2s, box-shadow 0.2s' }}
              onMouseEnter={e=>{e.currentTarget.style.transform='translateY(-2px)';e.currentTarget.style.boxShadow='0 10px 30px rgba(19,136,8,0.38)';}}
              onMouseLeave={e=>{e.currentTarget.style.transform='none';e.currentTarget.style.boxShadow='0 6px 20px rgba(19,136,8,0.28)';}}>
              <div style={{ position:'absolute', right:-12, bottom:-12, width:70, height:70, borderRadius:'50%', background:'rgba(255,255,255,0.07)' }} />
              <div style={{ position:'absolute', right:14, top:'50%', transform:'translateY(-50%)', color:'rgba(255,255,255,0.5)', fontSize:18 }}>›</div>
              <div style={{ display:'flex', alignItems:'center', gap:9, marginBottom:6 }}>
                <div style={{ width:34, height:34, borderRadius:8, background:'rgba(255,255,255,0.15)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:17 }}>👤</div>
                <div>
                  <div style={{ fontSize:13, fontWeight:800, color:'#FFF' }}>{t('portal_bidder_title')}</div>
                  <span style={{ fontSize:9, padding:'1px 6px', borderRadius:20, background:'rgba(255,255,255,0.2)', color:'#FFF', fontWeight:800, letterSpacing:'0.07em' }}>{t('portal_bidder_tag')}</span>
                </div>
              </div>
              <p style={{ margin:0, fontSize:11, color:'rgba(255,255,255,0.8)', lineHeight:1.5 }}>{t('portal_bidder_sub')}</p>
            </div>

            {/* Officer */}
            <div onClick={onOfficer} style={{ background:`linear-gradient(135deg, ${GOV.navyDark}, ${GOV.navy})`, borderRadius:10, padding:'14px 16px', cursor:'pointer', position:'relative', overflow:'hidden', boxShadow:'0 6px 20px rgba(0,51,102,0.35)', transition:'transform 0.2s, box-shadow 0.2s' }}
              onMouseEnter={e=>{e.currentTarget.style.transform='translateY(-2px)';e.currentTarget.style.boxShadow='0 10px 30px rgba(0,51,102,0.48)';}}
              onMouseLeave={e=>{e.currentTarget.style.transform='none';e.currentTarget.style.boxShadow='0 6px 20px rgba(0,51,102,0.35)';}}>
              <div style={{ position:'absolute', right:-12, bottom:-12, width:70, height:70, borderRadius:'50%', background:'rgba(255,255,255,0.05)' }} />
              <div style={{ position:'absolute', right:14, top:'50%', transform:'translateY(-50%)', color:'rgba(255,255,255,0.4)', fontSize:18 }}>›</div>
              <div style={{ display:'flex', alignItems:'center', gap:9, marginBottom:6 }}>
                <div style={{ width:34, height:34, borderRadius:8, background:'rgba(255,255,255,0.12)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:17 }}>🔐</div>
                <div>
                  <div style={{ fontSize:13, fontWeight:800, color:'#FFF' }}>{t('portal_officer_title')}</div>
                  <span style={{ fontSize:9, padding:'1px 6px', borderRadius:20, background:'rgba(255,166,0,0.28)', color:'#FCD34D', fontWeight:800, letterSpacing:'0.07em' }}>{t('portal_officer_tag')}</span>
                </div>
              </div>
              <p style={{ margin:0, fontSize:11, color:'rgba(255,255,255,0.6)', lineHeight:1.5 }}>{t('portal_officer_sub')}</p>
            </div>
          </div>
        </div>

        {/* Right side panel - standards and registry */}
        <div style={{ display:'flex', flexDirection:'column', gap:10, flex:'1 1 200px', maxWidth:280, minWidth:0 }}>
          <div style={{ background:tk.sectionBg, border:`1px solid ${tk.border}`, borderRadius:10, padding:'12px 15px' }}>
            <div style={{ fontSize:9, color:tk.textMuted, fontWeight:700, textTransform:'uppercase', letterSpacing:'0.07em' }}>{t('compliance_label')}</div>
            <div style={{ fontSize:13, fontWeight:800, color:GOV.navy, marginTop:4, lineHeight:1.3 }}>{t('compliance_std')}</div>
            <div style={{ marginTop:8, display:'flex', flexDirection:'column', gap:4 }}>
              {['GIGW 3.0','WCAG 2.1 AA','GFR Rule 173','RTI Act 2005'].map(b => (
                <div key={b} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:5 }}>
                  <span style={{ fontSize:10, color:tk.textSub }}>{b}</span>
                  <div style={{ width:16, height:16, borderRadius:'50%', background:'#DCFCE7', border:'1px solid #86EFAC', display:'flex', alignItems:'center', justifyContent:'center', fontSize:8, color:GOV.green, fontWeight:900 }}>✓</div>
                </div>
              ))}
            </div>
          </div>
          {/* Registry sync */}
          <div style={{ background:tk.card, border:`1px solid ${tk.border}`, borderRadius:8, padding:'9px 14px' }}>
            <div style={{ fontSize:9, color:tk.textMuted, fontWeight:700, letterSpacing:'0.06em', marginBottom:5 }}>REGISTRY SYNC STATUS</div>
            {[['GSTN','#4ADE80'],['UDYAM','#4ADE80'],['CBDT-PAN','#4ADE80'],['EPFO','#FBBF24']].map(([r,c]) => (
              <div key={r} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:6, marginBottom:3 }}>
                <span style={{ fontSize:10, color:tk.textSub, fontFamily:'monospace' }}>{r}</span>
                <span style={{ width:7, height:7, borderRadius:'50%', background:c, boxShadow:`0 0 6px ${c}`, display:'inline-block' }} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Live Metrics ──────────────────────────────────────────────────────────────
function LiveMetrics({ t, tk, data, loading }) {
  const cards = data ? [
    { icon:'✓', val: data.total, lbl:t('metric_total'), sub:`${data.approved} cleared`, status:t('status_verified'), sc:GOV.green, sb:'#F0FDF4', sbr:'#BBF7D0', top:GOV.green },
    { icon:'🏛', val: data.activeTenders, lbl:t('metric_tenders'), sub:'Government e-Marketplace', status:t('status_live'), sc:GOV.blue, sb:'#EFF6FF', sbr:'#BFDBFE', top:GOV.blue },
    { icon:'✓', val: data.approved, lbl:t('metric_approved'), sub:'Final officer decision', status:t('status_good'), sc:'#059669', sb:'#ECFDF5', sbr:'#6EE7B7', top:'#059669' },
    { icon:'⏱', val: data.pending, lbl:t('metric_pending'), sub:'Awaiting registry check', status:t('status_progress'), sc:GOV.amber, sb:'#FFFBEB', sbr:'#FDE68A', top:GOV.amber },
    { icon:'▲', val: data.flagged, lbl:t('metric_flagged'), sub:'Mandatory scrutiny', status:t('status_attention'), sc:GOV.red, sb:'#FEF2F2', sbr:'#FECACA', top:GOV.red },
    { icon:'🏆', val: data.score>0?`${data.score}%`:'--', lbl:t('metric_score'), sub:'Benchmark: ≥ 80.0%', status:t('status_good'), sc:GOV.navy, sb:'#EFF6FF', sbr:'#BFDBFE', top:GOV.navy },
  ] : [];

  return (
    <div style={{ maxWidth:1400, margin:'0 auto', padding:'20px 18px 0' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
        <h2 style={{ margin:0, fontSize:15, fontWeight:800, color:tk.text }}>{t('metrics_heading')}</h2>
        <span style={{ fontSize:9, color:tk.textMuted, fontFamily:'monospace' }}>AUTO-REFRESH 30s</span>
      </div>
      {loading ? (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(160px,1fr))', gap:12 }}>
          {Array.from({length:6}).map((_,i) => (
            <div key={i} style={{ background:tk.card, border:`1px solid ${tk.border}`, borderRadius:8, height:100, animation:'ggpulse 1.5s infinite' }} />
          ))}
        </div>
      ) : (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(160px,1fr))', gap:12 }}>
          {cards.map((c,i) => (
            <div key={i} style={{ background:tk.card, border:`1px solid ${tk.border}`, borderRadius:8, padding:'14px 15px', borderTop:`3px solid ${c.top}`, boxShadow:'0 1px 4px rgba(0,0,0,0.05)', transition:'box-shadow 0.2s, transform 0.2s' }}
              onMouseEnter={e=>{e.currentTarget.style.boxShadow='0 4px 16px rgba(0,0,0,0.09)';e.currentTarget.style.transform='translateY(-1px)';}}
              onMouseLeave={e=>{e.currentTarget.style.boxShadow='0 1px 4px rgba(0,0,0,0.05)';e.currentTarget.style.transform='none';}}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:8 }}>
                <div style={{ width:32, height:32, borderRadius:7, background:c.sb, border:`1px solid ${c.sbr}`, display:'flex', alignItems:'center', justifyContent:'center', fontSize:14, color:c.sc, fontWeight:800 }}>{c.icon}</div>
                <span style={{ fontSize:9, fontWeight:800, padding:'2px 7px', borderRadius:20, background:c.sb, color:c.sc, border:`1px solid ${c.sbr}` }}>{c.status}</span>
              </div>
              <div style={{ fontSize:27, fontWeight:800, color:tk.text, lineHeight:1, letterSpacing:'-0.5px' }}>{c.val}</div>
              <div style={{ fontSize:11, color:tk.textSub, fontWeight:600, marginTop:3 }}>{c.lbl}</div>
              <div style={{ fontSize:10, color:tk.textMuted, marginTop:4 }}>{c.sub}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Statutory Categories ──────────────────────────────────────────────────────
const CAT_DATA = [
  { ik:'cat_udyam', icon:'🏭', reg:'MoMSME — Udyam Portal', detail:'Enterprise category, NIC classification, Udyam certificate validity & active status', color:'#7C3AED' },
  { ik:'cat_gst', icon:'🏛️', reg:'GSTN — Goods & Services Tax Network', detail:'GSTIN active status, state code match, registration date vs tender eligibility period', color:'#0891B2' },
  { ik:'cat_pan', icon:'🪪', reg:'CBDT — Income Tax Dept, MoF', detail:'PAN validity, UDIN cross-check for CA-certified 3yr turnover, name consistency', color:'#D97706' },
  { ik:'cat_epfo', icon:'👷', reg:'EPFO — Ministry of Labour', detail:'Establishment code, ECR filing compliance, ESIC registration for manpower bids', color:'#DC2626' },
  { ik:'cat_oem', icon:'🔑', reg:'OEM Self-Decl. + CA Attestation', detail:'Authorization letter validity, authorized dealer scope, MII affidavit cross-reference', color:'#059669' },
  { ik:'cat_mii', icon:'🇮🇳', reg:'DPIIT — PPP-MII Order 2020', detail:'Local content ≥ 50%, Class-I/II preference eligibility, DPIIT category verification', color:GOV.green },
];

function StatutoryCategories({ t, tk }) {
  return (
    <div style={{ background:tk.sectionBg, borderTop:`1px solid ${tk.border}`, borderBottom:`1px solid ${tk.border}` }}>
      <div style={{ maxWidth:1400, margin:'0 auto', padding:'24px 18px' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16, flexWrap:'wrap', gap:8 }}>
          <div>
            <h2 style={{ margin:0, fontSize:15, fontWeight:800, color:tk.text }}>{t('cat_heading')}</h2>
            <p style={{ margin:'3px 0 0', fontSize:12, color:tk.textSub }}>{t('cat_sub')}</p>
          </div>
          <span style={{ fontSize:10, fontWeight:800, padding:'4px 12px', borderRadius:20, background:tk.card, border:`1px solid ${tk.border}`, color:GOV.navy }}>{t('cat_core')}</span>
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(270px,1fr))', gap:12 }}>
          {CAT_DATA.map((c,i) => (
            <div key={i} style={{ background:tk.card, border:`1px solid ${tk.border}`, borderRadius:8, padding:'14px 16px', borderLeft:`3px solid ${c.color}`, transition:'all 0.2s', cursor:'default' }}
              onMouseEnter={e=>{e.currentTarget.style.boxShadow='0 4px 16px rgba(0,0,0,0.1)';e.currentTarget.style.transform='translateY(-1px)';}}
              onMouseLeave={e=>{e.currentTarget.style.boxShadow='none';e.currentTarget.style.transform='none';}}>
              <div style={{ display:'flex', alignItems:'center', gap:9, marginBottom:8 }}>
                <div style={{ width:34, height:34, borderRadius:7, background:`${c.color}14`, border:`1px solid ${c.color}28`, display:'flex', alignItems:'center', justifyContent:'center', fontSize:17, flexShrink:0 }}>{c.icon}</div>
                <div>
                  <div style={{ fontSize:12, fontWeight:800, color:tk.text }}>{t(c.ik)}</div>
                  <div style={{ fontSize:9, color:tk.textMuted, marginTop:1 }}>{c.reg}</div>
                </div>
              </div>
              <div style={{ fontSize:11, color:tk.textSub, lineHeight:1.65 }}>{c.detail}</div>
              <div style={{ marginTop:8, display:'flex', gap:5 }}>
                <span style={{ fontSize:9, fontWeight:700, padding:'2px 8px', borderRadius:20, background:'rgba(19,136,8,0.08)', color:GOV.green, border:'1px solid rgba(19,136,8,0.2)' }}>● LIVE</span>
                <span style={{ fontSize:9, fontWeight:700, padding:'2px 8px', borderRadius:20, background:tk.sectionBg, color:GOV.navy, border:`1px solid ${tk.border}` }}>AI Evaluated</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Pipeline Strip ────────────────────────────────────────────────────────────
function PipelineStrip({ tk }) {
  const steps = [['📋','RFP Intelligence','PyMuPDF'],['👁️','Vision OCR','LayoutLM'],['🔗','6-Registry Check','GSTN·PAN·EPFO'],['⚖️','Rules Engine','Zero Hallucination'],['🛡️','SHA-256 Audit','Immutable Ledger']];
  return (
    <div style={{ maxWidth:1400, margin:'0 auto', padding:'16px 14px', width:'100%', maxWidth:'100vw', boxSizing:'border-box' }}>
      <div style={{ background:tk.card, border:`1px solid ${tk.border}`, borderRadius:8, padding:'12px 14px', overflowX:'auto', WebkitOverflowScrolling:'touch', width:'100%', boxSizing:'border-box' }}>
        <div style={{ display:'flex', alignItems:'center', gap:8, minWidth:'max-content' }}>
          {steps.map(([icon,title,sub],i) => (
            <div key={i} style={{ display:'flex', alignItems:'center', gap:8 }}>
              <div style={{ display:'flex', alignItems:'center', gap:7, background:tk.sectionBg, border:`1px solid ${tk.border}`, borderRadius:7, padding:'7px 13px' }}>
                <div style={{ width:22, height:22, borderRadius:'50%', background:GOV.navy, color:'#FFF', fontSize:10, display:'flex', alignItems:'center', justifyContent:'center', fontWeight:800, flexShrink:0 }}>{i+1}</div>
                <div>
                  <div style={{ fontSize:11, fontWeight:700, color:tk.text }}>{icon} {title}</div>
                  <div style={{ fontSize:9, color:tk.textMuted, fontFamily:'monospace' }}>{sub}</div>
                </div>
              </div>
              {i < steps.length-1 && <span style={{ color:tk.textMuted, fontSize:18, flexShrink:0 }}>→</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Elite Portal Modal (Glass + Slider Animation) ─────────────────────────────
function PortalModal({ tk, t, mode, onClose, onSuccess }) {
  const [tab, setTab] = useState(mode === 'BIDDER' ? 1 : 0);
  const [anim, setAnim] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [regUsername, setRegUsername] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regName, setRegName] = useState('');
  const [company, setCompany] = useState('');
  const [gstin, setGstin] = useState('');
  const [pan, setPan] = useState('');
  const [category, setCategory] = useState('MSME');
  const [turnover, setTurnover] = useState('14.2');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => { requestAnimationFrame(() => setVisible(true)); }, []);

  function switchTab(i) {
    setAnim(true);
    setTimeout(() => { setTab(i); setError(null); setAnim(false); }, 220);
  }

  function closeModal() {
    setVisible(false);
    setTimeout(onClose, 320);
  }

  async function doLogin(e) {
    e.preventDefault(); setError(null); setLoading(true);
    try { const r = await login(username.trim(), password); onSuccess(r); }
    catch (e2) { setError(e2.message || 'Login failed'); }
    finally { setLoading(false); }
  }
  async function doRegister(e) {
    e.preventDefault(); setError(null); setLoading(true);
    try {
      await registerBidder({ username:regUsername.trim(), password:regPassword, name:regName.trim(), company_name:company.trim(), gstin:gstin.toUpperCase(), pan:pan.toUpperCase(), category, state:'Tamil Nadu', turnover_cr:parseFloat(turnover)||0 });
      onSuccess({ role:'BIDDER' });
    } catch(e2) { setError(e2.message||'Registration failed'); }
    finally { setLoading(false); }
  }

  const inp = { width:'100%', padding:'10px 12px', borderRadius:7, fontSize:13, background:tk.inputBg, border:`1.5px solid ${tk.inputBorder}`, color:tk.inputText, outline:'none', boxSizing:'border-box', fontFamily:'inherit', transition:'border-color 0.2s' };
  const lbl = { display:'block', fontSize:10, fontWeight:700, color:tk.textSub, marginBottom:5, textTransform:'uppercase', letterSpacing:'0.07em' };

  return (
    <div style={{ position:'fixed', inset:0, zIndex:3000, display:'flex', alignItems:'center', justifyContent:'center', padding:12,
      background: visible ? 'rgba(0,0,0,0.65)' : 'rgba(0,0,0,0)',
      backdropFilter: visible ? 'blur(8px) saturate(180%)' : 'none',
      transition:'all 0.32s cubic-bezier(0.4,0,0.2,1)',
    }} onClick={e => e.target===e.currentTarget && closeModal()}>
      <div style={{
        background: tk.glass,
        backdropFilter: 'blur(20px) saturate(200%)',
        border: `1px solid ${tk.glassBorder}`,
        borderRadius:16, width:tab===1?560:440, maxWidth:'100%',
        maxHeight:'92vh', overflowY:'auto',
        boxShadow:'0 32px 80px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.05)',
        transform: visible ? 'translateY(0) scale(1)' : 'translateY(30px) scale(0.96)',
        transition:'transform 0.35s cubic-bezier(0.34,1.56,0.64,1), width 0.3s ease',
      }}>
        <Tricolor h={3} />
        {/* Header */}
        <div style={{ background:`linear-gradient(135deg, ${GOV.navyDark}, ${GOV.navy})`, padding:'14px 18px', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <AshokaEmblem size={30} glow={false} />
            <div>
              <div style={{ color:'#FFF', fontSize:13, fontWeight:800 }}>{tab===0?t('login_title'):t('register_tab')}</div>
              <div style={{ color:'rgba(255,255,255,0.5)', fontSize:10, marginTop:1 }}>{t('login_subtitle')}</div>
            </div>
          </div>
          <button onClick={closeModal} aria-label="Close"
            style={{ background:'rgba(255,255,255,0.1)', border:'none', color:'#FFF', width:28, height:28, borderRadius:8, cursor:'pointer', fontSize:18, display:'flex', alignItems:'center', justifyContent:'center', transition:'background 0.2s' }}
            onMouseEnter={e=>e.currentTarget.style.background='rgba(255,255,255,0.2)'}
            onMouseLeave={e=>e.currentTarget.style.background='rgba(255,255,255,0.1)'}>
            ×
          </button>
        </div>
        {/* Tab slider */}
        <div style={{ display:'flex', background:tk.sectionBg, borderBottom:`1px solid ${tk.border}`, position:'relative' }}>
          {[t('login_tab'), t('register_tab')].map((label,i) => (
            <button key={i} onClick={() => switchTab(i)}
              style={{ flex:1, padding:'11px 14px', border:'none', cursor:'pointer', fontSize:12, fontWeight:700, background:'transparent', color:tab===i?GOV.navy:tk.textMuted, transition:'color 0.2s', position:'relative', zIndex:1 }}>
              {label}
            </button>
          ))}
          {/* Sliding indicator */}
          <div style={{ position:'absolute', bottom:0, left:`${tab*50}%`, width:'50%', height:2.5, background:GOV.navy, borderRadius:'2px 2px 0 0', transition:'left 0.25s cubic-bezier(0.4,0,0.2,1)' }} />
        </div>
        {/* Body with slide animation */}
        <div style={{ overflow:'hidden' }}>
          <div style={{ display:'flex', transform:`translateX(${-tab*100}%)`, transition:anim?'none':'transform 0.28s cubic-bezier(0.4,0,0.2,1)' }}>
            {/* LOGIN PANEL */}
            <div style={{ minWidth:'100%', padding:'18px', boxSizing:'border-box' }}>
              {error && <div role="alert" style={{ background:'#FEF2F2', border:'1px solid #FECACA', borderRadius:7, padding:'10px 14px', marginBottom:14, color:GOV.red, fontSize:12, fontWeight:600 }}>⚠️ {error}</div>}
              <form onSubmit={doLogin} noValidate>
                <div style={{ marginBottom:13 }}>
                  <label htmlFor="m-login-user" style={lbl}>{t('field_username')}</label>
                  <input id="m-login-user" type="text" required autoFocus={tab===0} placeholder="officer@gem.gov.in" value={username} onChange={e=>setUsername(e.target.value)} style={inp}
                    onFocus={e=>e.target.style.borderColor=GOV.navy} onBlur={e=>e.target.style.borderColor=tk.inputBorder} />
                </div>
                <div style={{ marginBottom:16 }}>
                  <label htmlFor="m-login-pass" style={lbl}>{t('field_password')}</label>
                  <input id="m-login-pass" type="password" required placeholder="••••••••" value={password} onChange={e=>setPassword(e.target.value)} style={inp}
                    onFocus={e=>e.target.style.borderColor=GOV.navy} onBlur={e=>e.target.style.borderColor=tk.inputBorder} />
                </div>
                {/* Demo credentials box */}
                <div style={{ background:'linear-gradient(135deg, #EFF6FF, #DBEAFE)', border:'1px solid #93C5FD', borderRadius:8, padding:'10px 14px', marginBottom:16 }}>
                  <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:4, flexWrap:'wrap', gap:6 }}>
                    <div style={{ fontSize:10, fontWeight:800, color:GOV.blue, letterSpacing:'0.04em' }}>🎯 DEMO CREDENTIALS</div>
                    <button
                      type="button"
                      id="demo-autofill-btn"
                      onClick={() => { setUsername('officer@gem.gov.in'); setPassword('Admin@123'); }}
                      style={{ background:GOV.navy, color:'#FFF', border:'none', borderRadius:4, padding:'2px 8px', fontSize:10, fontWeight:700, cursor:'pointer', display:'flex', alignItems:'center', gap:4 }}
                      title="Click to auto-fill demo credentials"
                    >
                      ⚡ Auto-Fill
                    </button>
                  </div>
                  <div style={{ fontSize:11, color:GOV.blue, wordBreak:'break-word' }}>
                    <strong>Officer:</strong> <code style={{ background:'rgba(0,0,0,0.08)', padding:'1px 4px', borderRadius:4, fontWeight:600 }}>officer@gem.gov.in</code> / <code style={{ background:'rgba(0,0,0,0.08)', padding:'1px 4px', borderRadius:4, fontWeight:600 }}>Admin@123</code>
                  </div>
                  <div style={{ fontSize:10, color:'#3B82F6', marginTop:3 }}>Or use your registered Bidder credentials</div>
                </div>
                <button id="login-submit" type="submit" disabled={loading}
                  style={{ width:'100%', padding:'12px', borderRadius:8, border:'none', background:loading?'#94A3B8':`linear-gradient(135deg, ${GOV.navyDark}, ${GOV.navy})`, color:'#FFF', fontWeight:700, fontSize:14, cursor:loading?'not-allowed':'pointer', boxShadow:loading?'none':`0 4px 14px rgba(0,51,102,0.4)`, transition:'all 0.2s', letterSpacing:'0.02em' }}
                  onMouseEnter={e=>{if(!loading){e.currentTarget.style.boxShadow=`0 6px 20px rgba(0,51,102,0.55)`;e.currentTarget.style.transform='translateY(-1px)';}}}
                  onMouseLeave={e=>{e.currentTarget.style.boxShadow=`0 4px 14px rgba(0,51,102,0.4)`;e.currentTarget.style.transform='none';}}>
                  {loading ? t('btn_logging') : t('btn_login')}
                </button>
              </form>
            </div>
            {/* REGISTER PANEL */}
            <div style={{ minWidth:'100%', padding:'18px', boxSizing:'border-box' }}>
              {error && <div role="alert" style={{ background:'#FEF2F2', border:'1px solid #FECACA', borderRadius:7, padding:'10px 14px', marginBottom:12, color:GOV.red, fontSize:12, fontWeight:600 }}>⚠️ {error}</div>}
              <form onSubmit={doRegister} noValidate>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(190px, 1fr))', gap:10, marginBottom:10 }}>
                  <div><label style={lbl}>{t('field_company')}</label><input required placeholder="Bharat Safety Pvt. Ltd" value={company} onChange={e=>setCompany(e.target.value)} style={inp} onFocus={e=>e.target.style.borderColor=GOV.navy} onBlur={e=>e.target.style.borderColor=tk.inputBorder} /></div>
                  <div><label style={lbl}>{t('field_rep')}</label><input required placeholder="Rajesh Kumar" value={regName} onChange={e=>setRegName(e.target.value)} style={inp} onFocus={e=>e.target.style.borderColor=GOV.navy} onBlur={e=>e.target.style.borderColor=tk.inputBorder} /></div>
                </div>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(190px, 1fr))', gap:10, marginBottom:10 }}>
                  <div><label style={lbl}>{t('field_gstin')}</label><input required placeholder="33AABCA1234F1Z5" maxLength={15} value={gstin} onChange={e=>setGstin(e.target.value.toUpperCase())} style={{...inp,fontFamily:'monospace'}} onFocus={e=>e.target.style.borderColor=GOV.navy} onBlur={e=>e.target.style.borderColor=tk.inputBorder} /></div>
                  <div><label style={lbl}>{t('field_pan')}</label><input required placeholder="AABCA1234F" maxLength={10} value={pan} onChange={e=>setPan(e.target.value.toUpperCase())} style={{...inp,fontFamily:'monospace'}} onFocus={e=>e.target.style.borderColor=GOV.navy} onBlur={e=>e.target.style.borderColor=tk.inputBorder} /></div>
                </div>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(190px, 1fr))', gap:10, marginBottom:10 }}>
                  <div><label style={lbl}>{t('field_category')}</label>
                    <select value={category} onChange={e=>setCategory(e.target.value)} style={{...inp,background:tk.inputBg}}>
                      <option value="MSME">MSME (Udyam Verified)</option>
                      <option value="STARTUP">DPIIT Startup</option>
                      <option value="LARGE">Large Enterprise</option>
                    </select>
                  </div>
                  <div><label style={lbl}>{t('field_turnover')}</label><input type="number" step="0.1" required placeholder="18.5" value={turnover} onChange={e=>setTurnover(e.target.value)} style={inp} onFocus={e=>e.target.style.borderColor=GOV.green} onBlur={e=>e.target.style.borderColor=tk.inputBorder} /></div>
                </div>
                <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(190px, 1fr))', gap:10, marginBottom:16 }}>
                  <div><label style={lbl}>{t('field_username')}</label><input required placeholder="bharat_safety_26" value={regUsername} onChange={e=>setRegUsername(e.target.value)} style={inp} onFocus={e=>e.target.style.borderColor=GOV.green} onBlur={e=>e.target.style.borderColor=tk.inputBorder} /></div>
                  <div><label style={lbl}>{t('field_password')}</label><input type="password" required placeholder="••••••••" value={regPassword} onChange={e=>setRegPassword(e.target.value)} style={inp} onFocus={e=>e.target.style.borderColor=GOV.green} onBlur={e=>e.target.style.borderColor=tk.inputBorder} /></div>
                </div>
                <button type="submit" disabled={loading}
                  style={{ width:'100%', padding:'12px', borderRadius:8, border:'none', background:loading?'#94A3B8':`linear-gradient(135deg, #0D6E08, ${GOV.green})`, color:'#FFF', fontWeight:700, fontSize:14, cursor:loading?'not-allowed':'pointer', boxShadow:loading?'none':'0 4px 14px rgba(19,136,8,0.4)', transition:'all 0.2s' }}
                  onMouseEnter={e=>{if(!loading){e.currentTarget.style.boxShadow='0 6px 20px rgba(19,136,8,0.55)';e.currentTarget.style.transform='translateY(-1px)';}}}
                  onMouseLeave={e=>{e.currentTarget.style.boxShadow='0 4px 14px rgba(19,136,8,0.4)';e.currentTarget.style.transform='none';}}>
                  {loading ? t('btn_registering') : t('btn_register')}
                </button>
              </form>
            </div>
          </div>
        </div>
        <Tricolor h={2.5} />
      </div>
    </div>
  );
}

// ── Government Footer ─────────────────────────────────────────────────────────
function GovFooter({ t, tk }) {
  return (
    <footer style={{ background:'#07090F', borderTop:`1px solid #111827`, marginTop:'auto' }}>
      <Tricolor h={2.5} />
      <div style={{ maxWidth:1400, margin:'0 auto', padding:'22px 18px 16px' }}>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(175px,1fr))', gap:22, marginBottom:18 }}>
          <div>
            <div style={{ display:'flex', alignItems:'center', gap:9, marginBottom:9 }}>
              <AshokaEmblem size={32} />
              <div>
                <div style={{ color:'#F9FAFB', fontWeight:800, fontSize:14 }}>RashtraBid</div>
                <div style={{ color:'#4B5563', fontSize:10 }}>SIH 2026 — Problem 26100</div>
              </div>
            </div>
            <div style={{ color:'#4B5563', fontSize:11, lineHeight:1.8 }}>
              AI-Powered Bid Compliance<br/>CPCL / GeM Integration<br/>Ministry of Petroleum & Natural Gas
            </div>
            {/* Patriotic slogan */}
            <div style={{ marginTop:12, padding:'8px 12px', background:'rgba(255,102,0,0.08)', borderLeft:`3px solid ${GOV.saffron}`, borderRadius:'0 6px 6px 0' }}>
              <div style={{ color:GOV.saffron, fontSize:11, fontWeight:700 }}>जय हिंद! जय भारत!</div>
              <div style={{ color:'#6B7280', fontSize:10 }}>One Nation · One Portal · Zero Corruption</div>
            </div>
          </div>
          <div>
            <div style={{ color:'#F9FAFB', fontWeight:700, fontSize:11, marginBottom:8, textTransform:'uppercase', letterSpacing:'0.07em' }}>Registry Links</div>
            {['GeM Portal — gem.gov.in','GSTN — gstn.gov.in','Udyam — udyamregistration.gov.in','CBDT e-Filing — incometax.gov.in','EPFO — epfindia.gov.in','MCA21 — mca.gov.in'].map(r => (
              <div key={r} style={{ color:'#4B5563', fontSize:11, marginBottom:4 }}>› {r}</div>
            ))}
          </div>
          <div>
            <div style={{ color:'#F9FAFB', fontWeight:700, fontSize:11, marginBottom:8, textTransform:'uppercase', letterSpacing:'0.07em' }}>Compliance</div>
            {[['GIGW 3.0','GIGW Certified'],['WCAG 2.1 AA','Accessible'],['GFR Rule 173','Financial'],['IT Act 2000','Cyber Law'],['RTI Act 2005','Transparency'],['DPDP Act 2023','Privacy'],['PPP-MII 2020','Make-in-India']].map(([l,s]) => (
              <div key={l} style={{ display:'flex', alignItems:'center', gap:5, marginBottom:3 }}>
                <span style={{ color:'#22C55E', fontSize:9, fontWeight:700 }}>✓</span>
                <span style={{ color:'#9CA3AF', fontSize:10 }}>{l}</span>
                <span style={{ color:'#4B5563', fontSize:10 }}>— {s}</span>
              </div>
            ))}
          </div>
          <div>
            <div style={{ color:'#F9FAFB', fontWeight:700, fontSize:11, marginBottom:8, textTransform:'uppercase', letterSpacing:'0.07em' }}>Security</div>
            {['SHA-256 Audit Chain','AES-256 Data Encryption','TLS 1.3 Transport','JWT Authentication','Rate Limiting Active','CORS Policy Enforced'].map(s => (
              <div key={s} style={{ display:'flex', alignItems:'center', gap:5, marginBottom:3 }}>
                <span style={{ color:'#3B82F6', fontSize:9 }}>🔒</span>
                <span style={{ color:'#6B7280', fontSize:10 }}>{s}</span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ borderTop:'1px solid #111827', paddingTop:12, display:'flex', justifyContent:'space-between', flexWrap:'wrap', gap:6 }}>
          <div style={{ fontSize:10, color:'#374151' }}>{t('footer_copy')}</div>
          <div style={{ fontSize:10, color:'#374151' }}>{t('footer_contact')}</div>
        </div>
      </div>
    </footer>
  );
}

// ── Main Export ───────────────────────────────────────────────────────────────
export default function LandingPage() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const lang = useSelector(selectLang);
  const t = useTranslation(lang);
  const [dark, setDark] = useState(() => localStorage.getItem('gg_theme') === 'dark');
  const [textScale, setTextScale] = useState(1);
  const [modal, setModal] = useState(null);
  const tk = theme(dark);
  const { data, loading } = useLiveMetrics();
  const fontSize = textScale === 0 ? 13 : textScale === 2 ? 17 : 15;

  const toggleDark = () => setDark(d => { const n=!d; localStorage.setItem('gg_theme',n?'dark':'light'); return n; });
  const changeLang = useCallback((code) => dispatch(setGlobalLang(code)), [dispatch]);

  function handleSuccess(res) {
    if (res.token) dispatch(loginSuccess({ token:res.token, role:res.role, name:res.name||res.user?.name, email:res.username, department:res.user?.department||'' }));
    navigate(res.role === 'BIDDER' ? '/my-bids' : '/dashboard', { replace:true });
  }

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        @keyframes ggpulse{0%,100%{opacity:1}50%{opacity:0.35}}
        input[type=search]::-webkit-search-cancel-button{display:none}
        :focus-visible{outline:2px solid ${GOV.navy};outline-offset:2px}
        html{scroll-behavior:smooth}
      `}</style>
      <div style={{ minHeight:'100vh', background:tk.bg, color:tk.text, fontFamily:"'Inter','Segoe UI',sans-serif", fontSize, display:'flex', flexDirection:'column', transition:'background 0.25s,color 0.25s' }}>
        <TopRibbon t={t} lang={lang} onLangChange={changeLang} dark={dark} onDarkToggle={toggleDark} textScale={textScale} onScaleChange={setTextScale} />
        <MainHeader t={t} tk={tk} onOfficer={() => setModal('OFFICER')} onBidder={() => setModal('BIDDER')} />
        <main id="main-content">
          <HeroSection t={t} tk={tk} data={data} onOfficer={() => setModal('OFFICER')} onBidder={() => setModal('BIDDER')} />
          <LiveMetrics t={t} tk={tk} data={data} loading={loading} />
          <StatutoryCategories t={t} tk={tk} />
          <PipelineStrip tk={tk} />
        </main>
        <GovFooter t={t} tk={tk} />
        {modal && <PortalModal tk={tk} t={t} mode={modal} onClose={() => setModal(null)} onSuccess={handleSuccess} />}
      </div>
    </>
  );
}
