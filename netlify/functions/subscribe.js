/**
 * Netlify Function: subscribe to Sender.net list group.
 *
 * REQUIRED ENV (set in Netlify UI → Site settings → Environment variables):
 *   SENDER_API_TOKEN: Sender API bearer token (never commit this)
 * Redeploy after setting the env var so preview/production pick it up.
 */
const LIST_GROUPS = {
  sandcastle: 'ep6n1m',
  // Wolfeboro events list. Same Sender group the site has always used, so
  // existing subscribers stay where they are; only the site's tag changed.
  events: 'bqXo1k',
  // Legacy key: cached pages or old flyers may still post list=oaks.
  oaks: 'bqXo1k',
};

/** Flyer QR tracking group titles by list key (created on first flyer signup if missing). */
const FLYER_QR_GROUP_TITLES = {
  sandcastle: 'Flyer QR',
  oaks: 'Oaks Flyer QR',
  // Reuse the existing tracking group so flyer counts stay in one place.
  events: 'Oaks Flyer QR',
};

const FLYER_SOURCES = new Set(['flyer_qr', 'flyer', 'qr']);

/** In-memory cache of flyer group ids for this function instance (id only, never token). */
const flyerGroupIdCache = Object.create(null);

function corsHeaders(allowedOrigin) {
  const h = {
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    Vary: 'Origin',
  };
  if (allowedOrigin) h['Access-Control-Allow-Origin'] = allowedOrigin;
  return h;
}

function json(statusCode, body, allowedOrigin) {
  return {
    statusCode,
    headers: Object.assign({ 'Content-Type': 'application/json' }, corsHeaders(allowedOrigin)),
    body: JSON.stringify(body),
  };
}

/* ------------------------------------------------------------------ */
/* Abuse protection (added Oct 2026 after direct-POST signup bombing). */
/* ------------------------------------------------------------------ */

/** Production hostnames allowed to post to this function. */
const ALLOWED_HOSTS = new Set([
  'wolfeboroevents.com',
  'www.wolfeboroevents.com',
  'wolfeborostays.com',
  'www.wolfeborostays.com',
  'wolfeborooaks.com',
  'www.wolfeborooaks.com',
  'sandcastletime.net',
  'www.sandcastletime.net',
]);

/** Minimum milliseconds between page load and submit (humans need longer). */
const MIN_ELAPSED_MS = 2500;
/** A page left open longer than this is treated as stale/forged. */
const MAX_ELAPSED_MS = 1000 * 60 * 60 * 24 * 7;

/** Per-IP rate limit. */
const RATE_LIMIT_MAX = 5;
const RATE_LIMIT_WINDOW_MS = 60 * 60 * 1000;

/** Disposable or junk domains seen in the abuse, plus common throwaway providers. */
const BLOCKED_DOMAINS = new Set([
  'sigismail.com',
  'copped-mail.com',
  'example.com',
  'example.org',
  'example.net',
  'test.com',
  'lame.com',
  'mailinator.com',
  'guerrillamail.com',
  'guerrillamail.net',
  'sharklasers.com',
  '10minutemail.com',
  'temp-mail.org',
  'tempmail.com',
  'tempmailo.com',
  'yopmail.com',
  'trashmail.com',
  'getnada.com',
  'dispostable.com',
  'maildrop.cc',
  'throwawaymail.com',
  'fakeinbox.com',
  'mailnesia.com',
  'emailondeck.com',
  'mohmal.com',
  'mintemail.com',
  'spamgourmet.com',
  'grr.la',
]);

/** Common misspellings of big providers (e.g. outlookc.om); reject so people can fix them. */
const TYPO_DOMAINS = new Set([
  'outlookc.om', 'outlok.com', 'outloo.com', 'outlook.co', 'outlook.cm', 'outllook.com',
  'gmial.com', 'gmai.com', 'gmal.com', 'gamil.com', 'gnail.com', 'gmail.co', 'gmail.cm', 'gmailc.om', 'gmail.con',
  'hotmial.com', 'hotmal.com', 'hotmai.com', 'hotmail.co', 'hotmailc.om', 'hotmail.con',
  'yahooo.com', 'yaho.com', 'yahoo.co', 'yahooc.om', 'yahoo.con',
  'iclod.com', 'icloud.co', 'icoud.com', 'aol.co',
]);

