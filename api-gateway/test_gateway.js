/**
 * GeM-Guard API Gateway Comprehensive Test Suite
 * Validates:
 * 1. Health check & Root keep-alive
 * 2. Mock personas JWT login (officer, evaluator, auditor)
 * 3. Invalid credentials rejection
 * 4. Token decode & claims verification
 * 5. Auth middleware protection & spoofing prevention
 * 6. Reverse proxy header injection (x-user-id, x-user-role)
 */

import http from 'http';
import jwt from 'jsonwebtoken';

const GATEWAY_PORT = 3010;
const MOCK_BACKEND_PORT = 8011;
const JWT_SECRET = 'sih_26100_supersecret';

process.env.PORT = String(GATEWAY_PORT);
process.env.BACKEND_URL = `http://localhost:${MOCK_BACKEND_PORT}`;
process.env.JWT_SECRET = JWT_SECRET;

// 1. Start mock FastAPI backend to verify incoming headers
let lastBackendRequest = null;
const mockBackend = http.createServer((req, res) => {
  lastBackendRequest = {
    method: req.method,
    url: req.url,
    headers: { ...req.headers },
  };
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ status: 'ok', receivedHeaders: req.headers, path: req.url }));
});

await new Promise((resolve) => mockBackend.listen(MOCK_BACKEND_PORT, resolve));
console.log(`[TEST] Mock backend listening on port ${MOCK_BACKEND_PORT}`);

// 2. Start Gateway server
const { app } = await import('./server.js');
const gatewayServer = app.listen(GATEWAY_PORT);
console.log(`[TEST] Gateway testing instance listening on port ${GATEWAY_PORT}`);

let passed = 0;
let failed = 0;

function assert(condition, message) {
  if (condition) {
    console.log(`  ✓ ${message}`);
    passed++;
  } else {
    console.error(`  ✗ FAILED: ${message}`);
    failed++;
  }
}

