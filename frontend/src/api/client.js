/**
 * RashtraBid — API Client v6.0 (Pure JavaScript)
 * All routes go through the Gateway on Port 3000.
 * Vite proxies /api/* → localhost:3000 in dev.
 */

const envUrl = import.meta.env.VITE_API_URL;
// Vite proxy maps /api → localhost:3000, so /api/v1/* works end-to-end
const BASE = envUrl ? envUrl.replace(/\/$/, '') : '/api';

/**
 * Normalizes request paths against BASE to prevent duplicate /v1 segments
 * (e.g. BASE=".../api/v1" + path="/v1/bids" -> ".../api/v1/bids")
 */
function resolveUrl(path) {
  let p = path.startsWith('/') ? path : `/${path}`;
  if (BASE.endsWith('/v1') && p.startsWith('/v1/')) {
    p = p.slice(3);
  }
  return `${BASE}${p}`;
}

// Auth token management (RashtraBid with backwards-compat)
const TOKEN_KEY = 'rashtrabid_token';

export const getToken = () => localStorage.getItem(TOKEN_KEY) || localStorage.getItem('gemguard_token') || localStorage.getItem('token');
export const setToken = (t) => {
  localStorage.setItem(TOKEN_KEY, t);
  localStorage.setItem('gemguard_token', t);
};
export const clearToken = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem('gemguard_token');
  localStorage.removeItem('token');
};

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, init) {
  const url = resolveUrl(path);
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...init?.headers,
    },
    ...init,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const msg = body.detail ?? body.error ?? body.message ?? res.statusText;
    if (res.status === 401) clearToken();
    throw new ApiError(res.status, msg);
  }

  if (res.status === 204) return undefined;
  return res.json();
}

async function uploadWithProgress(path, formData, onProgress) {
  const url = resolveUrl(path);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    const token = getToken();
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });
    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          resolve({ status: 'ok', raw: xhr.responseText });
        }
      } else {
        try {
          const body = JSON.parse(xhr.responseText || '{}');
          reject(new ApiError(xhr.status, body.detail ?? body.error ?? body.message ?? xhr.statusText));
        } catch {
          reject(new ApiError(xhr.status, xhr.statusText || 'Upload failed'));
        }
      }
    });
    xhr.addEventListener('error', () => reject(new ApiError(0, 'Network error during upload')));
    xhr.send(formData);
  });
}

// ── Auth ────────────────────────────────────────────────────────────────────

export const login = async (username, password) => {
  const data = await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  setToken(data.token);
  return data;
};

export const logout = () => clearToken();

export const getMe = () => request('/auth/me');

