// Automatic error reports: when something fails, the technical details (tool, message, code and
// the support log, with links removed) go to Madar's server log so problems are found without
// screenshots. No files, names typed by the visitor or Google tokens are sent. At most fifteen
// different reports per page visit; the server keeps them for 90 days.
const SENT = new Set(); let count = 0;
export const LIMIT = 15;

export function scrub(text, max) {
  return String(text ?? '').replace(/https?:\/\/\S+/g, '[رابط]').replace(/ya29\.[\w.-]+/g, '[token]').replace(/[\u0000-\u0008\u000b-\u001f]/g, ' ').slice(-max);
}

export function reportBody(kind, detail = {}) {
  return {kind: scrub(kind, 20), tool: scrub(detail.tool, 40), message: scrub(detail.message, 300), code: scrub(detail.code, 60),
    status: Number(detail.status) || 0, stage: scrub(detail.stage, 120), log: scrub(detail.log, 4000),
    page: scrub(location.pathname, 60), ua: scrub(navigator.userAgent, 200), at: new Date().toISOString()};
}

export function report(kind, detail = {}) {
  try {
    if (count >= LIMIT) return;
    const key = kind + '|' + String(detail.tool || '') + '|' + String(detail.message || '').slice(0, 120);
    if (SENT.has(key)) return;
    SENT.add(key); count++;
    return send(JSON.stringify(reportBody(kind, detail)));
  } catch {}
  return Promise.resolve(false);
}

// A report must not get lost on a weak phone connection: an ordinary request first (keepalive
// only while the page is closing, because some phones drop keepalive requests), one retry, and
// finally the browser's beacon.
async function send(body) {
  const post = keepalive => fetch('/api/report', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body, keepalive, cache: 'no-store'});
  for (let attempt = 0; attempt < 2; attempt++) {
    try { const r = await post(document.visibilityState === 'hidden' && body.length < 60000); if (r.ok || r.status < 500) return true; } catch {}
    await new Promise(done => setTimeout(done, 2000));
  }
  try { return navigator.sendBeacon?.('/api/report', new Blob([body], {type: 'application/json'})) || false; } catch { return false; }
}

export function watchErrors() {
  addEventListener('error', e => {
    if (e.message) { report('error', {message: e.message, stage: String(e.filename || '').split('/').pop() + ':' + e.lineno + ':' + (e.colno || 0), log: String(e.error?.stack || '')}); return; }
    // A script, style, font or image of the page itself that failed to load.
    const t = e.target, src = t?.src || t?.href;
    if (t && t !== window && src && new URL(src, location.href).origin === location.origin) report('load', {message: (t.tagName || '').toLowerCase() + ' ' + new URL(src, location.href).pathname});
  }, true);
  // Madar's own server answering with an error, or not answering at all.
  const plain = window.fetch?.bind(window);
  if (plain && !plain.madarWatched) {
    const watched = async (input, init) => {
      const url = typeof input === 'string' ? input : input?.url || '';
      const path = url.startsWith('/') ? url : (() => { try { const u = new URL(url); return u.origin === location.origin ? u.pathname : (u.hostname.endsWith('.modal.run') ? 'modal' + u.pathname.replace(/fc-[\w]+/, 'fc-…') : ''); } catch { return ''; } })();
      const mine = path.startsWith('/api/') && !path.startsWith('/api/report') || path.startsWith('modal');
      try {
        const r = await plain(input, init);
        if (mine && r.status >= 500) report('api', {message: 'HTTP ' + r.status + ' ' + path.split('?')[0], status: r.status});
        return r;
      } catch (err) {
        if (mine && err?.name !== 'AbortError') report('api', {message: 'لا يوجد رد · ' + path.split('?')[0] + ' · ' + (err?.message || ''), code: navigator.onLine === false ? 'offline' : ''});
        throw err;
      }
    };
    watched.madarWatched = true; window.fetch = watched;
  }
  addEventListener('unhandledrejection', e => {
    const r = e.reason; if (r?.name === 'AbortError') return;
    report('rejection', {message: r?.message || String(r)});
  });
}
