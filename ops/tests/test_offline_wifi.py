import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

OPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OPS))
import offline_wifi_boot as recovery
import prepare_offline_wifi as prepare


class OfflineWifiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.boot, self.root = self.base / 'boot', self.base / 'root'
        self.boot.mkdir()
        (self.root / 'etc/NetworkManager/system-connections').mkdir(parents=True)
        self.original = b'console=tty1 root=PARTUUID=9586d7bf-02 rootwait\n'
        (self.boot / 'cmdline.txt').write_bytes(self.original)
        (self.boot / 'config.txt').write_text('arm_64bit=1\n')
        self.password = 'fixture-password-only'

    def stage(self): return prepare.prepare(self.boot, 'Fixture Wi-Fi', self.password)
    def recover(self, probe=lambda: (prepare.ROOT_UUID, prepare.HOST_FINGERPRINT)):
        return recovery.recover(self.boot, self.root, probe)
    def target(self): return list((self.root / 'etc/NetworkManager/system-connections').iterdir())

    def test_preparation_is_reversible_and_does_not_embed_plaintext(self):
        result = self.stage()
        self.assertTrue(result['requires_boot_verification'])
        self.assertEqual((self.boot / (recovery.PREFIX + '.cmdline')).read_bytes(), self.original)
        payload = (self.boot / (recovery.PREFIX + '.nmconnection')).read_text()
        self.assertNotIn(self.password, payload)
        derived = hashlib.pbkdf2_hmac('sha1', self.password.encode(), b'Fixture Wi-Fi', 4096, 32).hex()
        self.assertIn('psk=' + derived, payload)
        self.assertIn(recovery.BOOT_ARGUMENTS, (self.boot / 'cmdline.txt').read_text())
        self.assertFalse(self.target())

    def test_success_writes_profile_restores_boot_and_erases_temporary_credentials(self):
        self.stage(); result = self.recover()
        self.assertTrue(result['ok']); self.assertEqual(len(self.target()), 1)
        self.assertEqual((self.boot / 'cmdline.txt').read_bytes(), self.original)
        for suffix in ('.json', '.cmdline', '.nmconnection', '.py'):
            self.assertFalse((self.boot / (recovery.PREFIX + suffix)).exists())
        report = (self.boot / (recovery.PREFIX + '.result.json')).read_text()
        self.assertNotIn(self.password, report); self.assertNotIn('psk=', report)
        self.assertEqual(result['wifi_connected'], 'not-tested')

    def test_wrong_disk_or_host_key_does_not_change_network(self):
        for probe in (lambda: ('other-root', prepare.HOST_FINGERPRINT),
                      lambda: (prepare.ROOT_UUID, 'SHA256:other')):
            self.stage(); result = self.recover(probe)
            self.assertFalse(result['ok']); self.assertFalse(self.target())
            self.assertEqual((self.boot / 'cmdline.txt').read_bytes(), self.original)

    def test_payload_tampering_fails_closed_and_still_disarms_boot(self):
        self.stage()
        (self.boot / (recovery.PREFIX + '.nmconnection')).write_text('corrupt')
        self.assertFalse(self.recover()['ok']); self.assertFalse(self.target())
        self.assertEqual((self.boot / 'cmdline.txt').read_bytes(), self.original)

    def test_missing_plan_disarms_without_reboot_loop(self):
        self.stage(); (self.boot / (recovery.PREFIX + '.json')).unlink()
        result = self.recover()
        self.assertFalse(result['ok']); self.assertTrue(result['recovery_disarmed'])
        self.assertEqual((self.boot / 'cmdline.txt').read_bytes(), self.original)

    def test_damaged_original_disarms_using_only_our_arguments(self):
        self.stage(); (self.boot / (recovery.PREFIX + '.cmdline')).write_bytes(b'damaged')
        result = self.recover()
        self.assertFalse(result['ok']); self.assertTrue(result['recovery_disarmed'])
        self.assertEqual((self.boot / 'cmdline.txt').read_bytes(), self.original)

    def test_existing_profile_is_not_overwritten(self):
        self.stage()
        plan = json.loads((self.boot / (recovery.PREFIX + '.json')).read_text())
        target = self.root / 'etc/NetworkManager/system-connections' / plan['profile_filename']
        target.write_bytes(b'existing-important-profile')
        self.assertFalse(self.recover()['ok'])
        self.assertEqual(target.read_bytes(), b'existing-important-profile')

    def test_wrong_boot_target_is_rejected_without_edits(self):
        (self.boot / 'cmdline.txt').write_bytes(b'root=PARTUUID=other-02\n')
        with self.assertRaises(ValueError): self.stage()
        self.assertEqual(sorted(p.name for p in self.boot.iterdir()), ['cmdline.txt', 'config.txt'])

    def test_existing_override_not_replaced(self):
        (self.boot / 'cmdline.txt').write_bytes(self.original.rstrip() + b' systemd.run=existing\n')
        with self.assertRaises(ValueError): self.stage()

    def test_repeated_preparation_does_not_overwrite(self):
        self.stage(); before = (self.boot / 'cmdline.txt').read_bytes()
        with self.assertRaises(ValueError): self.stage()
        self.assertEqual((self.boot / 'cmdline.txt').read_bytes(), before)


if __name__ == '__main__': unittest.main()
