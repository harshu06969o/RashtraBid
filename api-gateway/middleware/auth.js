/**
 * RashtraBid API Gateway - Auth Middleware
 * Stateless JWT Authentication & Identity Header Injection
 */

import jwt from 'jsonwebtoken';
import dotenv from 'dotenv';

dotenv.config();

export const JWT_SECRET = process.env.JWT_SECRET || 'sih_26100_supersecret';
export const JWT_ALGORITHM = 'HS256';
export const JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || '24h';

/**
 * v6.0 — Five Isolated RBAC Personas (strict workspace separation, no role bleeding):
 * 1. officer@gem.gov.in     -> PROCUREMENT_OFFICER    (tender creation, corrigendum, award sign-off)
 * 2. evaluator@gem.gov.in   -> TECHNICAL_EVALUATOR    (OCR evidence review, connector checks)
 * 3. financial@gem.gov.in   -> FINANCIAL_EVALUATOR    (envelope unsealing, L1 ranking, MII/MSE prefs)
 * 4. auditor@gem.gov.in     -> AUDIT_OFFICER          (forensic read-only, chain verify, export)
 * 5. bidder@vendor.com      -> BIDDER                 (marketplace, sealed upload, self-check)
 */
export const MOCK_PERSONAS = {
  'officer@gem.gov.in': {
    id: 'officer@gem.gov.in',
    username: 'officer@gem.gov.in',
    email: 'officer@gem.gov.in',
    name: 'Procurement Officer (CPCL)',
    role: 'PROCUREMENT_OFFICER',
    department: 'CPCL Procurement',
    rights: 'Tender creation, corrigendum, award sign-off. Full review and financial unsealing.',
    permissions: [
      'FULL_OVERRIDE',
      'APPROVE_BID',
      'REJECT_BID',
      'SEEK_CLARIFICATION',
      'EVALUATE_BID',
      'COMPILE_REQUIREMENTS',
      'MANAGE_TENDERS',
      'READ',
      'REVIEW_BID',
      'VIEW_EVIDENCE',
      'VIEW_TRACE',
      'ADD_REVIEW_NOTE',
      'UNSEAL_FINANCIAL_ENVELOPE',
      'VIEW_FINANCIAL_BIDS',
      'CALCULATE_L1',
      'APPLY_MII_MSE_PREFERENCE',
      'VIEW_PRICE_BIDS',
    ],
    passwords: ['Admin@123', 'admin', 'officer', 'officer123', 'Password@123', 'gemguard', 'rashtrabid'],
  },
  'bidder@vendor.com': {
    id: 'bidder@vendor.com',
    username: 'bidder@vendor.com',
    email: 'bidder@vendor.com',
    name: 'Bharat Engineering & Industrial Ltd',
    role: 'BIDDER',
    department: 'Vendor / Supplier',
    rights: 'Marketplace search, pre-submission dry-run, Two-Envelope sealed upload. Own data only.',
    permissions: [
      'VIEW_TENDERS',
      'SUBMIT_BID',
      'UPLOAD_DOCUMENTS',
      'PRE_SUBMISSION_CHECK',
      'VIEW_OWN_BIDS',
    ],
    passwords: ['Bidder@123', 'bidder', 'vendor', 'Admin@123', 'Password@123', 'gemguard'],
  },
};

/**
 * Generate a signed JWT token for a persona or user payload
 */
export function generateToken(persona, customOptions = {}) {
  const payload = {
    sub: persona.username,
    id: persona.id || persona.username,
    userId: persona.id || persona.username,
    username: persona.username,
    email: persona.email || persona.username,
    role: persona.role,
    name: persona.name,
    department: persona.department,
    rights: persona.rights,
    permissions: persona.permissions,
  };

  return jwt.sign(payload, JWT_SECRET, {
    expiresIn: customOptions.expiresIn || JWT_EXPIRES_IN,
    algorithm: JWT_ALGORITHM,
  });
}

/**
 * Verify and decode a JWT token
 */
export function verifyToken(token) {
  return jwt.verify(token, JWT_SECRET, { algorithms: [JWT_ALGORITHM] });
}

/**
 * Determine if a request target is a public endpoint
 */
export function isPublicPath(path, method = 'GET') {
  if (method === 'OPTIONS') return true;

  const clean = (path || '').split('?')[0].replace(/\/+$/, '') || '/';
  
  const publicRoutes = [
    '',
    '/',
    '/health',
    '/api/health',
    '/api/v1/health',
    '/auth/login',
    '/api/auth/login',
    '/api/v1/auth/login',
    '/auth/register',
    '/api/auth/register',
    '/api/v1/auth/register',
    '/api/docs',
    '/api/redoc',
    '/openapi.json',
  ];

  if (publicRoutes.includes(clean)) return true;
  if (clean.startsWith('/api/docs') || clean.startsWith('/api/redoc')) return true;

  return false;
}

