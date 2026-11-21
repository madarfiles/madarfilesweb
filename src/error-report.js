// Automatic error reports: when something fails, the technical details (tool, message, code and
// the support log, with links removed) go to Madar's server log so problems are found without
// screenshots. No files, names typed by the visitor or Google tokens are sent. At most five
// different reports per page visit.
const SENT = new Set(); let count = 0;
export const LIMIT = 5;

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
    const body = JSON.stringify(reportBody(kind, detail));
    fetch('/api/report', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body, keepalive: body.length < 60000}).catch(() => {});
  } catch {}
}

export function watchErrors() {
  addEventListener('error', e => { if (e.message) report('error', {message: e.message, stage: String(e.filename || '').split('/').pop() + ':' + e.lineno}); });
  addEventListener('unhandledrejection', e => {
    const r = e.reason; if (r?.name === 'AbortError') return;
    report('rejection', {message: r?.message || String(r)});
  });
}
