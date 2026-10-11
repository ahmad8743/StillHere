/* Local, session-scoped Plaid Sandbox bridge. Provider tokens stay in server memory. */
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const { randomBytes, createHash } = require('node:crypto');

const ROOT = path.resolve(__dirname, '..');
const FRONTEND = path.join(ROOT, 'frontend');
const STATIC = new Set(['index.html', 'styles.css', 'fixtures.js', 'finance-validation.js', 'finance-engine.js', 'mock-service.js', 'finance-controls.js', 'check-in-demo.js', 'check-in-controls.js', 'plaid-controls.js', 'app.js']);
const sessions = new Map();
const secretId = () => randomBytes(32).toString('hex');
const cents = (value) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const rounded = Math.round(value * 100);
  return Number.isSafeInteger(rounded) && Math.abs(value * 100 - rounded) < 0.00001 ? rounded : null;
};
const fail = (status, code, message) => Object.assign(new Error(message), { status, code });

async function configuration() {
  const values = {};
  try {
    const text = await fs.readFile(path.join(ROOT, '.env.plaid'), 'utf8');
    for (const line of text.split(/\r?\n/)) {
      const match = line.match(/^\s*(PLAID_CLIENT_ID|PLAID_SECRET|PLAID_ENV|PLAID_DEMO_PORT)\s*=\s*(.*?)\s*$/);
      if (match) values[match[1]] = match[2].replace(/^(['"])(.*)\1$/, '$2');
    }
  } catch (error) { if (error.code !== 'ENOENT') throw fail(500, 'configuration_error', 'Unable to read .env.plaid.'); }
  for (const key of ['PLAID_CLIENT_ID', 'PLAID_SECRET', 'PLAID_ENV', 'PLAID_DEMO_PORT']) if (process.env[key] !== undefined) values[key] = process.env[key];
  if ((values.PLAID_ENV || 'sandbox') !== 'sandbox') throw fail(500, 'sandbox_only', 'This connector supports PLAID_ENV=sandbox only.');
  const port = Number(values.PLAID_DEMO_PORT || 4100);
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw fail(500, 'invalid_port', 'Choose a PLAID_DEMO_PORT from 1024 to 65535.');
  return { client_id: values.PLAID_CLIENT_ID, secret: values.PLAID_SECRET, port };
}

async function start() {
  const config = await configuration();
  const origin = `http://127.0.0.1:${config.port}`;
  const configured = Boolean(config.client_id && config.secret);
  async function plaid(endpoint, payload) {
    if (!configured) throw fail(503, 'configuration_required', 'Add your Sandbox client ID and secret to .env.plaid, then restart this server.');
    let response;
    try {
      response = await fetch(`https://sandbox.plaid.com${endpoint}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'Plaid-Version': '2020-09-14' },
        body: JSON.stringify({ client_id: config.client_id, secret: config.secret, ...payload }), signal: AbortSignal.timeout(20000)
      });
    } catch { throw fail(502, 'provider_unavailable', 'Plaid Sandbox is unavailable. Retry when your connection is available.'); }
    let value;
    try { value = await response.json(); }
    catch { throw fail(502, 'invalid_provider_response', 'Plaid returned an unreadable response.'); }
    if (!response.ok || value.error_code) {
      const code = /^[A-Z_]{1,80}$/.test(value.error_code || '') ? value.error_code : 'PROVIDER_ERROR';
      throw fail(502, code, `Plaid Sandbox returned ${code}. No budget change was made.`);
    }
    return value;
  }
  function send(res, status, value) {
    res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    res.end(JSON.stringify(value));
  }
  function session(req, res, create = false) {
    const id = (req.headers.cookie || '').split(';').map((part) => part.trim()).find((part) => part.startsWith('stillhere_plaid_demo='))?.split('=')[1];
    if (id && sessions.has(id)) return sessions.get(id);
    if (!create) throw fail(401, 'session_required', 'Reload this local demo to start its private Sandbox session.');
    if (sessions.size >= 100) throw fail(503, 'session_limit', 'Restart the local demo server to clear its temporary sessions.');
    const value = { id: secretId(), csrf: secretId(), item: null, public_token_hash: null, busy: false };
    sessions.set(value.id, value);
    res.setHeader('Set-Cookie', `stillhere_plaid_demo=${value.id}; HttpOnly; SameSite=Strict; Path=/`);
    return value;
  }
  async function body(req) {
    if (req.headers['content-type']?.split(';')[0].trim() !== 'application/json') throw fail(415, 'json_required', 'Send a JSON request.');
    let text = '';
    for await (const chunk of req) {
      text += chunk.toString('utf8');
      if (Buffer.byteLength(text) > 16384) throw fail(413, 'body_too_large', 'The request is too large.');
    }
    try {
      const value = JSON.parse(text);
      if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
      return value;
    } catch { throw fail(400, 'invalid_json', 'Send a JSON object.'); }
  }
  const accountKey = (item, id) => `plaid_sandbox_${createHash('sha256').update(`${item.id}:${id}`).digest('hex').slice(0, 24)}`;
  function projection(s) {
    return { environment: 'sandbox', configured, csrf: s.csrf, connected: Boolean(s.item), accounts: s.item?.accounts || [], transactions: s.item?.history || [], balances_fetched_at: s.item?.balances_fetched_at || null, transactions_fetched_at: s.item?.transactions_fetched_at || null, transactions_ready: s.item?.transactions_ready || false };
  }
  async function balances(item) {
    const value = await plaid('/accounts/balance/get', { access_token: item.token });
    const now = new Date().toISOString();
    item.accounts = value.accounts.filter((account) => account.type === 'depository' && ['checking', 'savings'].includes(account.subtype)).map((account) => ({
      id: accountKey(item, account.account_id), name: account.name, mask: account.mask,
      currency: account.balances.iso_currency_code, available_cents: cents(account.balances.available), current_cents: cents(account.balances.current), fetched_at: now
    }));
    item.balances_fetched_at = now;
  }
  async function transactions(item) {
    const originalCursor = item.cursor;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      let cursor = originalCursor;
      const staged = new Map(item.records);
      try {
        for (let page = 0; page < 100; page += 1) {
          const value = await plaid('/transactions/sync', { access_token: item.token, ...(cursor ? { cursor } : {}), count: 500 });
          for (const record of [...value.added, ...value.modified]) {
            if (record.pending_transaction_id) staged.delete(record.pending_transaction_id);
            staged.set(record.transaction_id, record);
          }
          for (const record of value.removed) staged.delete(record.transaction_id);
          cursor = value.next_cursor;
          if (!value.has_more) {
            for (const record of staged.values()) if (record.pending_transaction_id) staged.delete(record.pending_transaction_id);
            const allowed = new Set(item.accounts.map((account) => account.id));
            item.history = [...staged.values()].filter((record) => allowed.has(accountKey(item, record.account_id))).map((record) => ({
              id: createHash('sha256').update(record.transaction_id).digest('hex').slice(0, 24), account_id: accountKey(item, record.account_id), date: record.date,
              name: record.merchant_name || record.name, amount_cents: cents(record.amount), currency: record.iso_currency_code, pending: record.pending
            })).sort((a, b) => b.date.localeCompare(a.date)).slice(0, 100);
            item.cursor = cursor;
            item.records = staged;
            item.transactions_fetched_at = new Date().toISOString();
            item.transactions_ready = ['INITIAL_UPDATE_COMPLETE', 'HISTORICAL_UPDATE_COMPLETE'].includes(value.transactions_update_status);
            return;
          }
        }
        throw fail(502, 'pagination_limit', 'The transaction update is too large for this local demo.');
      } catch (error) {
        if (error.code !== 'TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION' || attempt === 2) throw error;
      }
    }
  }
  const server = http.createServer(async (req, res) => {
    try {
      if (req.headers.host !== `127.0.0.1:${config.port}`) throw fail(403, 'invalid_host', 'Use the printed 127.0.0.1 address.');
      const pathname = new URL(req.url, origin).pathname;
      if (pathname.startsWith('/api/plaid/')) {
        if (req.headers.origin && req.headers.origin !== origin) throw fail(403, 'invalid_origin', 'Use the same local origin.');
        const s = session(req, res, req.method === 'GET' && pathname === '/api/plaid/status');
        if (req.method === 'GET' && pathname === '/api/plaid/status') return send(res, 200, projection(s));
        if (req.method !== 'POST' || req.headers.origin !== origin || req.headers['x-stillhere-csrf'] !== s.csrf) throw fail(403, 'invalid_request', 'Reload the local demo before retrying.');
        const value = await body(req);
        if (s.busy) throw fail(409, 'operation_pending', 'A bank operation is already running. Wait for it to finish.');
        s.busy = true;
        try {
          if (pathname === '/api/plaid/link-token') {
            if (s.item) throw fail(409, 'already_connected', 'Disconnect this test bank before connecting another.');
            const token = await plaid('/link/token/create', { user: { client_user_id: s.id }, client_name: 'StillHere Sandbox', products: ['transactions'], country_codes: ['US'], language: 'en', account_filters: { depository: { account_subtypes: ['checking', 'savings'] } } });
            return send(res, 200, { link_token: token.link_token, expiration: token.expiration, environment: 'sandbox' });
          }
          if (pathname === '/api/plaid/exchange') {
            if (typeof value.public_token !== 'string' || !value.public_token.startsWith('public-sandbox-') || value.public_token.length > 512) throw fail(400, 'invalid_public_token', 'A Sandbox public token is required.');
            const fingerprint = createHash('sha256').update(value.public_token).digest('hex');
            if (s.item) {
              if (s.public_token_hash === fingerprint) return send(res, 200, projection(s));
              throw fail(409, 'already_connected', 'A test bank is already connected.');
            }
            const token = await plaid('/item/public_token/exchange', { public_token: value.public_token });
            s.item = { id: token.item_id, token: token.access_token, cursor: null, records: new Map(), accounts: [], history: [] };
            s.public_token_hash = fingerprint;
            return send(res, 200, projection(s));
          }
          if (pathname === '/api/plaid/refresh') {
            if (!s.item) throw fail(409, 'not_connected', 'Connect a test bank first.');
            await balances(s.item);
            await transactions(s.item);
            return send(res, 200, projection(s));
          }
          if (pathname === '/api/plaid/disconnect') {
            if (s.item) await plaid('/item/remove', { access_token: s.item.token });
            s.item = null;
            s.public_token_hash = null;
            return send(res, 200, projection(s));
          }
          throw fail(404, 'route_unavailable', 'This route is unavailable.');
        } finally { s.busy = false; }
      }
      if (req.method !== 'GET') throw fail(405, 'method_unavailable', 'Use GET for frontend files.');
      const file = pathname === '/' ? 'index.html' : pathname.slice(1);
      if (!STATIC.has(file)) throw fail(404, 'file_unavailable', 'This file is unavailable.');
      const content = await fs.readFile(path.join(FRONTEND, file));
      if (file === 'index.html') session(req, res, true);
      res.writeHead(200, { 'Content-Type': file.endsWith('.js') ? 'text/javascript; charset=utf-8' : file.endsWith('.css') ? 'text/css; charset=utf-8' : 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY' });
      res.end(content);
    } catch (error) {
      send(res, error.status || 500, { error: { code: error.code && error.status ? error.code : 'internal_error', message: error.status ? error.message : 'The local connector could not complete this request.' } });
    }
  });
  server.requestTimeout = 30000;
  server.headersTimeout = 10000;
  server.listen(config.port, '127.0.0.1', () => {
    process.stdout.write(`StillHere Plaid Sandbox: ${origin}/#finance\nSandbox credentials configured: ${configured ? 'yes' : 'no'}\n`);
  });
  server.on('error', () => { process.stderr.write('Unable to start the local Plaid server. Check the port and retry.\n'); process.exitCode = 1; });
}

if (require.main === module) start().catch((error) => { process.stderr.write(`${error.status ? error.message : 'Unable to start the local Plaid server.'}\n`); process.exitCode = 1; });
// Built by Raneem Mousa
