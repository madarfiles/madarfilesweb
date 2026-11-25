// Fast lane (Modal GPU) tickets. The site decides who may use the paid GPU: each visitor gets a
// few jobs a day and the whole site has a daily ceiling, so the monthly free credit cannot be
// drained. A ticket is random, used once and expires quickly; the Modal app redeems it here
// before doing any work. Only a salted hash of the visitor's address is stored, for one day.
export const FAST_ENDPOINT = 'https://madarfiles-app--madar-fast.modal.run';
export const FAST_LIMITS = {perVisitor: 5, perDay: 60, ticketMs: 15 * 60e3};
const TOOLS = new Set(['separate']);

const hex = bytes => Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
const day = now => new Date(now).toISOString().slice(0, 10);
async function visitorKey(ip, now) {
 return hex(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode('madar-fast|' + day(now) + '|' + ip)))).slice(0, 32);
}
const read = async (store, key) => { try { return (await store.get(key, {type: 'json'})) || null; } catch { return null; } };

export async function fastTicket(body, store, {ip = '', now = Date.now(), limits = FAST_LIMITS, endpoint = FAST_ENDPOINT} = {}) {
 if (!TOOLS.has(body?.tool)) return [400, {ok: false, reason: 'tool'}];
 if (!ip) return [200, {ok: false, reason: 'unknown'}];
 const d = day(now), visitor = 'v/' + d + '/' + await visitorKey(ip, now), total = 'd/' + d;
 const [mine, all] = await Promise.all([read(store, visitor), read(store, total)]);
 if ((mine?.n || 0) >= limits.perVisitor) return [200, {ok: false, reason: 'visitor', limit: limits.perVisitor}];
 if ((all?.n || 0) >= limits.perDay) return [200, {ok: false, reason: 'site'}];
 const ticket = hex(crypto.getRandomValues(new Uint8Array(24)));
 await store.setJSON('t/' + ticket, {exp: now + limits.ticketMs, tool: body.tool});
 await Promise.all([store.setJSON(visitor, {n: (mine?.n || 0) + 1}), store.setJSON(total, {n: (all?.n || 0) + 1})]);
 return [200, {ok: true, ticket, endpoint, left: limits.perVisitor - (mine?.n || 0) - 1}];
}

export async function fastRedeem(body, store, {now = Date.now()} = {}) {
 const ticket = body?.ticket;
 if (typeof ticket !== 'string' || !/^[a-f0-9]{48}$/.test(ticket)) return [400, {ok: false}];
 const saved = await read(store, 't/' + ticket);
 if (!saved) return [403, {ok: false}];
 await store.delete('t/' + ticket);
 if (saved.exp < now) return [403, {ok: false}];
 return [200, {ok: true, tool: saved.tool}];
}
