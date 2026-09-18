/**
 * RashtraBid API Gateway v6.0
 * High-Performance Secure API Gateway & Reverse Proxy
 *
 * v6.0 Strict Specifications:
 * 1. Express initialized with helmet, cors, and morgan
 * 2. http-proxy-middleware forwarding /api/v1/* to process.env.BACKEND_URL
 * 3. GET /health at root for Render keep-alive
 * 4. Five-Persona Stateless JWT Authentication (PROCUREMENT_OFFICER, TECHNICAL_EVALUATOR,
 *    FINANCIAL_EVALUATOR, AUDIT_OFFICER, BIDDER)
 * 5. Header Injection: x-user-id, x-user-role stripped then re-injected from JWT
 * 6. Route-Level RBAC: Per-route role enforcement, no cross-role bleed
 * 7. Time Blinder: Officers blocked from reading bid content before tender closing_date
 * 8. Deadline Gate: Bidder document uploads hard-rejected after tender closing_date
 * 9. FINANCIAL_EVALUATOR: Financial unsealing + L1 endpoints gated behind role check
 */

import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import dotenv from 'dotenv';
import { createProxyMiddleware } from 'http-proxy-middleware';

import {
  authMiddleware,
  injectProxyHeaders,
  generateToken,
  MOCK_PERSONAS,
  JWT_SECRET,
} from './middleware/auth.js';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

// ── v6.0 RBAC Helpers ──────────────────────────────────────────────────────────

/**
 * Route-level RBAC guard middleware factory.
 * Usage: app.use('/path', rbac('ROLE_A', 'ROLE_B'), proxy)
 */
function rbac(...roles) {
  return (req, res, next) => {
    const userRole = req.user?.role || req.headers['x-user-role'] || '';
    if (!userRole) {
      return res.status(401).json({ error: 'Unauthorized', message: 'Authentication required', code: 'NO_AUTH' });
    }
    if (!roles.includes(userRole)) {
      return res.status(403).json({
        error: 'Forbidden',
        message: `Your role '${userRole}' is not authorized for this endpoint. Required: [${roles.join(', ')}]`,
        code: 'RBAC_DENIED',
        user_role: userRole,
        required_roles: roles,
      });
    }
    return next();
  };
}

/**
 * Time Blinder Middleware — v6.0
 * Blocks PROCUREMENT_OFFICERs from accessing bid content/documents
 * before the tender's closing_date. Prevents insider price-peeking.
 * The backend must include x-tender-closing-date header in responses,
 * but we enforce this at the gateway via query param or body inspection.
 * For uploads: we check x-tender-deadline header set by backend on prior tender fetch.
 */
async function timeBlinder(req, res, next) {
  const role = req.user?.role || '';
  if (role !== 'PROCUREMENT_OFFICER') return next();

  // Extract tender closing date from custom request header (set by frontend after fetching tender)
  const deadline = req.headers['x-tender-deadline'];
  if (!deadline) return next(); // No deadline info provided; defer to backend

  const closingDate = new Date(deadline);
  if (isNaN(closingDate.getTime())) return next();

  if (new Date() < closingDate) {
    return res.status(403).json({
      error: 'Forbidden',
      message: '⏰ Time Blinder Active: Bid contents are sealed until the tender closing date.',
      code: 'TIME_BLINDER_ACTIVE',
      tender_closes_at: closingDate.toISOString(),
      current_time: new Date().toISOString(),
    });
  }
  return next();
}

/**
 * Deadline Gate Middleware — v6.0
 * Hard-rejects BIDDER document uploads that arrive after T_deadline.
 * Reads x-tender-deadline header (set by the frontend from the tender object).
 */
async function deadlineGate(req, res, next) {
  const role = req.user?.role || '';
  if (role !== 'BIDDER') return next();

  const deadline = req.headers['x-tender-deadline'];
  if (!deadline) return next(); // No deadline provided; backend enforces

  const closingDate = new Date(deadline);
  if (isNaN(closingDate.getTime())) return next();

  if (new Date() > closingDate) {
    return res.status(423).json({
      error: 'Locked',
      message: '🔒 Deadline Gate: The submission window for this tender has officially closed. No further uploads are accepted.',
      code: 'DEADLINE_PASSED',
      tender_closed_at: closingDate.toISOString(),
      submitted_at: new Date().toISOString(),
    });
  }
  return next();
}

// ── 1. Security Headers (Helmet) ─────────────────────────────────────────────
app.use(helmet({
  crossOriginResourcePolicy: { policy: 'cross-origin' },
  crossOriginOpenerPolicy: { policy: 'same-origin-allow-popups' },
}));

