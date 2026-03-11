// Webby — Cloudflare Pages Worker
// Handles QR scan tracking via KV and serves static assets
//
// KV namespace binding: SCANS (must be created and bound in Cloudflare dashboard)
// Fallback: if KV not bound, logs are lost but site still works

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // ── POST /api/track — log a QR scan ──
    if (url.pathname === '/api/track' && request.method === 'POST') {
      return handleTrack(request, env);
    }

    // ── GET /api/scans — list all scans (for admin dashboard) ──
    if (url.pathname === '/api/scans' && request.method === 'GET') {
      return handleGetScans(request, env);
    }

    // ── GET /api/scans/csv — export as CSV ──
    if (url.pathname === '/api/scans/csv' && request.method === 'GET') {
      return handleExportCSV(request, env);
    }

    // ── GET /api/scans/:slug — list full scan history for one business ──
    if (url.pathname.startsWith('/api/scans/') && request.method === 'GET') {
      return handleGetScanDetail(request, env);
    }

    // ── Everything else: serve static assets ──
    return env.ASSETS.fetch(request);
  }
};

const API_KEY = 'sold2move2026';
const LOCAL_TIMEZONE = 'America/Toronto';

function formatLocalTime(ts) {
  return new Date(ts).toLocaleString('en-US', {
    timeZone: LOCAL_TIMEZONE,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });
}

function buildTimestampFields(ts) {
  return {
    ts,
    iso: new Date(ts).toISOString(),
    local: formatLocalTime(ts),
  };
}

function parseLegacyTimestamp(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value !== 'string' || value.trim() === '') {
    return null;
  }

  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function normalizeIndexEntry(data) {
  const firstTs = parseLegacyTimestamp(data.first_scan_ts ?? data.first_scan);
  const lastTs = parseLegacyTimestamp(data.last_scan_ts ?? data.last_scan);

  return {
    count: data.count || 0,
    first_scan_ts: firstTs,
    first_scan_iso: firstTs ? new Date(firstTs).toISOString() : null,
    first_scan: firstTs ? formatLocalTime(firstTs) : (data.first_scan_local || data.first_scan || 'Unknown'),
    last_scan_ts: lastTs,
    last_scan_iso: lastTs ? new Date(lastTs).toISOString() : null,
    last_scan: lastTs ? formatLocalTime(lastTs) : (data.last_scan_local || data.last_scan || 'Unknown'),
  };
}

function normalizeScanEntry(entry) {
  const ts = parseLegacyTimestamp(entry.ts ?? entry.iso ?? entry.date);

  return {
    ts,
    iso: ts ? new Date(ts).toISOString() : null,
    local: ts ? formatLocalTime(ts) : (entry.local || entry.date || 'Unknown'),
    ua: entry.ua || '',
    ref: entry.ref || 'dm',
  };
}

function isAuthorized(request) {
  const url = new URL(request.url);
  return url.searchParams.get('key') === API_KEY;
}


async function handleTrack(request, env) {
  try {
    const data = await request.json();
    const slug = data.slug || 'unknown';
    const ref = data.ref || 'organic';
    const ts = data.ts || Date.now();
    const ua = data.ua || '';

    // Only track QR scans (ref=dm) — ignore organic visits for the scan log
    if (ref !== 'dm') {
      return new Response('ok', { status: 200 });
    }

    if (!env.SCANS) {
      // KV not bound yet — silently accept
      return new Response('ok', { status: 200 });
    }

    // Read existing scans for this slug
    const key = `scan:${slug}`;
    const existing = await env.SCANS.get(key, 'json') || [];

    const timestamp = buildTimestampFields(ts);
    existing.push({
      ts: timestamp.ts,
      iso: timestamp.iso,
      local: timestamp.local,
      ua: ua.substring(0, 200),
      ref: ref,
    });

    // Store (keep last 50 scans per business)
    await env.SCANS.put(key, JSON.stringify(existing.slice(-50)));

    // Also update the master scan index
    const indexKey = 'scan_index';
    const index = await env.SCANS.get(indexKey, 'json') || {};
    if (!index[slug]) {
      index[slug] = {
        first_scan_ts: timestamp.ts,
        first_scan_iso: timestamp.iso,
        first_scan_local: timestamp.local,
        count: 0,
      };
    }
    index[slug].count = (index[slug].count || 0) + 1;
    index[slug].last_scan_ts = timestamp.ts;
    index[slug].last_scan_iso = timestamp.iso;
    index[slug].last_scan_local = timestamp.local;
    await env.SCANS.put(indexKey, JSON.stringify(index));

    return new Response('ok', { status: 200 });
  } catch (e) {
    return new Response('error', { status: 200 }); // Don't break the site
  }
}


async function handleGetScans(request, env) {
  // Simple auth — prevent random people from viewing scan data
  if (!isAuthorized(request)) {
    return new Response(JSON.stringify({ error: 'unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  if (!env.SCANS) {
    return new Response(JSON.stringify({ error: 'KV not bound', scans: {} }), {
      headers: { 'Content-Type': 'application/json' }
    });
  }

  const index = await env.SCANS.get('scan_index', 'json') || {};
  const normalizedIndex = Object.fromEntries(
    Object.entries(index).map(([slug, data]) => [slug, normalizeIndexEntry(data)])
  );

  return new Response(JSON.stringify({ scans: normalizedIndex }), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache'
    }
  });
}

async function handleGetScanDetail(request, env) {
  if (!isAuthorized(request)) {
    return new Response(JSON.stringify({ error: 'unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  if (!env.SCANS) {
    return new Response(JSON.stringify({ error: 'KV not bound', scans: [] }), {
      headers: { 'Content-Type': 'application/json' }
    });
  }

  const url = new URL(request.url);
  const slug = decodeURIComponent(url.pathname.replace('/api/scans/', '')).trim();
  if (!slug) {
    return new Response(JSON.stringify({ error: 'missing slug', scans: [] }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  const index = await env.SCANS.get('scan_index', 'json') || {};
  const history = await env.SCANS.get(`scan:${slug}`, 'json') || [];
  const scans = history
    .map(normalizeScanEntry)
    .sort((a, b) => (b.ts || 0) - (a.ts || 0));

  return new Response(JSON.stringify({
    slug,
    summary: normalizeIndexEntry(index[slug] || { count: scans.length }),
    scans,
  }), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache'
    }
  });
}


async function handleExportCSV(request, env) {
  if (!isAuthorized(request)) {
    return new Response('unauthorized', { status: 401 });
  }

  if (!env.SCANS) {
    return new Response('slug,first_scan_local,first_scan_iso,last_scan_local,last_scan_iso,total_scans\n', {
      headers: {
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename="qr_scans.csv"'
      }
    });
  }

  const index = await env.SCANS.get('scan_index', 'json') || {};

  let csv = 'slug,first_scan_local,first_scan_iso,last_scan_local,last_scan_iso,total_scans\n';
  for (const [slug, data] of Object.entries(index)) {
    const normalized = normalizeIndexEntry(data);
    csv += `${slug},${normalized.first_scan},${normalized.first_scan_iso || ''},${normalized.last_scan},${normalized.last_scan_iso || ''},${normalized.count}\n`;
  }

  return new Response(csv, {
    headers: {
      'Content-Type': 'text/csv',
      'Content-Disposition': 'attachment; filename="qr_scans.csv"'
    }
  });
}
