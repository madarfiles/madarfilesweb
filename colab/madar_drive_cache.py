"""Models kept in the visitor's own Google Drive (hidden «appDataFolder», scope drive.appdata).

The first run of a tool downloads its models as usual; afterwards they are copied into the
hidden Madar folder of the visitor's Drive. Every later session (even on a new Colab machine)
pulls them from Drive, inside Google's network, instead of downloading again. Every file is
checked by SHA-256 before use. Any problem (no Drive permission, full Drive, network) only
means the normal download happens: the tool never fails because of the cache.
"""
import fcntl, hashlib, json, os, shutil, tarfile, threading, time
from pathlib import Path

VERSION = '1'
BASE = Path(__file__).resolve().parent
KEY = BASE/'google.json'
FILES = 'https://www.googleapis.com/drive/v3/files'
UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files'
CACHE = Path('/content/madar_models')
LOCKS = BASE/'drive-locks'
BLOCK = 8 << 20


def _hub():
    return Path(os.environ.get('HF_HOME') or BASE/'cache/huggingface')/'hub'


def _repo(repo):
    return ('hf-' + repo.replace('/', '--'), _hub()/('models--' + repo.replace('/', '--')))


def parts(task):
    """(name, local path) of every model a tool uses. Folders are Hugging Face caches."""
    from madar_colab_runtime import MODEL, DUB_MODEL
    whisper = _repo('mobiuslabsgmbh/faster-whisper-large-v3-turbo')
    nllb = _repo('facebook/nllb-200-distilled-600M')
    sound = _repo('MIT/ast-finetuned-audioset-10-10-0.4593')
    return {
        'separate': [('uvr-' + MODEL, CACHE/MODEL)],
        'dub': [('uvr-' + DUB_MODEL, CACHE/DUB_MODEL), whisper, ('titanet-large', CACHE/'titanet_large.onnx'), sound, nllb],
        'asr': [whisper, nllb],
        'translate': [nllb],
    }.get(task, [])


def token():
    try:
        data = json.loads(KEY.read_text())
    except (OSError, ValueError):
        return None
    if data.get('drive') is not True or not isinstance(data.get('token'), str) or data.get('expires', 0) < time.time() + 120:
        return None
    return data['token']


def _ready(path):
    """A local model is complete: a non-empty file, or a Hugging Face folder with a snapshot
    and no unfinished download."""
    if path.is_file():
        return path.stat().st_size > 0
    if not path.is_dir():
        return False
    snaps = path/'snapshots'
    return snaps.is_dir() and any(snaps.iterdir()) and not any((path/'blobs').glob('*.incomplete'))


def _lock(name):
    LOCKS.mkdir(parents=True, exist_ok=True)
    handle = open(LOCKS/(name + '.lock'), 'a')
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle


def _find(name, auth, requests):
    r = requests.get(FILES, headers=auth, timeout=(10, 20), params={
        'spaces': 'appDataFolder', 'q': f"name = 'madar-{VERSION}-{name}' and trashed = false",
        'fields': 'files(id,size,appProperties)', 'pageSize': 10})
    if r.status_code != 200:
        raise RuntimeError('DRIVE_LIST_%d' % r.status_code)
    for item in r.json().get('files', []):
        props = item.get('appProperties') or {}
        if len(props.get('sha256', '')) == 64 and str(item.get('size')) == props.get('size'):
            return item['id'], props['sha256'], int(props['size']), props.get('kind', 'file')
    return None


