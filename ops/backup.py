"""Encrypted off-Pi backup. Private content stays in process memory until encrypted."""
import argparse
import base64
import ctypes
from ctypes import wintypes
import getpass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
import threading
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b'PICONTROL-BACKUP-1\n'
KEY_MAGIC = b'PICONTROL-RECOVERY-1\n'
MAX_ARCHIVE = 128 * 1024 * 1024


def dpapi(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Local key protection requires Windows DPAPI')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    func.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    func.restype = wintypes.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN; CurrentUser scope, no LocalMachine flag.
    if not func(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create; partial output is removed on failure.
    with path.open('xb') as stream:
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            path.unlink(missing_ok=True)
            raise


def load_key(path, create=False):
    path = Path(path)
    if not path.exists() and create:
        write_new(path, dpapi(os.urandom(32)))
    key = dpapi(path.read_bytes(), decrypt=True)
    if len(key) != 32:
        raise ValueError('Invalid backup key')
    return key


def encrypt(data, key, magic=MAGIC):
    nonce = os.urandom(12)
    return magic + nonce + AESGCM(key).encrypt(nonce, data, magic)


def decrypt(data, key, magic=MAGIC):
    if not data.startswith(magic) or len(data) < len(magic) + 28:
        raise ValueError('Invalid encrypted file')
    start = len(magic)
    return AESGCM(key).decrypt(data[start:start+12], data[start+12:], magic)


def verify_archive(data):
    if len(data) > MAX_ARCHIVE:
        raise ValueError('Archive too large')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        members = tar.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)) or 'manifest.json' not in names:
            raise ValueError('Missing manifest or duplicate paths')
        total = 0
        for item in members:
            path = PurePosixPath(item.name)
            if (not item.isfile() or path.is_absolute() or '..' in path.parts
                    or '\\' in item.name or ':' in item.name):
                raise ValueError('Unsafe archive path')
            total += item.size
            if total > MAX_ARCHIVE:
                raise ValueError('Expanded archive too large')
        manifest = json.load(tar.extractfile('manifest.json'))
        if manifest.get('version') != 1:
            raise ValueError('Unsupported manifest version')
        entries = manifest['files']
        expected = {f['path'] for f in entries}
        if len(expected) != len(entries) or expected != set(names) - {'manifest.json'}:
            raise ValueError('Manifest inventory mismatch')
        for entry in entries:
            value = tar.extractfile(entry['path']).read()
            if len(value) != entry['size'] or hashlib.sha256(value).hexdigest() != entry['sha256']:
                raise ValueError('Archive checksum mismatch')
        return manifest


def extract_verified(data, destination):
    manifest = verify_archive(data)
    destination = Path(destination).resolve()
    # A new directory only. Never automatically overwrite the live system.
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        for member in tar.getmembers():
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            write_new(target, tar.extractfile(member).read())
            if os.name != 'nt':
                target.chmod(0o600)  # Original metadata is retained in manifest, not applied blindly.
    return manifest


def fetch_archive(ssh_options):
    code = base64.b64encode(Path(__file__).with_name('backup_collect.py').read_bytes()).decode()
    command = "sudo -n python3 -B -c \"import base64;exec(base64.b64decode('" + code + "'))\""
    # No PowerShell binary pipeline: Python reads SSH stdout directly.
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen(['ssh', *ssh_options, 'rasp-tt', command], stdout=subprocess.PIPE,
                              stderr=errors) as proc:
            timer = threading.Timer(90, proc.kill)
            timer.start()
            try:
                data = proc.stdout.read(MAX_ARCHIVE + 1)
                if len(data) > MAX_ARCHIVE:
                    proc.kill()
                    raise RuntimeError('Remote backup exceeds limit')
                result = proc.wait(timeout=90)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise RuntimeError('Backup timed out') from None
            finally:
                timer.cancel()
            if result:
                raise RuntimeError('Pi backup failed; check SSH and temporary sudo authorization')
    verify_archive(data)
    return data


def recovery_key(password, salt):
    return Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(password.encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'verify', 'restore-files', 'export-key', 'import-key'])
    parser.add_argument('--file', type=Path)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--ssh-options-base64', default='W10=')
    parser.add_argument('--key-file', type=Path,
                        default=Path(os.environ.get('LOCALAPPDATA', '.')) / 'PiControl/backup/key.dpapi')
    args = parser.parse_args()
    if args.action == 'import-key':
        payload = args.file.read_bytes()
        salt = payload[:16]
        key = decrypt(payload[16:], recovery_key(getpass.getpass('Recovery password: '), salt), KEY_MAGIC)
        if len(key) != 32:
            raise ValueError('Invalid recovery key')
        write_new(args.key_file, dpapi(key))
        print('Recovery key imported for current Windows user.')
        return
    key = load_key(args.key_file, create=args.action == 'create')
    if args.action == 'export-key':
        password = getpass.getpass('New recovery password (12+ characters): ')
        if len(password) < 12 or password != getpass.getpass('Confirm password: '):
            raise ValueError('Password too short or confirmation differs')
        salt = os.urandom(16)
        write_new(args.file, salt + encrypt(key, recovery_key(password, salt), KEY_MAGIC))
        print('Encrypted recovery key exported. Store separately from backups.')
        return
    if args.action == 'create':
        data = fetch_archive(json.loads(base64.b64decode(args.ssh_options_base64)))
        output = args.file or args.key_file.parent / ('pi-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.picbackup')
        encrypted = encrypt(data, key)
        # Check the complete encrypted round-trip before saving.
        manifest = verify_archive(decrypt(encrypted, key))
        write_new(output, encrypted)
    else:
        output = args.file
        data = decrypt(output.read_bytes(), key)
        manifest = verify_archive(data)
        if args.action == 'restore-files':
            extract_verified(data, args.destination)
    print(json.dumps(dict(file=str(output), verified=True, files=len(manifest['files']),
                          missing=len(manifest['missing']), skipped=len(manifest['skipped']),
                          created_utc=manifest['created_utc'])))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not emit archive content, credentials or raw remote stderr.
        raise SystemExit('Backup failed: ' + type(error).__name__ + '. Check arguments, key, SSH and sudo.') from None