/**
 * Express Authentication Middleware
 * 1. Strips untrusted incoming client headers (spoofing prevention)
 * 2. Allows public routes without mandatory credentials
 * 3. Decodes and verifies JWT on protected routes
 * 4. Injects x-user-id and x-user-role into request
 */
export function authMiddleware(req, res, next) {
  // Security: Prevent client header spoofing by stripping untrusted identity headers
  delete req.headers['x-user-id'];
  delete req.headers['x-user-role'];
  delete req.headers['x-user-name'];
  delete req.headers['x-user-permissions'];
  delete req.headers['x-user-rights'];

  // Check if route is public
  const targetPath = req.path || req.url || '';
  const originalPath = req.originalUrl || '';
  const isPublic = isPublicPath(targetPath, req.method) || isPublicPath(originalPath, req.method);

  // Extract Bearer token from headers
  const authHeader = req.headers['authorization'] || req.headers['Authorization'];
  let token = null;

  if (authHeader && typeof authHeader === 'string') {
    const parts = authHeader.trim().split(/\s+/);
    if (parts.length === 2 && parts[0].toLowerCase() === 'bearer') {
      token = parts[1];
    } else if (parts.length === 1 && !parts[0].toLowerCase().startsWith('bearer')) {
      token = parts[0];
    }
  }

  // Fallback to query parameter (needed for iframes and download links that can't send headers)
  if (!token && req.query && req.query.token) {
    token = req.query.token;
  }

  // Fallback check for query param token if needed
  if (!token && req.query?.token) {
    token = String(req.query.token);
  }

  // If no token is provided:
  if (!token) {
    if (isPublic) {
      return next();
    }
    return res.status(401).json({
      error: 'Unauthorized',
      message: 'Authentication token required. Expected: Authorization: Bearer <token>',
      code: 'TOKEN_MISSING',
    });
  }

  // Verify and decode JWT
  try {
    const decoded = verifyToken(token);
    req.user = decoded;

    const userId = decoded.id || decoded.sub || decoded.username || '';
    const userRole = decoded.role || '';
    const userName = decoded.name || decoded.username || '';

    // Inject identity headers into req.headers
    req.headers['x-user-id'] = userId;
    req.headers['x-user-role'] = userRole;
    if (userName) req.headers['x-user-name'] = userName;
    if (decoded.permissions) {
      req.headers['x-user-permissions'] = Array.isArray(decoded.permissions)
        ? decoded.permissions.join(',')
        : String(decoded.permissions);
    }
    if (decoded.rights) {
      req.headers['x-user-rights'] = String(decoded.rights);
    }

    return next();
  } catch (err) {
    // If token is invalid/expired on a public route, allow it without user context
    if (isPublic) {
      return next();
    }

    return res.status(401).json({
      error: 'Unauthorized',
      message: 'Invalid or expired authentication token',
      detail: err.message,
      code: err.name === 'TokenExpiredError' ? 'TOKEN_EXPIRED' : 'TOKEN_INVALID',
    });
  }
}

/**
 * Injects authenticated headers into http-proxy-middleware proxyReq
 */
export function injectProxyHeaders(proxyReq, req) {
  if (req.user) {
    const userId = req.user.id || req.user.sub || req.user.username || '';
    const userRole = req.user.role || '';
    const userName = req.user.name || req.user.username || '';

    proxyReq.setHeader('x-user-id', userId);
    proxyReq.setHeader('x-user-role', userRole);
    if (userName) proxyReq.setHeader('x-user-name', userName);

    if (req.user.permissions) {
      const perms = Array.isArray(req.user.permissions)
        ? req.user.permissions.join(',')
        : String(req.user.permissions);
      proxyReq.setHeader('x-user-permissions', perms);
    }
    if (req.user.rights) {
      proxyReq.setHeader('x-user-rights', String(req.user.rights));
    }
  } else if (req.headers['x-user-id'] && req.headers['x-user-role']) {
    proxyReq.setHeader('x-user-id', req.headers['x-user-id']);
    proxyReq.setHeader('x-user-role', req.headers['x-user-role']);
    if (req.headers['x-user-name']) {
      proxyReq.setHeader('x-user-name', req.headers['x-user-name']);
    }
  }

  // Preserve and pass forwarded trace headers
  proxyReq.setHeader('X-Forwarded-Host', req.headers.host || '');
  proxyReq.setHeader('X-Gateway-Time', new Date().toISOString());
  proxyReq.setHeader('X-Gateway-Service', 'RashtraBid-API-Gateway');
}

/**
 * Role-Based Access Control Guard
 */
export function requireRole(...allowedRoles) {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({
        error: 'Unauthorized',
        message: 'Authentication required before role verification',
      });
    }
    if (!allowedRoles.includes(req.user.role)) {
      return res.status(403).json({
        error: 'Forbidden',
        message: `Access denied. Required role(s): [${allowedRoles.join(', ')}]. Current role: ${req.user.role}`,
        user_role: req.user.role,
        required_roles: allowedRoles,
      });
    }
    return next();
  };
}

export default authMiddleware;
