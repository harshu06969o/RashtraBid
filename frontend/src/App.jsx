import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { useSelector } from 'react-redux';
import TopNav from './components/TopNav';
import LandingPage from './pages/LandingPage';
import DashboardPage from './pages/DashboardPage';
import TenderWorkspacePage from './pages/TenderWorkspacePage';
import BidWorkspacePage from './pages/BidWorkspacePage';
import BidderWorkspacePage from './pages/BidderWorkspacePage';
import ComplianceDashboard from './pages/ComplianceDashboard';
import CorrigendumPage from './pages/CorrigendumPage';
import LoginPage from './pages/LoginPage';
import FinancialWorkspacePage from './pages/FinancialWorkspacePage';
import { getToken } from './api/client';

// ─── Auth Guard ───────────────────────────────────────────────────────────────
function RequireAuth({ children }) {
  const token = getToken() || localStorage.getItem('rashtrabid_token') || localStorage.getItem('token') || localStorage.getItem('gemguard_token');
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children ? <>{children}</> : <Outlet />;
}

// ─── Role Guard ───────────────────────────────────────────────────────────────
// Redirects to the role's home workspace if user tries to access an unauthorized route.
function RoleGuard({ allowedRoles, fallback }) {
  const authState = useSelector(s => s.auth);
  const role = authState?.role || localStorage.getItem('role') || '';
  if (!allowedRoles.includes(role)) {
    return <Navigate to={fallback || ROLE_HOME[role] || '/login'} replace />;
  }
  return <Outlet />;
}

// Role → default home route
const ROLE_HOME = {
  PROCUREMENT_OFFICER: '/dashboard',
  BIDDER: '/my-bids',
  FINANCIAL_EVALUATOR: '/financial',
};

// ─── Layout with TopNav ────────────────────────────────────────────────────────
function AuthLayout() {
  return (
    <RequireAuth>
      <TopNav />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', width: '100%', maxWidth: '100vw', overflowX: 'hidden' }}>
        <Outlet />
      </div>
    </RequireAuth>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', width: '100%', maxWidth: '100vw', overflowX: 'hidden' }}>
        <Routes>
          {/* Public */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />

          {/* ── Protected Layout wrapper ─────────────────────────────── */}
          <Route element={<AuthLayout />}>

            {/* Officer workspace */}
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/tenders" element={<TenderWorkspacePage />} />
            <Route path="/tenders/:tenderId" element={<TenderWorkspacePage />} />
            <Route path="/tender" element={<TenderWorkspacePage />} />
            <Route path="/tender/:tenderId" element={<TenderWorkspacePage />} />
            <Route path="/corrigendum" element={<CorrigendumPage />} />
            
            <Route path="/bids" element={<BidWorkspacePage />} />
            <Route path="/bids/:bidId" element={<BidWorkspacePage />} />
            <Route path="/compliance" element={<ComplianceDashboard />} />
            <Route element={<RoleGuard allowedRoles={['FINANCIAL_EVALUATOR']} />}>
              <Route path="/financial" element={<FinancialWorkspacePage />} />
            </Route>

            {/* Bidder workspace */}
            <Route path="/my-bids" element={<BidderWorkspacePage />} />

            {/* Shared: redirect /marketplace to correct role home */}
            <Route path="/marketplace" element={<Navigate to="/my-bids" replace />} />

          </Route>

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