def restore(task, report=lambda *a, **k: None):
    """Copies every model of `task` that is missing on this machine from Drive. Returns the
    names restored. Holds a lock per model so the early preparation and the job never fetch
    the same model twice."""
    auth_token = token()
    if not auth_token:
        return []
    import requests
    auth = {'Authorization': 'Bearer ' + auth_token}
    done = []
    for name, path in parts(task):
        if _ready(path):
            continue
        lock = _lock(name)
        try:
            if _ready(path):
                continue
            found = _find(name, auth, requests)
            if not found:
                continue
            file_id, digest, size, kind = found
            report('setup', 'نجيب النماذج الجاهزة من Google Drive…')
            tmp = CACHE/'.drive-tmp'; tmp.mkdir(parents=True, exist_ok=True)
            part = tmp/(name + '.part')
            h = hashlib.sha256(); got = 0
            with requests.get(f'{FILES}/{file_id}', params={'alt': 'media'}, headers=auth, stream=True, timeout=(15, 60)) as r:
                if r.status_code != 200:
                    continue
                with open(part, 'wb') as out:
                    for block in r.iter_content(BLOCK):
                        h.update(block); out.write(block); got += len(block)
            if got != size or h.hexdigest() != digest:
                part.unlink(missing_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            if kind == 'dir':
                unpacked = tmp/(name + '.dir'); shutil.rmtree(unpacked, ignore_errors=True)
                with tarfile.open(part) as tar:
                    tar.extractall(unpacked, filter='data')
                part.unlink(missing_ok=True)
                source = unpacked/path.name
                if not source.is_dir():
                    shutil.rmtree(unpacked, ignore_errors=True); continue
                if path.exists():
                    shutil.rmtree(path, ignore_errors=True)
                os.replace(source, path); shutil.rmtree(unpacked, ignore_errors=True)
            else:
                os.replace(part, path)
            (LOCKS/(name + '.from-drive')).touch()
            done.append(name)
        except Exception:
            pass
        finally:
            lock.close()
    return done


def _upload(name, path, auth, requests):
    tmp = CACHE/'.drive-tmp'; tmp.mkdir(parents=True, exist_ok=True)
    kind = 'dir' if path.is_dir() else 'file'
    if kind == 'dir':
        packed = tmp/(name + '.tar')
        with tarfile.open(packed, 'w') as tar:
            tar.add(path, arcname=path.name)
    else:
        packed = path
    try:
        h = hashlib.sha256(); size = 0
        with open(packed, 'rb') as f:
            for block in iter(lambda: f.read(BLOCK), b''):
                h.update(block); size += len(block)
        meta = {'name': f'madar-{VERSION}-{name}', 'parents': ['appDataFolder'],
                'appProperties': {'sha256': h.hexdigest(), 'size': str(size), 'kind': kind}}
        r = requests.post(UPLOAD, params={'uploadType': 'resumable'}, json=meta, timeout=(10, 30),
                          headers={**auth, 'X-Upload-Content-Type': 'application/octet-stream', 'X-Upload-Content-Length': str(size)})
        location = r.headers.get('Location', '')
        if r.status_code != 200 or not location.startswith('https://www.googleapis.com/upload/drive/v3/files'):
            return False
        with open(packed, 'rb') as f:
            r = requests.put(location, data=f, headers={'Content-Length': str(size), 'Content-Type': 'application/octet-stream'}, timeout=(15, 1800))
        return r.status_code in (200, 201)
    finally:
        if kind == 'dir':
            packed.unlink(missing_ok=True)


def save(task):
    """Copies to Drive the models of `task` that this machine downloaded and Drive lacks."""
    auth_token = token()
    if not auth_token:
        return []
    import requests
    auth = {'Authorization': 'Bearer ' + auth_token}
    saved = []
    for name, path in parts(task):
        lock = _lock(name)
        try:
            if not _ready(path) or (LOCKS/(name + '.from-drive')).exists() or (LOCKS/(name + '.saved')).exists():
                continue
            if _find(name, auth, requests) or _upload(name, path, auth, requests):
                (LOCKS/(name + '.saved')).touch(); saved.append(name)
        except Exception:
            pass
        finally:
            lock.close()
    return saved


def save_later(task):
    """After a job finishes: upload in the background so the visitor never waits for it."""
    threading.Thread(target=save, args=(task,), daemon=True, name='madar-drive-save').start()