function hostOf(value) {
  if (!value) return '';
  try {
    return new URL(String(value)).hostname.toLowerCase();
  } catch {
    return '';
  }
}

function headerOf(event, name) {
  const h = (event && event.headers) || {};
  const lower = name.toLowerCase();
  for (const k of Object.keys(h)) {
    if (k.toLowerCase() === lower) return h[k];
  }
  return '';
}

/** Hosts for this deploy, provided by Netlify at runtime (covers deploy previews). */
function runtimeAllowedHosts() {
  const hosts = new Set();
  ['URL', 'DEPLOY_URL', 'DEPLOY_PRIME_URL'].forEach(function (k) {
    const h = hostOf(process.env[k]);
    if (h) hosts.add(h);
  });
  return hosts;
}

function isAllowedHost(host, event) {
  if (!host) return false;
  if (ALLOWED_HOSTS.has(host)) return true;
  if (runtimeAllowedHosts().has(host)) return true;
  // Netlify deploy previews / branch deploys of THIS site: <anything>--<site>.netlify.app
  const siteName = String(process.env.SITE_NAME || '').toLowerCase();
  if (siteName) {
    if (host === siteName + '.netlify.app') return true;
    if (host.endsWith('--' + siteName + '.netlify.app')) return true;
  }
  // Same-origin: the page and the function are served from the same host.
  const reqHost = String(headerOf(event, 'host') || '').toLowerCase().split(':')[0];
  if (reqHost && host === reqHost && host.endsWith('.netlify.app')) return true;
  return false;
}

/** Returns the allowed origin string, or '' if Origin/Referer is missing or foreign. */
function checkOrigin(event) {
  const origin = headerOf(event, 'origin');
  const referer = headerOf(event, 'referer');
  const host = hostOf(origin) || hostOf(referer);
  if (!isAllowedHost(host, event)) return '';
  return 'https://' + host;
}

function clientIp(event) {
  return (
    headerOf(event, 'x-nf-client-connection-ip') ||
    String(headerOf(event, 'x-forwarded-for') || '').split(',')[0].trim() ||
    'unknown'
  );
}

/** Rate-limit bucket: full IPv4 address, or the /64 prefix for IPv6 (clients rotate within it). */
function ipBucket(ip) {
  const raw = String(ip || 'unknown').trim().toLowerCase();
  if (raw.indexOf(':') === -1) return raw;
  const halves = raw.split('::');
  const head = halves[0] ? halves[0].split(':') : [];
  const tail = halves.length > 1 && halves[1] ? halves[1].split(':') : [];
  const fill = halves.length > 1 ? new Array(Math.max(0, 8 - head.length - tail.length)).fill('0') : [];
  const full = head.concat(fill, tail);
  return full.slice(0, 4).map(function (h) { return h || '0'; }).join(':') + '::/64';
}

function isPlausibleEmail(email) {
  if (typeof email !== 'string') return false;
  const e = email.trim().toLowerCase();
  if (e.length < 6 || e.length > 254) return false;
  if (!/^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.[a-z]{2,24}$/.test(e)) {
    return false;
  }
  const parts = e.split('@');
  const local = parts[0];
  const domain = parts[1];
  if (local.length > 64 || local.startsWith('.') || local.endsWith('.') || local.indexOf('..') !== -1) {
    return false;
  }
  if (BLOCKED_DOMAINS.has(domain)) return false;
  if (TYPO_DOMAINS.has(domain)) return false;
  const labels = domain.split('.');
  for (let i = 1; i < labels.length; i++) {
    if (BLOCKED_DOMAINS.has(labels.slice(i).join('.'))) return false;
  }
  // Generated "name123_surname.1990@" / "name123.surname_1990@" pattern seen from the bot
  if (/^[a-z]+\d{2,4}[._][a-z]+[._](19|20)\d{2}$/.test(local)) return false;
  // Long random-looking strings with no vowels
  if (local.length >= 12 && !/[aeiouy]/.test(local)) return false;
  return true;
}

/** Fallback in-memory limiter (per function instance) if Blobs is unavailable. */
const memoryHits = Object.create(null);

