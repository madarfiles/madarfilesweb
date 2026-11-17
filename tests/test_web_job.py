import hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('webjob', Path(__file__).parents[1]/'colab/madar_web_job.py')
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)

class WebJobTests(unittest.TestCase):
    def test_chunk_manifest_verifies_reassembly_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as d, patch.object(job, 'ROOT', Path(d)), patch.object(job, 'PART', 4):
            blocks = [b'abcd', b'efg']
            def upload():
                for i, data in enumerate(blocks): (Path(d)/f'input_{i:05d}.bin').write_bytes(data)
            upload()
            cfg = dict(ext='mkv',size=7,chunks=2,sha256=hashlib.sha256(b''.join(hashlib.sha256(b).digest() for b in blocks)).hexdigest())
            self.assertEqual(job.assemble(cfg).read_bytes(), b'abcdefg')
            self.assertFalse(list(Path(d).glob('input_*.bin')))
            upload()
            (Path(d)/'input_00001.bin').write_bytes(b'xyz')
            with self.assertRaises(ValueError): job.assemble(cfg)
            self.assertFalse((Path(d)/'source.mkv').exists())

    def test_duplicate_start_is_noop(self):
        with tempfile.TemporaryDirectory() as d, patch.object(job, 'ROOT', Path(d)), patch.object(job.subprocess,'run') as install:
            (Path(d)/'started.lock').touch()
            job.main()
            install.assert_not_called()

    def test_error_state_is_safe_and_persisted(self):
        with tempfile.TemporaryDirectory() as d, patch.object(job, 'ROOT', Path(d)), patch.object(job.subprocess,'run',side_effect=OSError('secret-log-url')):
            (Path(d)/'config.json').write_text('{}')
            job.main()
            state=json.loads((Path(d)/'state.json').read_text())
            self.assertEqual(state['state'],'error')
            self.assertNotIn('secret-log-url',state['message'])
