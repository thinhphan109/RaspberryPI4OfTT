import concurrent.futures
import threading
import unittest
from unittest.mock import Mock, patch

from read_cache import ReadCache
import observer
import app


class ReadCacheTests(unittest.TestCase):
    def test_same_key_concurrent_read_is_coalesced_and_results_are_isolated(self):
        cache = ReadCache()
        entered, release = threading.Event(), threading.Event()
        def load():
            entered.set()
            self.assertTrue(release.wait(2))
            return {'rows': [1]}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            loader = Mock(side_effect=load)
            pending = [pool.submit(cache.read, 'network', 60, loader) for _ in range(4)]
            self.assertTrue(entered.wait(2))
            release.set()
            results = [p.result(timeout=2) for p in pending]
        self.assertEqual(loader.call_count, 1)
        results[0]['rows'].append(2)
        self.assertEqual(results[1], {'rows': [1]})

    def test_slow_key_does_not_hold_other_keys(self):
        cache = ReadCache()
        entered, release = threading.Event(), threading.Event()
        def slow():
            entered.set()
            self.assertTrue(release.wait(2))
            return 'network'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(cache.read, 'network', 60, slow)
            self.assertTrue(entered.wait(2))
            try:
                other = pool.submit(cache.read, 'gpio', 10, lambda: 'gpio')
                self.assertEqual(other.result(timeout=1), 'gpio')
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=2), 'network')

    def test_clear_during_read_does_not_cache_pre_change_value(self):
        cache = ReadCache()
        entered, release = threading.Event(), threading.Event()
        def load():
            entered.set()
            self.assertTrue(release.wait(2))
            return 'old'
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(cache.read, 'network', 60, load)
            self.assertTrue(entered.wait(2))
            cache.clear()
            release.set()
            self.assertEqual(pending.result(timeout=2), 'old')
        self.assertEqual(cache.read('network', 60, lambda: 'new'), 'new')

    def test_error_releases_waiters_and_failed_reads_are_not_cached(self):
        cache = ReadCache()
        with self.assertRaises(ValueError):
            cache.read('network', 60, Mock(side_effect=ValueError('offline')))
        self.assertFalse(cache.loading)
        self.assertEqual(cache.read('network', 60, lambda: 'recovered'), 'recovered')

    def test_expiry_and_capacity(self):
        cache = ReadCache(max_entries=2)
        self.assertEqual(cache.read('a', 60, lambda: 1), 1)
        self.assertEqual(cache.read('a', 0, lambda: 2), 2)
        cache.read('b', 60, lambda: 3)
        cache.read('c', 60, lambda: 4)
        self.assertEqual(list(cache.values), ['b', 'c'])


class HttpDiagnosticsTests(unittest.TestCase):
    def test_open_port_with_http_500_is_not_healthy(self):
        for code in (200, 500):
            with self.subTest(code=code):
                connection = Mock()
                connection.getresponse.return_value.status = code
                with patch.object(observer.http.client, 'HTTPConnection', return_value=connection):
                    result = observer.diagnostics({'active': 'Pi-Fallback', 'ip': '192.168.50.1/24'})
                web = next(layer for layer in result['layers'] if layer['name'] == 'Dashboard')
                self.assertEqual(web['state'], 'ok' if code == 200 else 'failed')
                connection.request.assert_called_once_with('GET', '/login', headers={'Connection': 'close'})
                connection.close.assert_called_once()

    def test_timeout_closes_connection_and_reports_failure(self):
        connection = Mock()
        connection.getresponse.side_effect = TimeoutError()
        with patch.object(observer.http.client, 'HTTPConnection', return_value=connection):
            result = observer.diagnostics({'active': 'Pi-Fallback', 'ip': '192.168.50.1/24'})
        self.assertEqual(next(row['state'] for row in result['layers'] if row['name'] == 'Dashboard'), 'failed')
        connection.close.assert_called_once()


class HomepageCacheTests(unittest.TestCase):
    def test_home_and_status_share_network_cache_and_explicit_clear_refreshes(self):
        app._read_cache.clear()
        self.addCleanup(app._read_cache.clear)
        client = app.app.test_client()
        with client.session_transaction() as session:
            session.update(logged_in=True, csrf='response-test')
        with patch.object(app, 'helper', return_value={'profiles': []}) as helper, patch.object(app, 'collect', return_value={}):
            self.assertEqual(client.get('/').status_code, 200)
            self.assertEqual(client.get('/').status_code, 200)
            self.assertEqual(client.get('/api/status').status_code, 200)
            self.assertEqual(helper.call_count, 1)
            app._read_cache.clear()
            self.assertEqual(client.get('/api/status').status_code, 200)
            self.assertEqual(helper.call_count, 2)


if __name__ == '__main__':
    unittest.main()