function memoryRateLimited(ip, now) {
  const arr = (memoryHits[ip] || []).filter(function (t) {
    return now - t < RATE_LIMIT_WINDOW_MS;
  });
  arr.push(now);
  memoryHits[ip] = arr;
  return arr.length > RATE_LIMIT_MAX;
}

/** Per-IP limit backed by Netlify Blobs (free, no new service). Fails open on error. */
async function isRateLimited(event, ip) {
  const now = Date.now();
  if (memoryRateLimited(ip, now)) return true;
  try {
    const blobs = require('@netlify/blobs');
    if (blobs.connectLambda) blobs.connectLambda(event);
    const store = blobs.getStore('signup-rate-limit');
    const key = ip.replace(/[^a-zA-Z0-9.:_-]/g, '_');
    // One small blob per attempt, then count this IP's attempts in the window.
    // (list() reads are not edge-cached, so recent writes are counted.)
    await store.set(key + '/' + now, '1');
    const listed = await store.list({ prefix: key + '/' });
    const recent = (listed.blobs || [])
      .map(function (b) {
        return Number(String(b.key).split('/').pop());
      })
      .filter(function (t) {
        return Number.isFinite(t) && now - t < RATE_LIMIT_WINDOW_MS;
      });
    // Best-effort cleanup of this IP's expired entries.
    (listed.blobs || []).forEach(function (b) {
      const t = Number(String(b.key).split('/').pop());
      if (Number.isFinite(t) && now - t >= RATE_LIMIT_WINDOW_MS) store.delete(b.key).catch(function () {});
    });
    return recent.length > RATE_LIMIT_MAX;
  } catch (err) {
    console.log(JSON.stringify({ event: 'rate_limit', action: 'blobs_unavailable' }));
    return false;
  }
}

/* Cloudflare Turnstile. Enforced only when TURNSTILE_SECRET_KEY is set. */
async function verifyTurnstile(token, ip) {
  const secret = process.env.TURNSTILE_SECRET_KEY;
  if (!secret) {
    console.log(JSON.stringify({ event: 'turnstile', action: 'skipped_no_secret' }));
    return true;
  }
  if (!token || typeof token !== 'string' || token.length > 2048) return false;
  try {
    const form = new URLSearchParams();
    form.append('secret', secret);
    form.append('response', token);
    if (ip && ip !== 'unknown') form.append('remoteip', ip);
    const res = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
      method: 'POST',
      body: form,
    });
    const out = await res.json();
    if (!out || out.success !== true) {
      console.log(JSON.stringify({ event: 'turnstile', action: 'failed', codes: (out && out['error-codes']) || [] }));
      return false;
    }
    return true;
  } catch (err) {
    // Cloudflare unreachable: fail open so real signups keep working; other checks still apply.
    console.log(JSON.stringify({ event: 'turnstile', action: 'verify_error' }));
    return true;
  }
}

function logBlocked(reason, event, extra) {
  console.log(
    JSON.stringify(
      Object.assign(
        {
          event: 'signup_blocked',
          reason: reason,
          ip: clientIp(event),
          origin: headerOf(event, 'origin') || null,
          ua: String(headerOf(event, 'user-agent') || '').slice(0, 120),
        },
        extra || {}
      )
    )
  );
}

function senderHeaders(token) {
  return {
    Authorization: 'Bearer ' + token,
    Accept: 'application/json',
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (compatible; GrokBot/1.0)',
  };
}

function normalizeSource(data, query) {
  const raw =
    (data && (data.source || data.src)) ||
    (query && (query.source || query.src)) ||
    '';
  return String(raw).trim().toLowerCase();
}

/**
 * Page path the signup came from (hidden "page" field), e.g. "/port-townsend/".
 * Only a plain site path is kept; anything else is dropped.
 */
function normalizePage(data) {
  // Explicit short tag (e.g. "sign" from /wolfeboro/join/) wins over the path.
  const tag = String((data && data.source_page) || '').trim().toLowerCase();
  if (/^[a-z0-9_-]{1,40}$/.test(tag)) return tag;
  const raw = String((data && data.page) || '').trim().slice(0, 120);
  if (!raw || raw.charAt(0) !== '/' || raw.indexOf('//') === 0) return '';
  if (!/^[A-Za-z0-9/_.~-]+$/.test(raw)) return '';
  return raw;
}

