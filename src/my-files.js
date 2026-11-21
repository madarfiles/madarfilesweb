// «ملفاتي»: results kept on this device (IndexedDB), so they survive closing the page. Nothing
// leaves the device. The newest MAX_ITEMS results are kept, within a size budget that leaves the
// browser room (half of what it offers, never more than 1.5 GB); anything that can't be stored
// simply stays for this visit only.
const DB = 'madar-files', STORE = 'results', VERSION = 1;
export const MAX_ITEMS = 30, MAX_BYTES = 1.5 * 1024 ** 3;

let dbPromise = null;
function db() {
  if (!globalThis.indexedDB) return Promise.reject(Error('no indexedDB'));
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB, VERSION);
      request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE, {keyPath: 'id'}); };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => { dbPromise = null; reject(request.error); };
      request.onblocked = () => { dbPromise = null; reject(Error('blocked')); };
    });
  }
  return dbPromise;
}

function run(mode, work) {
  return db().then(handle => new Promise((resolve, reject) => {
    const tx = handle.transaction(STORE, mode), store = tx.objectStore(STORE);
    let value; const req = work(store);
    if (req) req.onsuccess = () => { value = req.result; };
    tx.oncomplete = () => resolve(value); tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error || Error('aborted'));
  }));
}

export async function budget() {
  try {
    const estimate = await navigator.storage?.estimate?.();
    if (estimate?.quota) return Math.min(MAX_BYTES, Math.floor(estimate.quota * 0.5));
  } catch {}
  return 500 * 1048576;
}

// Which records to drop so that at most `maxItems` remain within `maxBytes` (newest kept).
export function overflow(records, maxItems = MAX_ITEMS, maxBytes = MAX_BYTES) {
  const sorted = [...records].sort((a, b) => b.created - a.created);
  const keep = [], drop = []; let total = 0;
  for (const r of sorted) {
    const size = r.size || r.blob?.size || 0;
    if (keep.length < maxItems && total + size <= maxBytes) { keep.push(r); total += size; } else drop.push(r);
  }
  return drop;
}

export async function listFiles() {
  const all = (await run('readonly', store => store.getAll())) || [];
  return all.filter(r => r && r.blob instanceof Blob).sort((a, b) => b.created - a.created);
}

export async function saveFile({id, blob, name, type, created = Date.now()}) {
  const limit = await budget();
  if (!blob?.size || blob.size > limit * 0.8) return false;
  try { await navigator.storage?.persist?.(); } catch {}
  await run('readwrite', store => store.put({id, blob, name, type, created, size: blob.size}));
  const meta = (await run('readonly', store => store.getAll())) || [];
  const drop = overflow(meta.map(r => ({id: r.id, created: r.created, size: r.size})), MAX_ITEMS, limit);
  if (drop.length) await run('readwrite', store => { for (const r of drop) store.delete(r.id); });
  return !drop.some(r => r.id === id);
}

export function removeFile(id) { return run('readwrite', store => store.delete(id)).catch(() => {}); }
export function clearFiles() { return run('readwrite', store => store.clear()).catch(() => {}); }

export function when(created, now = Date.now()) {
  const d = new Date(created), today = new Date(now);
  const time = d.toLocaleTimeString('ar-SA-u-nu-latn', {hour: 'numeric', minute: '2-digit'});
  if (d.toDateString() === today.toDateString()) return 'اليوم ' + time;
  const y = new Date(now - 86400000);
  if (d.toDateString() === y.toDateString()) return 'أمس ' + time;
  return d.toLocaleDateString('ar-SA-u-nu-latn-ca-gregory', {day: 'numeric', month: 'short'}) + ' ' + time;
}