export const registerBidder = async (payload) => {
  const data = await request('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  setToken(data.token);
  return data;
};

// ── Tenders ──────────────────────────────────────────────────────────────────

export const listTenders = async () => {
  const res = await request('/v1/tenders');
  if (!Array.isArray(res)) throw new Error('API Shape Contract Violation: listTenders expected an Array');
  return res;
};
export const getTender = (id) => request(`/v1/tenders/${id}`);
export const getTenderDocuments = (tenderId) => request(`/v1/tenders/${tenderId}/documents`);
export const createTender = (payload) =>
  request('/v1/tenders', { method: 'POST', body: JSON.stringify(payload) });
export const updateTender = (id, payload) =>
  request(`/v1/tenders/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
export const uploadTenderDocument = (tenderId, file, onProgress) => {
  const fd = new FormData();
  fd.append('file', file);
  return uploadWithProgress(`/v1/tenders/${tenderId}/upload`, fd, onProgress);
};
export const compileRequirements = (tenderId, source) =>
  request(`/v1/tenders/${tenderId}/compile`, { method: 'POST', body: JSON.stringify({ source }) });
export const getTenderBids = (tenderId) => request(`/v1/tenders/${tenderId}/bids`);
export const deleteTender = (id) => request(`/v1/tenders/${id}`, { method: 'DELETE' });

// ── Bidders ──────────────────────────────────────────────────────────────────

export const listBidders = () => request('/v1/bidders');
export const getBidder = (id) => request(`/v1/bidders/${id}`);
export const getMyProfile = () => request('/v1/bidders/me/profile');

// ── Bids ─────────────────────────────────────────────────────────────────────

export const listBids = (tenderId) =>
  request(tenderId ? `/v1/bids?tender_id=${encodeURIComponent(tenderId)}` : '/v1/bids');
export const getMyBids = (tenderId) =>
  request(tenderId ? `/v1/bids/mine?tender_id=${encodeURIComponent(tenderId)}` : '/v1/bids/mine');
export const getBid = (id) => request(`/v1/bids/${id}`);
export const submitBid = (tenderId, extra = {}) =>
  request('/v1/bids', {
    method: 'POST',
    body: JSON.stringify(typeof tenderId === 'object' ? tenderId : { tender_id: tenderId, ...extra }),
  });
export const submitOfficerAction = (bidId, payload) =>
  request(`/v1/bids/${bidId}/officer-action`, { method: 'POST', body: JSON.stringify(payload) });

export const submitOfficerOverride = (bidId, payload) =>
  request(`/v1/bids/${bidId}/override`, { method: 'POST', body: JSON.stringify(payload) });

// ── Bidder Documents ──────────────────────────────────────────────────────────

export const listBidDocuments = (bidId) => request(`/v1/bids/${bidId}/documents`);
export const listBidEvidence = (bidId) => request(`/v1/bids/${bidId}/evidence`);
export const getBidDocument = (bidId, docId) => request(`/v1/bids/${bidId}/documents/${docId}`);
export const uploadBidderDocument = (bidId, file, docType = null, onProgress = null) => {
  let progressFn = onProgress;
  let categoryHint = docType;
  if (typeof docType === 'function') {
    progressFn = docType;
    categoryHint = null;
  }
  const fd = new FormData();
  fd.append('file', file);
  if (categoryHint) {
    fd.append('document_type', categoryHint);
  }
  return uploadWithProgress(`/v1/bids/${bidId}/documents/upload`, fd, progressFn);
};
export const uploadBidPackage = (bidId, files, onProgress = null) => {
  const fd = new FormData();
  for (const f of files) {
    fd.append('files', f);
  }
  return uploadWithProgress(`/v1/bids/${bidId}/package/upload`, fd, onProgress);
};
export const deleteBidDocument = (bidId, docId) =>
  request(`/v1/bids/${bidId}/documents/${docId}`, { method: 'DELETE' });

// ── Compliance Engine ────────────────────────────────────────────────────────

export const evaluateBid = (bidId) =>
  request(`/v1/bids/${bidId}/evaluate`, { method: 'POST' });

// ── Verification Connectors ───────────────────────────────────────────────────

export const runVerification = (bidId) => request(`/v1/bids/${bidId}/verify`, { method: 'POST' });
export const listVerifications = (bidId) => request(`/v1/bids/${bidId}/verifications`);
export const getConnectorsHealth = () => request('/v1/connectors/health');

// ── Trace & Audit ────────────────────────────────────────────────────────────

export const getComplianceTrace = (bidId) => request(`/v1/bids/${bidId}/trace`);
export const getAuditTimeline = (bidId) => request(`/v1/bids/${bidId}/audit`);
export const getAuditTrail = (bidId) => request(`/v1/bids/${bidId}/audit`);
export const getAuditReport = (bidId) => request(`/v1/bids/${bidId}/report`);

// ── Full Audit Chain (AUDIT_OFFICER only) ────────────────────────────────────

export const getFullAuditChain = (bidId) => request(`/v1/audit/chain/${bidId}`);
export const getAllAuditEvents = (limit = 200) => request(`/v1/audit/events?limit=${limit}`);
export const verifyChainIntegrity = (bidId) => request(`/v1/audit/verify/${bidId}`);
export const exportAuditDossier = (bidId) => request(`/v1/audit/export/${bidId}`);
export const exportFullDossier = () => request('/v1/audit/export');

// ── Financial Evaluator (FINANCIAL_EVALUATOR only) ───────────────────────────

export const getFinancialEnvelopes = (bidId) =>
  request(`/v1/financial/bids/${bidId}/envelope`);

export const unsealBid = (bidId, payload = {}) =>
  request(`/v1/financial/bids/${bidId}/unseal`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export const getL1Ranking = (tenderId) =>
  request(`/v1/financial/tenders/${tenderId}/l1`);

export const uploadFinancialEnvelope = (bidId, file, quotedPrice, miiPct, onProgress) => {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('quoted_price', String(quotedPrice));
  fd.append('mii_local_content_pct', String(miiPct));
  return uploadWithProgress(`/v1/financial/bids/${bidId}/envelope/upload`, fd, onProgress);
};

// ── Corrigendum ───────────────────────────────────────────────────────────────

export const runCorrigendumAnalysis = (payload) =>
  request('/v1/corrigendum/impact-analysis', { method: 'POST', body: JSON.stringify(payload) });

// ── Health ────────────────────────────────────────────────────────────────────

export const getHealth = () => request('/health', { headers: {} });

// ── Users (Officer) ───────────────────────────────────────────────────────────

export const listUsers = () => request('/v1/users');