/** Sender custom field (personalization tag) that stores the signup page. */
const SOURCE_PAGE_FIELD = '{$source_page}';

function isFlyerSource(source) {
  if (!source) return false;
  if (FLYER_SOURCES.has(source)) return true;
  return source.indexOf('flyer') !== -1;
}

function extractGroups(payload) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload.data)) return payload.data;
  if (payload.data && Array.isArray(payload.data.data)) return payload.data.data;
  if (Array.isArray(payload.groups)) return payload.groups;
  return [];
}

function groupTitle(g) {
  return String((g && (g.title || g.name)) || '').trim();
}

function groupIdOf(g) {
  if (!g) return null;
  const id = g.id != null ? g.id : g.group_id;
  return id != null ? String(id) : null;
}

async function findOrCreateFlyerQrGroup(token, listKey) {
  const title = FLYER_QR_GROUP_TITLES[listKey];
  if (!title) return null;
  if (flyerGroupIdCache[listKey]) return flyerGroupIdCache[listKey];

  const headers = senderHeaders(token);

  // Prefer: GET /v2/groups and find by title
  let page = 1;
  const maxPages = 10;
  while (page <= maxPages) {
    const listRes = await fetch(
      'https://api.sender.net/v2/groups?limit=100&page=' + page,
      { method: 'GET', headers }
    );
    if (!listRes.ok) break;
    const body = await listRes.json();
    const groups = extractGroups(body);
    const existing = groups.find(function (g) {
      return groupTitle(g) === title;
    });
    if (existing) {
      const id = groupIdOf(existing);
      if (id) {
        flyerGroupIdCache[listKey] = id;
        console.log(
          JSON.stringify({
            event: 'flyer_qr_group',
            action: 'found',
            list: listKey,
            id: id,
            title: title,
          })
        );
        return id;
      }
    }
    if (groups.length < 100) break;
    page += 1;
  }

  // Else create
  const createRes = await fetch('https://api.sender.net/v2/groups', {
    method: 'POST',
    headers,
    body: JSON.stringify({ title: title }),
  });
  if (!createRes.ok) {
    console.log(
      JSON.stringify({
        event: 'flyer_qr_group',
        action: 'create_failed',
        list: listKey,
        title: title,
        status: createRes.status,
      })
    );
    return null;
  }
  const created = await createRes.json();
  const createdObj = created && (created.data || created);
  const id = groupIdOf(createdObj);
  if (id) {
    flyerGroupIdCache[listKey] = id;
    console.log(
      JSON.stringify({
        event: 'flyer_qr_group',
        action: 'created',
        list: listKey,
        id: id,
        title: title,
      })
    );
    return id;
  }
  console.log(
    JSON.stringify({
      event: 'flyer_qr_group',
      action: 'create_no_id',
      list: listKey,
      title: title,
    })
  );
  return null;
}

