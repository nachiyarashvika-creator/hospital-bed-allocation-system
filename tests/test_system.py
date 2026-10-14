import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from app import create_app
from database import connect
from models import Person, Patient, Doctor, Nurse, bed_from_row


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, 'test.db')
        self.app = create_app(self.path)
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def patient(self, **changes):
        data = dict(name='Test Patient', gender='female', condition='general', severity=3)
        data.update(changes)
        return data

    def state(self):
        return self.client.get('/api/state').get_json()

    def test_frontend_and_seed_repeatability(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        with self.client.get('/static/app.js') as response:
            self.assertEqual(response.status_code, 200)
        create_app(self.path)
        self.assertEqual(len(self.state()['beds']), 12)
        self.assertEqual(len(self.state()['patients']), 3)

    def test_gender_and_specialized_allocation(self):
        for condition, expected in [('general','general'),('isolation','isolation'),('ventilator','icu')]:
            r = self.client.post('/api/admit',json=self.patient(condition=condition))
            self.assertEqual(r.status_code, 201)
            bed = r.get_json()['bed']
            self.assertEqual(bed['kind'], expected)
            self.assertIn(bed['gender'], ('female','mixed'))
            if condition == 'ventilator':
                self.assertEqual(bed['ventilator'], 1)

    def test_dirty_bed_cannot_allocate_and_queue_priority(self):
        self.client.post('/api/patients/1/discharge',json={})
        with connect(self.path) as db:
            self.assertEqual(db.execute('SELECT status FROM beds WHERE id=1').fetchone()[0], 'cleaning')
            # Reserve the remaining ready beds to force an actual waiting queue.
            db.execute("UPDATE beds SET status='reserved' WHERE status='ready'")
        low = self.client.post('/api/admit',json=self.patient(name='Low',severity=1)).get_json()
        high = self.client.post('/api/admit',json=self.patient(name='High',severity=5)).get_json()
        self.assertEqual(high['status'],'waiting')
        self.assertEqual(low['status'],'waiting')
        with connect(self.path) as db:
            db.execute('UPDATE beds SET cleaning_until=? WHERE id=1',(time.time()-1,))
        patients = {p['id']:p for p in self.state()['patients']}
        self.assertEqual(patients[high['patient_id']]['bed_id'],1)
        self.assertEqual(patients[low['patient_id']]['status'],'waiting')

    def test_fifo_and_skip_incompatible(self):
        with connect(self.path) as db:
            db.execute("UPDATE beds SET status='reserved' WHERE status='ready'")
        incompatible = self.client.post('/api/admit',json=self.patient(condition='isolation',severity=5)).get_json()
        first = self.client.post('/api/admit',json=self.patient(name='First')).get_json()
        second = self.client.post('/api/admit',json=self.patient(name='Second')).get_json()
        with connect(self.path) as db:
            db.execute("UPDATE beds SET status='ready' WHERE id=2")
        patients = {p['id']:p for p in self.state()['patients']}
        self.assertEqual(patients[first['patient_id']]['bed_id'],2)
        self.assertEqual(patients[second['patient_id']]['status'],'waiting')
        self.assertEqual(patients[incompatible['patient_id']]['status'],'waiting')

    def test_emergency_nearest_confirm_and_cancel(self):
        r = self.client.post('/api/emergency',json=self.patient(condition='ventilator',severity=5)).get_json()
        self.assertEqual(r['bed']['id'],6)
        self.assertEqual(r['status'],'reserved')
        self.assertEqual(self.client.post(f"/api/patients/{r['patient_id']}/confirm",json={}).status_code,200)
        self.client.post(f"/api/patients/{r['patient_id']}/discharge",json={})
        bed = next(b for b in self.state()['beds'] if b['id']==6)
        self.assertEqual(bed['status'],'cleaning')
        r = self.client.post('/api/emergency',json=self.patient(condition='icu',severity=5)).get_json()
        self.client.post(f"/api/patients/{r['patient_id']}/discharge",json={})
        bed = next(b for b in self.state()['beds'] if b['id']==r['bed']['id'])
        self.assertEqual(bed['status'],'ready')

    def test_emergency_shift_suggestion_no_automatic_transfer(self):
        with connect(self.path) as db:
            db.execute("UPDATE patients SET condition='general',severity=1 WHERE id=2")
            db.execute("UPDATE beds SET status='reserved' WHERE id IN (6,7)")
        r = self.client.post('/api/emergency',json=self.patient(condition='icu',severity=5)).get_json()
        self.assertEqual(r['status'],'waiting')
        self.assertEqual(r['shift_suggestions'][0]['patient_id'],2)
        self.assertEqual(next(p for p in self.state()['patients'] if p['id']==2)['bed_id'],5)

    def test_ventilator_transfer_requires_ventilator_source(self):
        with connect(self.path) as db:
            db.execute("UPDATE patients SET condition='general',severity=1 WHERE id=2")
            db.execute("UPDATE beds SET status='reserved' WHERE id IN (6,7)")
        r = self.client.post('/api/emergency',json=self.patient(condition='ventilator',severity=5)).get_json()
        self.assertEqual(r['status'],'waiting')
        self.assertEqual(r['shift_suggestions'],[])

    def test_validation_and_double_discharge(self):
        for change in [dict(name=''),dict(gender='invalid'),dict(condition='invalid'),dict(severity=True),dict(severity=6)]:
            self.assertEqual(self.client.post('/api/admit',json=self.patient(**change)).status_code,400)
        self.assertEqual(self.client.post('/api/admit',json=[]).status_code,400)
        self.assertEqual(self.client.post('/api/emergency',json=self.patient()).status_code,400)
        self.assertEqual(self.client.post('/api/patients/999/discharge',json={}).status_code,400)
        self.assertEqual(self.client.post('/api/patients/1/discharge',json={}).status_code,200)
        self.assertEqual(self.client.post('/api/patients/1/discharge',json={}).status_code,400)

    def test_concurrent_allocation(self):
        def admit(i):
            with self.app.test_client() as client:
                return client.post('/api/admit',json=self.patient(name=f'Concurrent {i}')).get_json()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(admit,range(8)))
        ids = [r['bed']['id'] for r in results if r['bed']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(any(r['status']=='waiting' for r in results))

    def test_oop_abstraction_and_polymorphism(self):
        with self.assertRaises(TypeError):
            Person('Abstract')
        p = Patient('Alice','female','general',1)
        p.name = 'New name'
        self.assertEqual(p.name,'New name')
        self.assertTrue(Doctor('Doctor').can_shift(p))
        self.assertEqual(Nurse('Nurse').role,'Nurse')
        with connect(self.path) as db:
            beds = [bed_from_row(db.execute('SELECT * FROM beds WHERE id=?',(i,)).fetchone()) for i in (1,5,8)]
        self.assertEqual([b.cleaning_seconds for b in beds],[30,60,90])
        self.assertEqual([b.supports(p) for b in beds],[True,True,False])


if __name__ == '__main__':
    unittest.main()