try {
  const base = `http://localhost:${GATEWAY_PORT}`;

  // Test 1: GET /health
  console.log('\n--- Test 1: Health Check (Render keep-alive) ---');
  const healthRes = await fetch(`${base}/health`);
  const healthJson = await healthRes.json();
  assert(healthRes.status === 200, 'GET /health returns HTTP 200');
  assert(healthJson.status === 'ok', 'Health status is ok');
  assert(healthJson.service === 'api-gateway', 'Service identifier is api-gateway');

  // Test 2: GET / (Root info)
  console.log('\n--- Test 2: Root info ---');
  const rootRes = await fetch(`${base}/`);
  const rootJson = await rootRes.json();
  assert(rootRes.status === 200, 'GET / returns HTTP 200');
  assert(rootJson.status === 'active', 'Gateway status is active');

  // Test 3: Login for Officer
  console.log('\n--- Test 3: Officer Persona Login ---');
  const officerLoginRes = await fetch(`${base}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'officer@gem.gov.in', password: 'Admin@123' }),
  });
  const officerJson = await officerLoginRes.json();
  assert(officerLoginRes.status === 200, 'Officer login returns HTTP 200');
  assert(officerJson.role === 'PROCUREMENT_OFFICER', 'Officer role is PROCUREMENT_OFFICER');
  assert(typeof officerJson.token === 'string', 'Officer receives JWT token');
  
  const decodedOfficer = jwt.verify(officerJson.token, JWT_SECRET);
  assert(decodedOfficer.sub === 'officer@gem.gov.in', 'Decoded sub is officer@gem.gov.in');
  assert(decodedOfficer.role === 'PROCUREMENT_OFFICER', 'Decoded role is PROCUREMENT_OFFICER');
  assert(decodedOfficer.rights.includes('full override'), 'Decoded rights include full override');

  // Test 4: Login for Evaluator
  console.log('\n--- Test 4: Evaluator Persona Login ---');
  const evalLoginRes = await fetch(`${base}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'evaluator@gem.gov.in', password: 'Eval@123' }),
  });
  const evalJson = await evalLoginRes.json();
  assert(evalLoginRes.status === 200, 'Evaluator login returns HTTP 200');
  assert(evalJson.role === 'TECHNICAL_EVALUATOR', 'Evaluator role is TECHNICAL_EVALUATOR');
  assert(typeof evalJson.token === 'string', 'Evaluator receives JWT token');

  const decodedEval = jwt.verify(evalJson.token, JWT_SECRET);
  assert(decodedEval.sub === 'evaluator@gem.gov.in', 'Decoded sub is evaluator@gem.gov.in');
  assert(decodedEval.role === 'TECHNICAL_EVALUATOR', 'Decoded role is TECHNICAL_EVALUATOR');
  assert(decodedEval.rights.includes('read-only/review'), 'Decoded rights include read-only/review');

  // Test 5: Login for Auditor
  console.log('\n--- Test 5: Auditor Persona Login ---');
  const auditLoginRes = await fetch(`${base}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'auditor@gem.gov.in', password: 'Audit@123' }),
  });
  const auditJson = await auditLoginRes.json();
  assert(auditLoginRes.status === 200, 'Auditor login returns HTTP 200');
  assert(auditJson.role === 'AUDIT_OFFICER', 'Auditor role is AUDIT_OFFICER');
  assert(typeof auditJson.token === 'string', 'Auditor receives JWT token');

  const decodedAudit = jwt.verify(auditJson.token, JWT_SECRET);
  assert(decodedAudit.sub === 'auditor@gem.gov.in', 'Decoded sub is auditor@gem.gov.in');
  assert(decodedAudit.role === 'AUDIT_OFFICER', 'Decoded role is AUDIT_OFFICER');
  assert(decodedAudit.rights.includes('audit log view'), 'Decoded rights include audit log view');

  // Test 6: Invalid password rejection
  console.log('\n--- Test 6: Invalid Credentials Handling ---');
  const badLoginRes = await fetch(`${base}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'officer@gem.gov.in', password: 'WrongPassword' }),
  });
  assert(badLoginRes.status === 401, 'Invalid password returns HTTP 401');

  // Test 7: Protected route without token rejected
  console.log('\n--- Test 7: Protected Route Rejection without Token ---');
  const noTokenRes = await fetch(`${base}/api/v1/tenders`);
  assert(noTokenRes.status === 401, 'Protected route /api/v1/tenders without token returns HTTP 401');

  // Test 8: Proxy Header Injection with Officer Token
  console.log('\n--- Test 8: Reverse Proxy Header Injection (Officer) ---');
  lastBackendRequest = null;
  const proxyOfficerRes = await fetch(`${base}/api/v1/tenders`, {
    headers: {
      Authorization: `Bearer ${officerJson.token}`,
      // Attempt spoofed header to verify it gets sanitized
      'x-user-role': 'ATTACKER_SPOOFED_ROLE',
    },
  });
  assert(proxyOfficerRes.status === 200, 'Proxy request with officer token succeeds (200)');
  assert(lastBackendRequest !== null, 'Backend received proxy request');
  assert(lastBackendRequest?.headers['x-user-id'] === 'officer@gem.gov.in', 'Backend received injected x-user-id: officer@gem.gov.in');
  assert(lastBackendRequest?.headers['x-user-role'] === 'PROCUREMENT_OFFICER', 'Backend received injected x-user-role: PROCUREMENT_OFFICER (spoof stripped)');

  // Test 9: Proxy Header Injection with Evaluator Token
  console.log('\n--- Test 9: Reverse Proxy Header Injection (Evaluator) ---');
  lastBackendRequest = null;
  const proxyEvalRes = await fetch(`${base}/api/v1/bids/123/review`, {
    headers: {
      Authorization: `Bearer ${evalJson.token}`,
    },
  });
  assert(proxyEvalRes.status === 200, 'Proxy request with evaluator token succeeds (200)');
  assert(lastBackendRequest?.headers['x-user-id'] === 'evaluator@gem.gov.in', 'Backend received injected x-user-id: evaluator@gem.gov.in');
  assert(lastBackendRequest?.headers['x-user-role'] === 'TECHNICAL_EVALUATOR', 'Backend received injected x-user-role: TECHNICAL_EVALUATOR');

  // Test 10: Proxy Header Injection with Auditor Token
  console.log('\n--- Test 10: Reverse Proxy Header Injection (Auditor) ---');
  lastBackendRequest = null;
  const proxyAuditRes = await fetch(`${base}/api/v1/audit/logs`, {
    headers: {
      Authorization: `Bearer ${auditJson.token}`,
    },
  });
  assert(proxyAuditRes.status === 200, 'Proxy request with auditor token succeeds (200)');
  assert(lastBackendRequest?.headers['x-user-id'] === 'auditor@gem.gov.in', 'Backend received injected x-user-id: auditor@gem.gov.in');
  assert(lastBackendRequest?.headers['x-user-role'] === 'AUDIT_OFFICER', 'Backend received injected x-user-role: AUDIT_OFFICER');

  console.log(`\n========================================`);
  console.log(`Total tests: ${passed + failed}`);
  console.log(`Passed: ${passed}`);
  console.log(`Failed: ${failed}`);
  console.log(`========================================\n`);

} catch (err) {
  console.error('Test execution error:', err);
  failed++;
} finally {
  mockBackend.close();
  gatewayServer.close();
  process.exit(failed === 0 ? 0 : 1);
}
