"""Guard state-machine tests; fake NM boundary, no network or Linux privileges."""
import importlib.machinery
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


GUARD = Path(__file__).resolve().parents[1] / 'helper/piwifi-guard'


def load_guard(path=GUARD):
    boundary = SimpleNamespace(IFACE='wlan0', FALLBACK='Pi-Fallback', nm=Mock(),
                               get_active=Mock(), connect_profile=Mock(),
                               get_profiles=Mock(return_value=[]), command=Mock())
    original = importlib.machinery.SourceFileLoader.exec_module
    def execute(loader, module):
        if loader.name == 'piwifi_helper': module.__dict__.update(vars(boundary))
        else: original(loader, module)
    loader = importlib.machinery.SourceFileLoader('fallback_under_test', str(path))
    guard = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    with patch.object(importlib.machinery.SourceFileLoader, 'exec_module', execute):
        loader.exec_module(guard)
    return guard


class FallbackLogicTests(unittest.TestCase):
    def setUp(self):
        self.g = load_guard()
        self.code, self.profile, self.ip = 30, '--', ''
        self.g.helper.nm.side_effect = self.nm
        self.g.helper.get_active.side_effect = lambda: self.profile
        self.clock = patch.object(self.g.time, 'monotonic', return_value=1000)
        self.clock.start(); self.addCleanup(self.clock.stop)
        self.old = patch.object(self.g, 'previous_state', return_value={})
        self.old_mock = self.old.start(); self.addCleanup(self.old.stop)
        self.choices = patch.object(self.g, 'candidates', return_value=[])
        self.choices_mock = self.choices.start(); self.addCleanup(self.choices.stop)
        self.g.helper.connect_profile.side_effect = self.connect

    def nm(self, *args):
        if args == ('radio', 'wifi'): return 'enabled'
        if args[0:2] == ('-g', 'GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS'):
            return f'{self.code} (localized state)\n{self.profile}\n{self.ip}'
        if args[0:2] == ('-g', 'GENERAL.STATE'): return f'{self.code} (state)'
        if args[0:2] == ('-g', 'IP4.ADDRESS'): return self.ip
        raise AssertionError(args)

    def connect(self, profile, recovery=True):
        self.code, self.profile, self.ip = 100, profile, '192.168.50.1/24'

    def expired(self): self.old_mock.return_value = {'offline_since': 900}

    def test_connected_ipv4_preserved_without_internet_probe(self):
        self.code, self.profile, self.ip = 100, 'home', '192.168.0.106/24'
        self.assertEqual(self.g.run()['state'], 'preserved')
        self.g.helper.connect_profile.assert_not_called()
        self.g.helper.command.assert_not_called()

    def test_profile_name_does_not_mean_connected(self):
        for code in (40, 50, 60, 70, 80, 90, 110):
            with self.subTest(code=code):
                self.code, self.profile, self.ip = code, 'old-wifi', ''
                result = self.g.run()
                self.assertEqual(result['state'], 'connection-pending')
                self.assertEqual(result['remaining'], 90)
        self.g.helper.connect_profile.assert_not_called()

    def test_unfinished_without_name_has_deadline(self):
        self.code = 70
        self.assertEqual(self.g.run()['state'], 'connection-pending')
        self.expired()
        self.assertEqual(self.g.run()['state'], 'fallback')

    def test_auth_and_dhcp_cannot_wait_forever(self):
        for code in (40, 50, 60, 70, 80, 90, 100, 110):
            with self.subTest(code=code):
                self.code, self.profile, self.ip = code, 'old-wifi', ''
                self.expired()
                self.assertEqual(self.g.run()['state'], 'fallback')

    def test_failed_state_goes_to_ap(self):
        self.code, self.profile = 120, 'failed-wifi'
        self.assertEqual(self.g.run()['state'], 'fallback')
        self.choices_mock.assert_not_called()

    def test_invalid_or_link_local_ipv4_is_not_ready(self):
        for ip in ('', 'garbage', '0.0.0.0/0', '127.0.0.1/8', '169.254.1.2/16', '::1/128'):
            with self.subTest(ip=ip):
                self.code, self.profile, self.ip = 100, 'home', ip
                self.assertFalse(self.g.connection_status()['ready'])

    def test_multiple_addresses_accept_real_lan(self):
        self.code, self.profile, self.ip = 100, 'home', '169.254.1.2/16\n192.168.0.4/24'
        self.assertTrue(self.g.connection_status()['ready'])

    def test_busy_ap_profile_does_not_pretend_to_be_broadcasting(self):
        self.code, self.profile = 50, 'Pi-Fallback'
        with patch.object(self.g, 'clients') as clients:
            self.assertEqual(self.g.run()['state'], 'connection-pending')
            clients.assert_not_called()
            self.expired()
            self.assertEqual(self.g.run()['state'], 'fallback')

    def test_name_changes_do_not_reset_outage_clock(self):
        self.code, self.profile = 70, 'different-wifi'
        self.old_mock.return_value = {'offline_since': 930, 'profile': 'old-wifi'}
        result = self.g.run()
        self.assertEqual(result['offline_since'], 930)
        self.assertEqual(result['remaining'], 20)

    def test_corrupt_and_future_clock_values_are_reset(self):
        self.code = 60
        for value in (None, 'bad', -1, 5000, float('inf'), float('nan')):
            self.old_mock.return_value = {'offline_since': value}
            self.assertEqual(self.g.run()['offline_since'], 1000)

    def test_no_saved_network_activates_ap(self):
        self.assertEqual(self.g.run()['state'], 'fallback')
        self.g.helper.connect_profile.assert_called_once_with('Pi-Fallback', recovery=False)

    def test_timeout_leaving_profile_name_still_activates_ap(self):
        self.choices_mock.return_value = [('old', 'uuid-old')]
        def connect(profile, recovery=True):
            if profile == 'uuid-old':
                self.code, self.profile = 70, 'old'
                raise RuntimeError('nmcli timed out')
            self.connect(profile, recovery)
        self.g.helper.connect_profile.side_effect = connect
        self.assertEqual(self.g.run()['state'], 'fallback')

    def test_success_without_usable_address_still_activates_ap(self):
        self.choices_mock.return_value = [('old', 'uuid-old')]
        def connect(profile, recovery=True):
            if profile == 'uuid-old': self.code, self.profile = 70, 'old'
            else: self.connect(profile, recovery)
        self.g.helper.connect_profile.side_effect = connect
        self.assertEqual(self.g.run()['state'], 'fallback')

    def test_at_most_two_saved_profiles_before_ap(self):
        self.choices_mock.return_value = [(str(n), str(n)) for n in range(20)]
        def connect(profile, recovery=True):
            if profile != 'Pi-Fallback': raise RuntimeError('not available')
            self.connect(profile, recovery)
        self.g.helper.connect_profile.side_effect = connect
        self.assertEqual(self.g.run()['state'], 'fallback')
        self.assertEqual(self.g.helper.connect_profile.call_count, 3)

    def test_deadline_skips_another_round_of_old_profiles(self):
        self.expired()
        self.assertEqual(self.g.run()['state'], 'fallback')
        self.choices_mock.assert_not_called()

    def test_profile_inventory_failure_does_not_skip_ap(self):
        self.choices_mock.side_effect = RuntimeError('cannot list profiles')
        self.assertEqual(self.g.run()['state'], 'fallback')

    def test_fallback_failure_is_error_not_success(self):
        self.g.helper.connect_profile.side_effect = RuntimeError('AP activation failed')
        result = self.g.run()
        self.assertEqual(result['state'], 'error')
        self.assertEqual(result['offline_since'], 1000)

    def test_ap_without_address_is_error_not_success(self):
        def connect(*args, **kwargs): self.code, self.profile = 70, 'Pi-Fallback'
        self.g.helper.connect_profile.side_effect = connect
        self.assertEqual(self.g.run()['state'], 'error')

    def test_completed_wifi_race_before_fallback_is_preserved(self):
        self.expired()
        def inventory():
            self.code, self.profile, self.ip = 100, 'late-wifi', '192.168.1.5/24'
            return []
        self.choices_mock.side_effect = inventory
        self.old_mock.return_value = {}
        self.assertEqual(self.g.run()['state'], 'preserved')
        self.g.helper.connect_profile.assert_not_called()

    def test_disabled_radio_is_respected(self):
        self.g.helper.nm.side_effect = lambda *a: 'disabled' if a == ('radio', 'wifi') else self.nm(*a)
        self.assertEqual(self.g.run()['state'], 'radio-disabled')
        self.g.helper.connect_profile.assert_not_called()

    def test_unmanaged_or_unavailable_does_not_force_device(self):
        for code in (0, 10, 20):
            self.code = code
            self.expired()
            self.assertEqual(self.g.run()['state'], 'device-busy-or-unavailable')
        self.g.helper.connect_profile.assert_not_called()

    def test_ap_clients_and_unknown_clients_preserved(self):
        self.code, self.profile, self.ip = 100, 'Pi-Fallback', '192.168.50.1/24'
        for count, expected in ((1, 'hotspot-in-use'), (None, 'clients-unknown')):
            with patch.object(self.g, 'clients', return_value=count):
                self.assertEqual(self.g.run()['state'], expected)
        self.g.helper.connect_profile.assert_not_called()

    def test_malformed_or_failed_nm_read_is_not_a_disconnection(self):
        self.g.helper.nm.side_effect = None
        self.g.helper.nm.return_value = 'invalid'
        with self.assertRaises(RuntimeError): self.g.run()
        self.g.helper.connect_profile.assert_not_called()

    def ap(self):
        self.code, self.profile, self.ip = 100, 'Pi-Fallback', '192.168.50.1/24'
        self.old_mock.return_value = {'empty_checks': 1}

    def test_ap_grace_and_two_empty_checks(self):
        self.ap()
        with patch.object(self.g, 'clients', return_value=0), patch.object(Path, 'read_text', return_value='99999999999'):
            self.assertEqual(self.g.run()['state'], 'hotspot-grace')
        self.old_mock.return_value = {}
        with patch.object(self.g, 'clients', return_value=0), patch.object(Path, 'read_text', return_value='0'):
            self.assertEqual(self.g.run()['state'], 'waiting-no-clients')
        self.g.helper.connect_profile.assert_not_called()

    def test_ap_unsupported_scan_does_not_interrupt_clients(self):
        self.ap()
        self.g.helper.command.side_effect = RuntimeError('scan not supported')
        with patch.object(self.g, 'clients', return_value=0), patch.object(Path, 'read_text', return_value='0'):
            self.assertEqual(self.g.run()['state'], 'ap-scan-unavailable')
        self.g.helper.connect_profile.assert_not_called()

    def test_ap_no_visible_known_wifi_keeps_hotspot(self):
        self.ap()
        self.g.helper.command.return_value = 'SSID: unknown-network'
        with patch.object(self.g, 'clients', return_value=0), patch.object(Path, 'read_text', return_value='0'):
            self.assertEqual(self.g.run()['state'], 'no-known-wifi')
        self.g.helper.connect_profile.assert_not_called()

    def test_client_arrives_before_ap_return(self):
        self.ap()
        self.g.helper.command.return_value = 'SSID: Home'
        self.choices_mock.return_value = [('home', 'uuid-home')]
        with patch.object(self.g, 'clients', side_effect=[0, 1]), patch.object(Path, 'read_text', return_value='0'):
            self.assertEqual(self.g.run()['state'], 'client-arrived')
        self.g.helper.connect_profile.assert_not_called()

    def test_ap_return_requires_completed_wifi(self):
        self.ap()
        self.g.helper.command.return_value = 'SSID: Home'
        self.choices_mock.return_value = [('home', 'uuid-home')]
        def connect(profile, recovery=True):
            self.code, self.profile, self.ip = 100, 'home', '192.168.1.5/24'
        self.g.helper.connect_profile.side_effect = connect
        with patch.object(self.g, 'clients', return_value=0), patch.object(Path, 'read_text', return_value='0'):
            self.assertEqual(self.g.run()['state'], 'returned-to-wifi')

    def test_failed_ap_return_restores_verified_hotspot(self):
        for raises in (True, False):
            with self.subTest(raises=raises):
                self.ap()
                self.g.helper.command.return_value = 'SSID: Home'
                self.choices_mock.return_value = [('home', 'uuid-home')]
                def connect(profile, recovery=True):
                    if profile == 'uuid-home':
                        self.code, self.profile, self.ip = 70, 'home', ''
                        if raises: raise RuntimeError('wrong credentials')
                    else: self.connect(profile, recovery)
                self.g.helper.connect_profile.side_effect = connect
                with patch.object(self.g, 'clients', return_value=0), patch.object(Path, 'read_text', return_value='0'):
                    self.assertEqual(self.g.run()['state'], 'return-failed-restored-ap')

    def test_ap_restore_failure_is_reported(self):
        self.ap()
        self.g.helper.command.return_value = 'SSID: Home'
        self.choices_mock.return_value = [('home', 'uuid-home')]
        self.g.helper.connect_profile.side_effect = RuntimeError('activation failed')
        with patch.object(self.g, 'clients', return_value=0), patch.object(Path, 'read_text', return_value='0'):
            self.assertEqual(self.g.run()['state'], 'error')


if __name__ == '__main__': unittest.main()
