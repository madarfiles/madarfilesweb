import test from 'node:test';
import assert from 'node:assert/strict';
import {fastTicket, fastRedeem, FAST_LIMITS} from '../src/fast-lane.js';
import {createPublicHandler} from '../src/netlify-public-server.js';
import {readFileSync} from 'node:fs';

function memory() {
 const m = new Map();
 return {m, async get(k) { return m.has(k) ? JSON.parse(m.get(k)) : null; }, async setJSON(k, v) { m.set(k, JSON.stringify(v)); }, async delete(k) { m.delete(k); }};
}

test('fast lane: tickets per visitor and per day, used once, expire', async () => {
 const store = memory(), now = Date.UTC(2026, 10, 25, 8);
 const limits = {perVisitor: 2, perDay: 3, ticketMs: 1000};
 const a1 = await fastTicket({tool: 'separate'}, store, {ip: '1.1.1.1', now, limits});
 assert.equal(a1[1].ok, true); assert.match(a1[1].ticket, /^[a-f0-9]{48}$/); assert.equal(a1[1].left, 1);
 assert.equal((await fastTicket({tool: 'separate'}, store, {ip: '1.1.1.1', now, limits}))[1].ok, true);
 assert.deepEqual((await fastTicket({tool: 'separate'}, store, {ip: '1.1.1.1', now, limits}))[1], {ok: false, reason: 'visitor', limit: 2});
 assert.equal((await fastTicket({tool: 'separate'}, store, {ip: '2.2.2.2', now, limits}))[1].ok, true);
 assert.equal((await fastTicket({tool: 'separate'}, store, {ip: '3.3.3.3', now, limits}))[1].reason, 'site');
 assert.equal((await fastTicket({tool: 'separate'}, store, {ip: '1.1.1.1', now: now + 86400e3, limits}))[1].ok, true, 'a new day resets');
 assert.equal((await fastTicket({tool: 'other'}, store, {ip: '1.1.1.1', now, limits}))[0], 400);
 assert.equal([...store.m.keys()].some(k => k.includes('1.1.1.1')), false, 'no raw address stored');
 assert.deepEqual(await fastRedeem({ticket: a1[1].ticket}, store, {now}), [200, {ok: true, tool: 'separate'}]);
 assert.equal((await fastRedeem({ticket: a1[1].ticket}, store, {now}))[0], 403, 'used once');
 const late = await fastTicket({tool: 'separate'}, store, {ip: '9.9.9.9', now: now + 86400e3, limits});
 assert.equal((await fastRedeem({ticket: late[1].ticket}, store, {now: now + 86400e3 + 5000}))[0], 403, 'expired');
 assert.equal((await fastRedeem({ticket: 'nope'}, store))[0], 400);
 assert.equal(FAST_LIMITS.perVisitor, 20);
});

test('public handler: error reports are logged, fast routes work, ticket needs same origin', async () => {
 const store = memory(), handler = createPublicHandler({fastStore: store});
 const logs = []; const orig = console.log; console.log = (...a) => logs.push(a.join(' '));
 try {
  const r = await handler(new Request('https://madar.test/api/report', {method: 'POST', headers: {Origin: 'https://madar.test', 'Content-Type': 'application/json'}, body: JSON.stringify({kind: 'error', tool: 'separate', message: 'x'})}));
  assert.equal(r.status, 204);
 } finally { console.log = orig; }
 assert.ok(logs.some(l => l.startsWith('MADAR_REPORT ')));
 const cross = await handler(new Request('https://madar.test/api/fast/ticket', {method: 'POST', headers: {Origin: 'https://evil.test'}, body: '{"tool":"separate"}'}), {ip: '5.5.5.5'});
 assert.equal(cross.status, 403);
 const ok = await (await handler(new Request('https://madar.test/api/fast/ticket', {method: 'POST', headers: {Origin: 'https://madar.test'}, body: '{"tool":"separate"}'}), {ip: '5.5.5.5'})).json();
 assert.equal(ok.ok, true);
 const redeem = await handler(new Request('https://madar.test/api/fast/redeem', {method: 'POST', body: JSON.stringify({ticket: ok.ticket})}));
 assert.equal(redeem.status, 200);
 assert.equal((await createPublicHandler({})(new Request('https://madar.test/api/fast/ticket', {method: 'POST', headers: {Origin: 'https://madar.test'}, body: '{"tool":"separate"}'}), {ip: '1'})).status, 200);
});

test('fast lane wiring: CSP allows the Modal endpoint, privacy explains it, workflow uses secrets', () => {
 assert.match(readFileSync('src/headers.json', 'utf8'), /connect-src[^"]*https:\/\/madarfiles-app--madar-fast\.modal\.run/);
 assert.match(readFileSync('src/privacy.html', 'utf8'), /Modal/);
 const wf = readFileSync('.github/workflows/modal.yml', 'utf8');
 assert.match(wf, /secrets\.MODAL_TOKEN_ID/); assert.match(wf, /secrets\.MODAL_TOKEN_SECRET/);
 assert.match(readFileSync('modal/madar_fast.py', 'utf8'), /\/api\/fast\/redeem/);
});
