import test from 'node:test';
import assert from 'node:assert/strict';
import {keepReport, listReports, pruneReports, verifyGithubToken, PER_DAY} from '../src/report-store.js';
import {createPublicHandler} from '../src/netlify-public-server.js';

const memory = () => { const m = new Map(); return {m,
  get: async (k, o) => m.has(k) ? (o?.type === 'json' ? JSON.parse(m.get(k)) : m.get(k)) : null,
  set: async (k, v) => { m.set(k, v); }, setJSON: async (k, v) => { m.set(k, JSON.stringify(v)); },
  delete: async k => { m.delete(k); }, list: async ({prefix}) => ({blobs: [...m.keys()].filter(k => k.startsWith(prefix)).map(key => ({key}))})}; };

test('reports: kept by day, listed newest first, old days pruned, daily ceiling', async () => {
  const s = memory(), t = Date.parse('2026-11-26T10:00:00Z');
  await keepReport(s, {kind: 'error', message: 'a'}, {now: t, random: () => 0.5});
  await keepReport(s, {kind: 'tool', message: 'b'}, {now: t + 1000, random: () => 0.6});
  await keepReport(s, {kind: 'old', message: 'c'}, {now: t - 100 * 864e5, random: () => 0.7});
  const list = await listReports(s, {days: 2, now: t + 2000});
  assert.deepEqual(list.map(r => r.message), ['b', 'a']);
  await pruneReports(s, t);
  assert.equal([...s.m.keys()].some(k => k.includes('2026-08')), false);
  s.m.set('n/2026-11-26', String(PER_DAY));
  assert.equal(await keepReport(s, {kind: 'x'}, {now: t, random: () => 0.5}), false);
});

test('reports: the list needs a valid GitHub identity; posting still works without one', async () => {
  const s = memory();
  const h = createPublicHandler({reportStore: s, verifier: async t => t === 'good' ? {repository: 'madarfiles/madarfilesweb'} : null});
  const post = await h(new Request('https://madarfiles.com/api/report', {method: 'POST', body: JSON.stringify({kind: 'error', message: 'boom'})}));
  assert.equal(post.status, 204);
  assert.equal((await h(new Request('https://madarfiles.com/api/report/list'))).status, 401);
  assert.equal((await h(new Request('https://madarfiles.com/api/report/list', {headers: {Authorization: 'Bearer bad'}}))).status, 401);
  const ok = await h(new Request('https://madarfiles.com/api/report/list?days=1', {headers: {Authorization: 'Bearer good'}}));
  assert.equal(ok.status, 200);
  assert.equal((await ok.json()).reports[0].message, 'boom');
});

test('reports: forged or foreign tokens are refused', async () => {
  const enc = o => Buffer.from(JSON.stringify(o)).toString('base64url');
  const now = Date.now(), claims = {iss: 'https://token.actions.githubusercontent.com', aud: 'madarfiles-reports', repository: 'someone/else', exp: now / 1000 + 300};
  assert.equal(await verifyGithubToken(enc({alg: 'RS256', kid: 'k'}) + '.' + enc(claims) + '.c2ln', {fetcher: async () => ({json: async () => ({keys: []})})}), null);
  assert.equal(await verifyGithubToken(enc({alg: 'none'}) + '.' + enc({...claims, repository: 'madarfiles/madarfilesweb'}) + '.x'), null);
  assert.equal(await verifyGithubToken('garbage'), null);
});

test('reports: a correctly signed token from this repository is accepted', async () => {
  const {publicKey, privateKey} = await crypto.subtle.generateKey({name: 'RSASSA-PKCS1-v1_5', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256'}, true, ['sign', 'verify']);
  const jwk = {...await crypto.subtle.exportKey('jwk', publicKey), kid: 'k1'};
  const enc = o => Buffer.from(JSON.stringify(o)).toString('base64url');
  const now = Date.now(), body = enc({alg: 'RS256', kid: 'k1'}) + '.' + enc({iss: 'https://token.actions.githubusercontent.com', aud: 'madarfiles-reports', repository: 'madarfiles/madarfilesweb', exp: Math.floor(now / 1000) + 300, nbf: Math.floor(now / 1000) - 5});
  const sig = Buffer.from(await crypto.subtle.sign('RSASSA-PKCS1-v1_5', privateKey, new TextEncoder().encode(body))).toString('base64url');
  const claims = await verifyGithubToken(body + '.' + sig, {fetcher: async () => ({json: async () => ({keys: [jwk]})}), now: now + 3600e3 * 2 - 3600e3 * 2});
  assert.equal(claims?.repository, 'madarfiles/madarfilesweb');
});
