import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import History, LinuxCollector, demo_frame, investigate, report
from server import Mission, make_server


class CoreTests(unittest.TestCase):
    def test_dependency_failure_and_recovery(self):
        failed = demo_frame(1, 'database')
        self.assertEqual(next(s['status'] for s in failed['services'] if s['id']=='db'), 'down')
        self.assertTrue(all(s['status']=='degraded' for s in failed['services'] if s['id']!='db'))
        self.assertIn('Database is down', investigate(failed)[0])
        self.assertTrue(all(s['status']=='healthy' for s in demo_frame(2)['services']))

    def test_thresholds_and_invalid_scenario(self):
        self.assertIn('CPU exceeds', investigate(demo_frame(0,'cpu'))[0])
        self.assertIn('Disk exceeds', investigate(demo_frame(0,'disk'))[0])
        with self.assertRaises(ValueError): demo_frame(0,'oops')

    def test_history_persistence_retention_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'history.db';h=History(path)
            first=h.save(demo_frame(0,'database'));h.event('simulation','Database unavailable',first['id'])
            recovered=h.save(demo_frame(1));h.event('recovery','Recovered',recovered['id'])
            text=report(first,h.events())
            self.assertIn('Database unavailable',text);self.assertNotIn(': Recovered',text)
            self.assertEqual(len(History(path).frames()),2)
            for i in range(725): h.save(demo_frame(i))
            self.assertEqual(len(h.frames()),720)

    def test_collector_missing_proc(self):
        with tempfile.TemporaryDirectory() as d:
            f=LinuxCollector(d).sample()
            self.assertIsNone(f['metrics']['cpu_pct'])
            self.assertIsNone(f['metrics']['memory_pct'])
            self.assertEqual(f['services'],[])
            self.assertTrue(f['notes'])

    def test_collector_real_counters_with_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'net').mkdir()
            (root/'stat').write_text('cpu  10 0 10 80 0 0 0 0 0 0\n')
            (root/'meminfo').write_text('MemTotal: 1000 kB\nMemAvailable: 400 kB\n')
            (root/'net/dev').write_text('header\nheader\n eth0: 100 0 0 0\n lo: 9000 0 0\n')
            collector=LinuxCollector(root)
            self.assertIsNone(collector.sample()['metrics']['cpu_pct'])
            (root/'stat').write_text('cpu  30 0 10 160 0 0 0 0 0 0\n')
            (root/'net/dev').write_text('header\nheader\n eth0: 200 0 0 0\n')
            frame=collector.sample()
            self.assertEqual(frame['metrics']['cpu_pct'],20)
            self.assertEqual(frame['metrics']['memory_pct'],60)
            self.assertGreater(frame['metrics']['network_rx_kbps'],0)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.mission=Mission(Path(self.tmp.name)/'mission.db')
        self.server=make_server(self.mission,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.port=self.server.server_port

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def request(self,path,method='GET',body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        conn.request(method,path,body,headers or {})
        r=conn.getresponse();data=r.read();status=r.status;conn.close()
        return status,data

    def post(self,scenario,headers=None):
        h={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}', 'X-Mission-Token':self.mission.token}
        if headers: h.update(headers)
        return self.request('/api/scenario','POST',json.dumps({'scenario':scenario}),h)

    def test_complete_incident_replay_report_recovery(self):
        self.assertEqual(self.request('/')[0],200)
        original=json.loads(self.request('/api/state')[1])['frames'][-1]
        status,data=self.post('database');self.assertEqual(status,200);failed=json.loads(data)
        self.assertEqual(failed['scenario'],'database')
        self.post('nominal')
        state=json.loads(self.request('/api/state')[1])
        self.assertEqual(state['frames'][0]['id'],original['id'])
        self.assertEqual(state['frames'][-1]['scenario'],'nominal')
        status,data=self.request('/api/report?frame='+str(failed['id']))
        self.assertEqual(status,200);self.assertIn(b'Database is down',data)
        self.assertNotIn(b'All systems nominal',data)

    def test_session_origin_host_guards(self):
        self.assertEqual(self.post('cpu',{'Origin':'http://evil.example'})[0],403)
        self.assertEqual(self.post('cpu',{'X-Mission-Token':'wrong'})[0],403)
        self.assertEqual(self.request('/api/state',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/api/scenario','POST','{}')[0],403)

    def test_invalid_payloads_and_missing_frames(self):
        self.assertEqual(self.post('not-a-scenario')[0],400)
        self.assertEqual(self.post('cpu',{'Content-Type':'text/plain'})[0],415)
        h={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}','X-Mission-Token':self.mission.token}
        for body in ['[1]', '{bad', 'x'*1025]:
            self.assertEqual(self.request('/api/scenario','POST',body,h)[0],400)
        self.assertEqual(self.request('/api/report?frame=999999')[0],404)
        self.assertEqual(self.request('/../../core.py')[0],404)
        self.assertEqual(self.request('/data/demo.sqlite3')[0],404)

    def test_host_mode_rejects_chaos(self):
        self.mission.mode='host'
        self.assertEqual(self.post('database')[0],400)
        f=self.mission.sample();self.assertEqual(f['mode'],'host');self.assertEqual(f['services'],[])


if __name__=='__main__':unittest.main()
