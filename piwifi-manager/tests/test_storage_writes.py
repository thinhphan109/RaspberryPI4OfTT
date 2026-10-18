import json
import tempfile
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from storage_writes import WriteTracker
import app
import observer


class StorageWritesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'writes.db'
        self.tracker=WriteTracker(self.path)
        self.now=1800000000

    def tearDown(self):
        self.tracker.close()
        self.tmp.cleanup()

    def sample(self,counter,seconds=0,boot='a',device='card-a',uptime=None):
        return dict(device=device,name='mmcblk0',model='test',boot=boot,counter=counter,
                    uptime=1000+seconds if uptime is None else uptime,timestamp=self.now+seconds)

    def test_initial_baseline_excludes_preinstall_writes(self):
        self.tracker.sample(self.sample(123456))
        result=self.tracker.query()
        self.assertEqual(result['total_bytes'],0)
        self.assertEqual(result['boot_bytes'],123456)
        self.assertIsNone(result['rate'])

    def test_delta_rate_and_daily_sum(self):
        self.tracker.sample(self.sample(100))
        self.tracker.sample(self.sample(1100,10))
        result=self.tracker.query()
        self.assertEqual(result['total_bytes'],1000)
        self.assertEqual(result['rate'],100)
        self.assertAlmostEqual(sum(r['written'] for r in result['daily_history']),1000)

    def test_same_boot_restart_recovers_since_last_checkpoint_once(self):
        self.tracker.sample(self.sample(100))
        self.tracker.sample(self.sample(1100,10))
        self.tracker.checkpoint(force=True)
        self.tracker.db.close()  # Simulated crash; no final flush.
        self.tracker=WriteTracker(self.path)
        self.tracker.sample(self.sample(1600,20))
        self.assertEqual(self.tracker.query()['total_bytes'],1500)
        self.tracker.checkpoint(force=True)
        self.tracker.db.close()
        self.tracker=WriteTracker(self.path)
        self.tracker.sample(self.sample(1600,21))
        self.assertEqual(self.tracker.query()['total_bytes'],1500)

    def test_restart_catches_unflushed_same_boot_bytes(self):
        self.tracker.sample(self.sample(100))
        self.tracker.sample(self.sample(1100,10))
        self.tracker.db.close()
        self.tracker=WriteTracker(self.path)
        self.tracker.sample(self.sample(1600,20))
        self.assertEqual(self.tracker.query()['total_bytes'],1500)

    def test_new_boot_adds_new_counter_without_subtraction(self):
        self.tracker.sample(self.sample(100))
        self.tracker.sample(self.sample(1100,10))
        self.tracker.sample(self.sample(200,30,boot='b',uptime=5))
        result=self.tracker.query()
        self.assertEqual(result['total_bytes'],1200)
        self.assertEqual(result['boot_bytes'],200)
        self.assertIsNone(result['rate'])

    def test_same_boot_counter_reset_no_negative_or_spike(self):
        self.tracker.sample(self.sample(1000))
        self.tracker.sample(self.sample(10,10))
        result=self.tracker.query()
        self.assertEqual(result['total_bytes'],0)
        self.assertEqual(result['resets'],1)
        self.assertIsNone(result['rate'])
        self.tracker.sample(self.sample(30,20))
        self.assertEqual(self.tracker.query()['total_bytes'],20)

    def test_different_cards_keep_separate_totals(self):
        self.tracker.sample(self.sample(100))
        self.tracker.sample(self.sample(1100,10))
        self.tracker.sample(self.sample(90000,20,device='card-b'))
        self.assertEqual(self.tracker.query()['total_bytes'],0)
        self.tracker.sample(self.sample(1600,30))
        self.assertEqual(self.tracker.query()['total_bytes'],1500)

    def test_day_boundary_vietnam_and_split(self):
        midnight=WriteTracker.bucket(self.now,86400)+86400
        self.now=midnight-5
        self.tracker.sample(self.sample(0))
        self.tracker.sample(self.sample(1000,10))
        days=self.tracker.query()['daily_history']
        self.assertEqual(len(days),2)
        self.assertAlmostEqual(days[0]['written'],500)
        self.assertAlmostEqual(days[1]['written'],500)
        self.assertEqual((days[1]['timestamp']+25200)%86400,0)

    def test_periodic_flush_is_batched_and_get_does_not_write(self):
        self.tracker.sample(self.sample(0))
        self.tracker.sample(self.sample(100,10))
        self.assertFalse(self.tracker.checkpoint())
        before=self.tracker.db.total_changes
        for _ in range(10):self.tracker.query()
        self.assertEqual(self.tracker.db.total_changes,before)
        with patch('storage_writes.time.monotonic',return_value=self.tracker.last_checkpoint+301):
            self.assertTrue(self.tracker.checkpoint())
        self.assertFalse(self.tracker.dirty)

    def test_close_flush_and_reopen_retains_graphs(self):
        self.tracker.sample(self.sample(0))
        self.tracker.sample(self.sample(1200,10))
        self.tracker.close()
        self.tracker=WriteTracker(self.path)
        self.tracker.sample(self.sample(1200,20))
        self.assertEqual(self.tracker.query()['total_bytes'],1200)
        self.assertAlmostEqual(sum(r['written'] for r in self.tracker.query()['daily_history']),1200)

    def test_retention_preserves_daily_and_cumulative(self):
        self.tracker.sample(self.sample(0))
        self.tracker.sample(self.sample(100,10))
        self.tracker.checkpoint(force=True)
        with patch('storage_writes.time.time',return_value=self.now+100*86400):
            self.tracker.sample(self.sample(1000,100*86400))
            self.tracker.checkpoint(force=True)
        self.assertEqual(self.tracker.query()['total_bytes'],1000)
        self.assertAlmostEqual(sum(r['written'] for r in self.tracker.query(days=0)['daily_history']),1000)
        minute_count=self.tracker.db.execute("SELECT COUNT(*) FROM buckets WHERE resolution='minute'").fetchone()[0]
        self.assertLessEqual(minute_count,10081)

    def test_gap_rate_unknown_and_clock_backwards_no_data_loss(self):
        self.tracker.sample(self.sample(0))
        self.tracker.sample(self.sample(100,100))
        self.assertIsNone(self.tracker.query()['rate'])
        self.tracker.sample(dict(self.sample(200,110),timestamp=self.now-10))
        self.assertEqual(self.tracker.query()['total_bytes'],200)

    def test_sqlite_failure_keeps_pending_for_retry(self):
        self.tracker.sample(self.sample(0))
        self.tracker.sample(self.sample(100,10))
        self.tracker.db.execute('PRAGMA query_only=ON')
        with self.assertRaises(sqlite3.OperationalError):self.tracker.checkpoint(force=True)
        self.assertTrue(self.tracker.pending)
        self.assertTrue(self.tracker.error)
        self.tracker.db.execute('PRAGMA query_only=OFF')
        self.tracker.checkpoint(force=True)
        self.assertEqual(self.tracker.query()['total_bytes'],100)

    def test_bounded_chart_keeps_sum(self):
        result=WriteTracker.compact([dict(timestamp=i,written=1,duration=1) for i in range(10000)])
        self.assertLessEqual(len(result),360)
        self.assertEqual(sum(r['written'] for r in result),10000)

    def test_api_auth_and_fixed_ranges(self):
        client=app.app.test_client()
        self.assertEqual(client.get('/api/storage-writes').status_code,302)
        with client.session_transaction() as session:session['logged_in']=True
        with patch.object(app,'ipc_read',return_value={'available':True,'total_bytes':123}) as ipc:
            self.assertEqual(client.get('/api/storage-writes?hours=../../etc/passwd').status_code,400)
            ipc.assert_not_called()
            self.assertEqual(client.get('/api/storage-writes?hours=168&days=0').json['data']['total_bytes'],123)
            ipc.assert_called_once_with('storage-writes',168,0)

    def test_ipc_query_uses_tracker_not_legacy_history_db(self):
        self.tracker.sample(self.sample(0))
        with patch.object(observer,'WRITE_TRACKER',self.tracker),patch.object(observer,'WRITE_ERROR',''),patch.object(observer,'connect',side_effect=AssertionError):
            self.assertTrue(observer.ram_query('storage-writes')['available'])

    def test_invalid_sample_preserves_totals(self):
        self.tracker.sample(self.sample(0))
        with self.assertRaises(ValueError):self.tracker.sample(self.sample(-1,10))
        self.assertEqual(self.tracker.query()['total_bytes'],0)

    def test_midnight_flushes_old_day_before_five_minute_interval(self):
        midnight=WriteTracker.bucket(self.now,86400)+86400
        self.now=midnight-5
        self.tracker.sample(self.sample(0))
        self.tracker.sample(self.sample(1000,10))
        self.assertTrue(self.tracker.day_changed)
        self.assertTrue(self.tracker.checkpoint())
        self.assertFalse(self.tracker.day_changed)
        days=self.tracker.db.execute("SELECT written FROM buckets WHERE resolution='day' ORDER BY bucket").fetchall()
        self.assertEqual(days,[(500.0,),(500.0,)])
