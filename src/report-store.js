// Error reports are kept in Netlify Blobs for 90 days so problems can be looked at long after the
// function log has rotated. Reading them back needs no stored password: the request must carry a
// short-lived identity token that GitHub issues only to workflows of the madarfiles/madarfilesweb
// repository (the "Read error reports" action).
export const KEEP_DAYS = 90, PER_DAY = 5000;
export const READ_AUDIENCE = 'madarfiles-reports', READ_REPO = 'madarfiles/madarfilesweb';
const ISSUER = 'https://token.actions.githubusercontent.com';

const day = now => new Date(now).toISOString().slice(0, 10);

export async function keepReport(store, report, {now = Date.now(), random = Math.random} = {}) {
  const d = day(now), countKey = 'n/' + d;
  const seen = Number(await store.get(countKey).catch(() => 0)) || 0;
  if (seen >= PER_DAY) return false;
  await store.set(countKey, String(seen + 1));
  await store.setJSON('r/' + d + '/' + new Date(now).toISOString().slice(11, 23) + '-' + random().toString(36).slice(2, 8), report);
  // Now and then, clear out days past the keeping period.
  if (random() < 0.02) await pruneReports(store, now).catch(() => {});
  return true;
}

export async function pruneReports(store, now = Date.now()) {
  const oldest = day(now - KEEP_DAYS * 864e5);
  for (const prefix of ['r/', 'n/']) {
    const {blobs = []} = await store.list({prefix});
    for (const b of blobs) if (b.key.slice(prefix.length, prefix.length + 10) < oldest) await store.delete(b.key);
  }
}

export async function listReports(store, {days = 7, now = Date.now(), limit = 2000} = {}) {
  const out = [];
  for (let i = 0; i < Math.min(Math.max(1, days), KEEP_DAYS) && out.length < limit; i++) {
    const {blobs = []} = await store.list({prefix: 'r/' + day(now - i * 864e5) + '/'});
    for (const b of blobs.sort((a, z) => z.key.localeCompare(a.key))) {
      if (out.length >= limit) break;
      const r = await store.get(b.key, {type: 'json'}).catch(() => null);
      if (r) out.push({id: b.key.slice(2), ...r});
    }
  }
  return out;
}

const b64url = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4)), c => c.charCodeAt(0));
let jwksCache = null;

// Checks a GitHub Actions identity token: signature (GitHub's published keys), issuer, audience,
// repository and expiry. Returns the claims, or null.
export async function verifyGithubToken(token, {fetcher = fetch, now = Date.now()} = {}) {
  try {
    const [h, p, sig] = String(token || '').split('.');
    if (!sig) return null;
    const header = JSON.parse(new TextDecoder().decode(b64url(h))), claims = JSON.parse(new TextDecoder().decode(b64url(p)));
    if (header.alg !== 'RS256' || claims.iss !== ISSUER || claims.aud !== READ_AUDIENCE || claims.repository !== READ_REPO) return null;
    if (!(claims.exp * 1000 > now) || claims.nbf * 1000 > now + 60e3) return null;
    if (!jwksCache || jwksCache.at < now - 3600e3) jwksCache = {at: now, keys: (await (await fetcher(ISSUER + '/.well-known/jwks')).json()).keys};
    const jwk = jwksCache.keys.find(k => k.kid === header.kid);
    if (!jwk) return null;
    const key = await crypto.subtle.importKey('jwk', {kty: 'RSA', n: jwk.n, e: jwk.e, alg: 'RS256', ext: true}, {name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256'}, false, ['verify']);
    const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64url(sig), new TextEncoder().encode(h + '.' + p));
    return ok ? claims : null;
  } catch { return null; }
}