exports.handler = async (event) => {
  const allowedOrigin = checkOrigin(event);

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers: corsHeaders(allowedOrigin), body: '' };
  }

  if (event.httpMethod !== 'POST') {
    return json(405, { ok: false, error: 'Method not allowed' }, allowedOrigin);
  }

  // 1. Origin / Referer allowlist: direct hits (curl, scripts) carry neither.
  if (!allowedOrigin) {
    logBlocked('origin', event);
    return json(403, { ok: false, error: 'Forbidden' });
  }

  let data;
  try {
    data = JSON.parse(event.body || '{}');
  } catch {
    return json(400, { ok: false, error: 'Invalid JSON' }, allowedOrigin);
  }
  if (!data || typeof data !== 'object') data = {};

  // 2. Honeypot: pretend success for bots, add nothing.
  if (data.website || data.company) {
    logBlocked('honeypot', event);
    return json(200, { ok: true }, allowedOrigin);
  }

  // 3. Time-to-submit: the page stamps a hidden ts on load and sends elapsed ms.
  const elapsed = Number(data.elapsed);
  const ts = Number(data.ts);
  if (!ts || !Number.isFinite(elapsed) || elapsed < MIN_ELAPSED_MS || elapsed > MAX_ELAPSED_MS) {
    logBlocked('timing', event, { elapsed: Number.isFinite(elapsed) ? elapsed : null });
    return json(200, { ok: true }, allowedOrigin);
  }

  // 4. Per-IP rate limit (Netlify Blobs, with in-memory fallback).
  const ip = clientIp(event);

  // 4b. Cloudflare Turnstile (skipped with a warning until the secret is configured).
  if (!(await verifyTurnstile(data.turnstile, ip))) {
    logBlocked('turnstile', event);
    return json(403, { ok: false, error: 'Verification failed' }, allowedOrigin);
  }
  if (await isRateLimited(event, ipBucket(ip))) {
    logBlocked('rate_limit', event);
    return json(429, { ok: false, error: 'Too many requests' }, allowedOrigin);
  }

  const email = String(data.email || '').trim();
  const listKey = String(
    data.list || (event.queryStringParameters && event.queryStringParameters.list) || ''
  ).toLowerCase();
  const groupId = LIST_GROUPS[listKey];
  const source = normalizeSource(data, event.queryStringParameters);
  const page = normalizePage(data);

  if (!groupId) {
    return json(400, { ok: false, error: 'Invalid list' }, allowedOrigin);
  }

  // 5. Email format plus disposable / generated-pattern rejection.
  if (!isPlausibleEmail(email)) {
    logBlocked('email', event, { domain: email.split('@')[1] || null });
    return json(400, { ok: false, error: 'Invalid email' }, allowedOrigin);
  }

  const token = process.env.SENDER_API_TOKEN;
  if (!token) {
    return json(500, { ok: false, error: 'Server not configured' }, allowedOrigin);
  }

  const groups = [groupId];

  // Flyer QR: also add to tracking group (website source stays on list group only)
  if (isFlyerSource(source) && FLYER_QR_GROUP_TITLES[listKey]) {
    try {
      const flyerId = await findOrCreateFlyerQrGroup(token, listKey);
      if (flyerId && flyerId !== groupId && groups.indexOf(flyerId) === -1) {
        groups.push(flyerId);
      }
    } catch {
      console.log(
        JSON.stringify({
          event: 'flyer_qr_group',
          action: 'error',
          list: listKey,
        })
      );
    }
  }

  const payload = {
    email: email.toLowerCase(),
    groups,
    trigger_automation: true,
  };

  const firstname = data.firstname != null ? String(data.firstname).trim() : '';
  const lastname = data.lastname != null ? String(data.lastname).trim() : '';
  if (firstname) payload.firstname = firstname;
  if (lastname) payload.lastname = lastname;

  // Signup page goes in a Sender custom field. If Sender rejects the request
  // with the field (e.g. the field does not exist), retry once without it so
  // the signup itself never fails because of tracking.
  if (page) payload.fields = { [SOURCE_PAGE_FIELD]: page };

  try {
    let res = await fetch('https://api.sender.net/v2/subscribers', {
      method: 'POST',
      headers: senderHeaders(token),
      body: JSON.stringify(payload),
    });

    if (!res.ok && payload.fields && res.status !== 409 && res.status !== 401 && res.status !== 429) {
      let detail = '';
      try {
        detail = (await res.text()).slice(0, 200);
      } catch {}
      console.log(JSON.stringify({ event: 'source_page_field_rejected', list: listKey, status: res.status, detail: detail }));
      delete payload.fields;
      res = await fetch('https://api.sender.net/v2/subscribers', {
        method: 'POST',
        headers: senderHeaders(token),
        body: JSON.stringify(payload),
      });
    } else if (res.ok && payload.fields) {
      console.log(JSON.stringify({ event: 'source_page_saved', list: listKey, page: page }));
    }

    if (!res.ok) {
      // Already subscribed / validation conflict: treat as success for UX
      if (res.status === 422 || res.status === 409) {
        return json(200, { ok: true, source: source || null }, allowedOrigin);
      }
      return json(502, { ok: false, error: 'Subscription failed' }, allowedOrigin);
    }

    return json(200, { ok: true, source: source || null }, allowedOrigin);
  } catch {
    return json(502, { ok: false, error: 'Subscription failed' }, allowedOrigin);
  }
};
