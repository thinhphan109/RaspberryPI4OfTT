import unittest
from unittest.mock import patch
from types import SimpleNamespace
import hardware
import metrics
import security
import observer
import app

class HardwareTests(unittest.TestCase):
    def test_pin_mapping_and_power_are_locked(self):
        pins=hardware.PINOUT_MAP
        self.assertEqual(len(pins),40)
        self.assertEqual(set(p['bcm'] for p in pins if p['bcm'] is not None),set(range(28)))
        self.assertEqual(pins[10]['bcm'],17)
        self.assertTrue(all(not p['writable'] for p in pins))

    def test_pinctrl_parser_does_not_invent_levels(self):
        rows=hardware.parse_pinctrl(' 0: ip pu | hi // GPIO0\n18: a2 pn | lo // PWM\n27: op pd | hi\ninvalid')
        self.assertEqual(rows[0]['func'],'INPUT')
        self.assertEqual(rows[18]['func'],'A2')
        self.assertEqual(rows[27]['level'],1)
        self.assertNotIn(5,rows)

    def test_all_power_history_flags_and_unavailable(self):
        with patch.object(metrics.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='throttled=0xf0000')):
            p=metrics.power_status()
        self.assertEqual(p['status'],'warning')
        self.assertTrue(p['frequency_capped_occurred'])
        self.assertTrue(p['soft_temp_limit_occurred'])
        with patch.object(metrics.subprocess,'run',side_effect=OSError):
            self.assertEqual(metrics.power_status()['status'],'unknown')

    def test_network_reset_and_removed_interface(self):
        old=metrics._network_last
        self.addCleanup(setattr,metrics,'_network_last',old)
        metrics._network_last={'wlan0':(1,1000,1000),'eth0':(1,0,0)}
        raw='h\nh\n wlan0: 10 0 0 0 0 0 0 0 20 0 0 0 0 0 0 0'
        with patch.object(metrics,'_read',return_value=raw):data=metrics.network_rates(2)
        self.assertIsNone(data[0]['rx_rate'])
        self.assertNotIn('eth0',metrics._network_last)

    def test_security_ipv6_and_failed_key(self):
        row=security.parse_record({'MESSAGE':'Failed publickey for invalid user root from 2001:db8::1 port 44 ssh2','__REALTIME_TIMESTAMP':'1000000','__CURSOR':'a'})
        self.assertEqual(row['ip'],'2001:db8::1')
        self.assertEqual(row['kind'],'failed')
        self.assertIsNone(security.parse_record({'MESSAGE':'pam_unix authentication failure'}))

    def test_private_gpio_and_disabled_control_csrf_json(self):
        client=app.app.test_client()
        self.assertEqual(client.get('/api/gpio/status').status_code,302)
        with client.session_transaction() as session:session.update(logged_in=True,csrf='token')
        self.assertEqual(client.post('/api/gpio/control',json={'csrf':123}).status_code,403)
        self.assertEqual(client.post('/api/gpio/control',json='invalid').status_code,403)
        response=client.post('/api/gpio/control',json={'csrf':'token','bcm':17,'value':1})
        self.assertEqual(response.status_code,403)
        self.assertIn('GPIO_CONTROL_DISABLED',response.json['error'])

    def test_history_ram_bounded_and_no_db_polling(self):
        with patch.object(observer,'reader',side_effect=AssertionError('Disk database read')),patch.object(observer,'connect',side_effect=AssertionError('Disk database write')),patch.object(observer,'ipc_read',return_value=[]):
            self.assertEqual(observer.history(),[])
        self.assertEqual(observer.SAMPLES.maxlen,10080)

    def test_request_metrics_read_virtual_files_without_commands(self):
        files={'/sys/class/thermal/thermal_zone0/temp':'45000','/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq':'1500000','/proc/meminfo':'MemTotal: 1000 kB\nMemAvailable: 500 kB', '/proc/stat':'cpu 10 0 0 90 0 0 0 0','/proc/net/dev':'h\nh\n wlan0: 200 0 0 0 0 0 0 0 300 0 0 0 0 0 0 0','/proc/net/route':'h\nwlan0 00000000 00000000 0001 0 0 100 00000000'}
        snapshot=dict(monotonic=1,cpu_ticks=[50,40],network=[dict(name='wlan0',rx=100,tx=100,rx_rate=0,tx_rate=0)])
        with patch.object(metrics,'_read',side_effect=lambda path:files.get(path)),patch.object(metrics.time,'monotonic',return_value=11),patch.object(metrics.subprocess,'run',side_effect=AssertionError('Subprocess in fast metrics')):
            data=metrics.fresh(snapshot)
        self.assertEqual(data['temperature'],45)
        self.assertEqual(data['frequency_mhz'],1500)
        self.assertEqual(data['network'][0]['rx_rate'],10)
        self.assertEqual(data['network'][0]['tx_rate'],20)
        self.assertEqual(data['ram']['percent'],50)
        self.assertEqual(snapshot['network'][0]['rx'],100)

if __name__=='__main__':unittest.main()