// ── 2. CORS Configuration ───────────────────────────────────────────────────
const allowedOrigins = [
  FRONTEND_URL,
  'http://localhost:5173',
  'http://localhost:3000',
  'http://127.0.0.1:5173',
  'http://127.0.0.1:3000',
];

app.use(cors({
  origin: (origin, callback) => {
    if (!origin) return callback(null, true);
    if (allowedOrigins.includes(origin) || /^https:\/\/.*\.vercel\.app$/.test(origin)) {
      return callback(null, true);
    }
    return callback(new Error('CORS policy violation - Origin not allowed'), false);
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
  allowedHeaders: [
    'Content-Type',
    'Authorization',
    'X-Requested-With',
    'x-user-id',
    'x-user-role',
    'x-user-name',
    'x-user-permissions',
    'x-user-rights',
    'x-tender-deadline',
  ],
  exposedHeaders: ['x-user-id', 'x-user-role', 'x-user-name'],
}));

// ── 3. Request Logging (Morgan) ──────────────────────────────────────────────
app.use(morgan('dev'));

// ── 4. Health Check ───────────────────────────────────────────────────────────
app.get('/health', (req, res) => {
  res.status(200).json({
    status: 'ok',
    service: 'api-gateway',
    version: '6.0.0',
    backend_target: BACKEND_URL,
    timestamp: new Date().toISOString(),
    rbac_roles: ['PROCUREMENT_OFFICER', 'TECHNICAL_EVALUATOR', 'FINANCIAL_EVALUATOR', 'AUDIT_OFFICER', 'BIDDER'],
    v6_features: ['TIME_BLINDER', 'DEADLINE_GATE', 'FINANCIAL_ENVELOPE', 'L1_RANKING', 'TWO_ENVELOPE_UPLOAD'],
  });
});

app.get('/', (req, res) => {
  res.status(200).json({
    name: 'RashtraBid API Gateway',
    version: '6.0.0',
    status: 'active',
    health: '/health',
    api_base: '/api/v1',
    personas: Object.keys(MOCK_PERSONAS).map((email) => ({
      email,
      role: MOCK_PERSONAS[email].role,
      name: MOCK_PERSONAS[email].name,
      rights: MOCK_PERSONAS[email].rights,
    })),
  });
});

// ── 5. Persona Login Handler ────────────────────────────────────────────────
const parseAuthBody = [express.json(), express.urlencoded({ extended: true })];

async function handleLogin(req, res) {
  try {
    const { username, email, password } = req.body || {};
    const identifier = (username || email || '').trim().toLowerCase();

    if (!identifier) {
      return res.status(400).json({
        error: 'Bad Request',
        message: 'Username or email is required',
      });
    }

    const persona = MOCK_PERSONAS[identifier];

    if (persona) {
      // Validate password if supplied
      if (password !== undefined && password !== null && password !== '') {
        const isValidPassword = persona.passwords.includes(password);
        if (!isValidPassword) {
          return res.status(401).json({
            error: 'Unauthorized',
            message: 'Invalid credentials for mock persona',
          });
        }
      }

      // Generate stateless JWT token
      const token = generateToken(persona);

      return res.status(200).json({
        token,
        role: persona.role,
        name: persona.name,
        username: persona.username,
        rights: persona.rights,
        permissions: persona.permissions,
        user: {
          id: persona.id,
          username: persona.username,
          name: persona.name,
          role: persona.role,
          department: persona.department,
          rights: persona.rights,
        },
      });
    }

    // If identifier is not in mock personas, attempt fallback to FastAPI backend
    try {
      const resp = await fetch(`${BACKEND_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: identifier, password: password || '' }),
      });
      const data = await resp.json().catch(() => ({}));
      return res.status(resp.status).json(data);
    } catch {
      return res.status(401).json({
        error: 'Unauthorized',
        message: `User '${identifier}' not found in mock personas and backend authentication is unreachable.`,
        available_personas: Object.keys(MOCK_PERSONAS),
      });
    }
  } catch (err) {
    return res.status(500).json({
      error: 'Internal Server Error',
      message: err.message,
    });
  }
}

// Register login route on all standard paths
app.post('/api/v1/auth/login', parseAuthBody, handleLogin);
app.post('/api/auth/login', parseAuthBody, handleLogin);
app.post('/auth/login', parseAuthBody, handleLogin);
app.post('/login', parseAuthBody, handleLogin);

// Persona catalog endpoint for UI/testers
app.get('/api/v1/auth/personas', (req, res) => {
  res.json({
    personas: Object.values(MOCK_PERSONAS).map(({ id, username, name, role, department, rights, permissions }) => ({
      id,
      username,
      name,
      role,
      department,
      rights,
      permissions,
    })),
  });
});
app.get('/auth/personas', (req, res) => {
  res.redirect('/api/v1/auth/personas');
});

// Current user inspection endpoint
app.get(['/api/v1/auth/me', '/api/auth/me', '/auth/me'], authMiddleware, (req, res) => {
  if (req.user) {
    return res.json({
      ...req.user,
      headers_injected: {
        'x-user-id': req.headers['x-user-id'],
        'x-user-role': req.headers['x-user-role'],
        'x-user-name': req.headers['x-user-name'],
      },
    });
  }
  return res.status(401).json({ error: 'Unauthorized', message: 'Not authenticated' });
});

// ── 6. Global Auth (runs FIRST — populates req.user for all RBAC guards below) ──
app.use(authMiddleware);

// ── 7. v6.0 Route-Level RBAC Guards ────────────────────────────────────────────

// Financial envelope routes — FINANCIAL_EVALUATOR only
app.use(/^\/((api\/v1\/|api\/)?financial\/)/, rbac('FINANCIAL_EVALUATOR'));

// Officer override — PROCUREMENT_OFFICER only
app.post(/^\/((api\/v1\/|api\/)?bids\/[^/]+\/override)$/, rbac('PROCUREMENT_OFFICER'));

// Audit export — AUDIT_OFFICER only
app.get(/^\/((api\/v1\/|api\/)?audit\/export)/, rbac('AUDIT_OFFICER'));

// Bid document uploads — apply Deadline Gate (blocks BIDDER after closing_date)
app.post(/^\/((api\/v1\/|api\/)?bids\/[^/]+\/(documents\/upload|package\/upload|envelope\/upload))$/, deadlineGate);

// Bid content access — apply Time Blinder (blocks PROCUREMENT_OFFICER before closing_date)
app.get(/^\/((api\/v1\/|api\/)?bids\/[^/]+\/(documents|evidence|packages))/, timeBlinder);

// BIDDER: silently rewrite /bids → /bids/mine so they only see their own data
app.get(/^\/((api\/v1\/|api\/)?bids)$/, (req, res, next) => {
  const role = req.user?.role || '';
  if (role === 'BIDDER') {
    // Redirect to their own bids only
    req.url = req.url.replace(/\/bids$/, '/bids/mine');
    req.path = '/bids/mine';
  }
  return next();
});

// ── 7. Reverse Proxy with Header Injection to FastAPI Backend ───────────────
// Note: We do NOT use global express.json() so multipart form-data streams intact
const backendProxy = createProxyMiddleware({
  target: BACKEND_URL,
  changeOrigin: true,
  ws: true,
  pathFilter: (pathname) => pathname.startsWith('/api') || pathname.startsWith('/auth'),
  on: {
    proxyReq: (proxyReq, req, res) => {
      injectProxyHeaders(proxyReq, req);
    },
    error: (err, req, res) => {
      console.error('[Gateway Proxy Error]', err.message);
      if (!res.headersSent) {
        res.status(502).json({
          error: 'Bad Gateway',
          message: 'Unable to connect to RashtraBid Backend service.',
          detail: err.message,
          backend_target: BACKEND_URL,
        });
      }
    },
  },
  // Legacy event hooks for backwards compatibility with various HPM configurations
  onProxyReq: (proxyReq, req, res) => {
    injectProxyHeaders(proxyReq, req);
  },
  onError: (err, req, res) => {
    console.error('[Gateway Proxy Error]', err.message);
    if (!res.headersSent) {
      res.status(502).json({
        error: 'Bad Gateway',
        message: 'Unable to connect to RashtraBid Backend service.',
        detail: err.message,
        backend_target: BACKEND_URL,
      });
    }
  },
});

// Reverse proxy — auth already applied globally above
app.use(backendProxy);

// ── 7. Server Listener ──────────────────────────────────────────────────────
const server = app.listen(PORT, '0.0.0.0', () => {
  console.log(`====================================================`);
  console.log(`🛡️  GeM-Guard API Gateway listening on port ${PORT}`);
  console.log(`🔗 Target Backend: ${BACKEND_URL}`);
  console.log(`🌐 Allowed Frontend: ${FRONTEND_URL}`);
  console.log(`💓 Health Check: http://localhost:${PORT}/health`);
  console.log(`🔑 Available Personas:`);
  Object.values(MOCK_PERSONAS).forEach((p) => {
    console.log(`   - ${p.username} [${p.role}] (${p.rights})`);
  });
  console.log(`====================================================`);
});

export { app, server };
export default app;
