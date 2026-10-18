import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backup
import backup_collect
from cryptography.exceptions import InvalidTag


def sample(name='etc/sample.conf', content=b'example', checksum=None, duplicate=False, link=False):
    stream = io.BytesIO()
    manifest = dict(version=1, created_utc='2026-10-19T00:00:00Z', missing=[], skipped=[],
                    files=[dict(path=name, size=len(content),
                                sha256=checksum or hashlib.sha256(content).hexdigest())])
    with tarfile.open(fileobj=stream, mode='w:gz') as tar:
        for _ in range(2 if duplicate else 1):
            item = tarfile.TarInfo(name)
            item.size = len(content)
            if link:
                item.type, item.linkname = tarfile.SYMTYPE, '/etc/passwd'
            tar.addfile(item, io.BytesIO(content))
        raw = json.dumps(manifest).encode()
        item = tarfile.TarInfo('manifest.json')
        item.size = len(raw)
        tar.addfile(item, io.BytesIO(raw))
    return stream.getvalue()


class BackupTests(unittest.TestCase):
    def test_roundtrip_and_nonce_uniqueness(self):
        key = os.urandom(32)
        data = sample()
        first, second = backup.encrypt(data, key), backup.encrypt(data, key)
        self.assertNotEqual(first, second)
        self.assertEqual(backup.decrypt(first, key), data)
        self.assertEqual(len(backup.verify_archive(backup.decrypt(first, key))['files']), 1)

    def test_wrong_key(self):
        with self.assertRaises(InvalidTag):
            backup.decrypt(backup.encrypt(sample(), os.urandom(32)), os.urandom(32))

    def test_tamper(self):
        key = os.urandom(32)
        value = bytearray(backup.encrypt(sample(), key))
        value[-1] ^= 1
        with self.assertRaises(InvalidTag):
            backup.decrypt(bytes(value), key)

    def test_bad_header(self):
        with self.assertRaises(ValueError):
            backup.decrypt(b'bad', os.urandom(32))

    def test_unsafe_paths_and_symlink(self):
        for name in ('../outside', '/absolute', 'C:/outside', 'etc\\outside'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                backup.verify_archive(sample(name))
        with self.assertRaises(ValueError):
            backup.verify_archive(sample(link=True))

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            backup.verify_archive(sample(duplicate=True))

    def test_bad_checksum(self):
        with self.assertRaises(ValueError):
            backup.verify_archive(sample(checksum='bad'))

    def test_restore_new_directory_only(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'restore'
            backup.extract_verified(sample(), target)
            self.assertEqual((target / 'etc/sample.conf').read_bytes(), b'example')
            with self.assertRaises(FileExistsError):
                backup.extract_verified(sample(), target)

    def test_exclusive_write(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'value'
            backup.write_new(target, b'original')
            with self.assertRaises(FileExistsError):
                backup.write_new(target, b'changed')
            self.assertEqual(target.read_bytes(), b'original')

    def test_portable_recovery(self):
        salt, key = os.urandom(16), os.urandom(32)
        derived = backup.recovery_key('unit-test recovery phrase', salt)
        encrypted = backup.encrypt(key, derived, backup.KEY_MAGIC)
        self.assertEqual(backup.decrypt(encrypted, derived, backup.KEY_MAGIC), key)
        with self.assertRaises(InvalidTag):
            backup.decrypt(encrypted, backup.recovery_key('different phrase', salt), backup.KEY_MAGIC)

    @unittest.skipUnless(os.name == 'nt', 'Windows key storage')
    def test_dpapi_key_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'key.dpapi'
            key = backup.load_key(path, create=True)
            self.assertEqual(key, backup.load_key(path))
            self.assertNotEqual(path.read_bytes(), key)

    @unittest.skipIf(os.name == 'nt', 'Pi collector runs on Linux')
    def test_collector_sqlite_online_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'config'
            config.write_bytes(b'example')
            db = root / 'storage-writes.db'
            with sqlite3.connect(db) as conn:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('CREATE TABLE sample(value)')
                conn.execute('INSERT INTO sample VALUES (42)')
                conn.commit()
                archive = backup_collect.collect([config, db, root / 'missing'], release=False)
            manifest = backup.verify_archive(archive)
            self.assertEqual(len(manifest['files']), 2)
            self.assertEqual(len(manifest['missing']), 1)
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                data = tar.extractfile(db.as_posix().lstrip('/')).read()
            self.assertEqual(data[18:20], b'\x01\x01')
            with sqlite3.connect(':memory:') as restored:
                restored.deserialize(data)
                self.assertEqual(restored.execute('SELECT value FROM sample').fetchone()[0], 42)
                self.assertEqual(restored.execute('PRAGMA quick_check').fetchone()[0], 'ok')


if __name__ == '__main__':
    unittest.main()
