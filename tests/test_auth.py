import os
import sqlite3
import tempfile
import time
import unittest
from app import create_app
from database import connect
from werkzeug.security import check_password_hash


class HospitalAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name,'auth.db')
        self.app = create_app(self.path)
        self.app.config['TESTING'] = True
        self.a = self.app.test_client()
        self.b = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def token(self,client):
        client.get('/login')
        with client.session_transaction() as session:
            return session['csrf_token']

    def register(self,client,code='sunrise',**changes):
        data=dict(hospital_name='Sunrise Hospital',code=code,city='Chennai',email='admin@example.com',password='A-long-password-123',csrf_token=self.token(client))
        data.update(changes)
        return client.post('/register',data=data)

    def post(self,client,path,data):
        with client.session_transaction() as session:
            token=session['csrf_token']
        return client.post(path,json=data,headers={'X-CSRF-Token':token})

    def test_unauthenticated_pages_and_api(self):
        self.assertEqual(self.a.get('/').status_code,302)
        self.assertEqual(self.a.get('/api/state').status_code,401)
        self.assertEqual(self.a.post('/api/admit',json={}).status_code,401)
        self.assertEqual(self.a.get('/health').get_json(),{'status':'ok'})
        response=self.a.get('/login')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(response.headers['X-Frame-Options'],'DENY')

    def test_registration_login_logout_and_hashing(self):
        initial=self.token(self.a)
        self.assertEqual(self.register(self.a).status_code,302)
        state=self.a.get('/api/state').get_json()
        self.assertEqual(state['hospital'],'Sunrise Hospital')
        self.assertEqual(len(state['beds']),12)
        self.assertEqual(state['patients'],[])
        self.assertEqual(self.a.get('/').status_code,200)
        with connect(self.path) as db:
            hashed=db.execute('SELECT password_hash FROM users').fetchone()[0]
            self.assertNotEqual(hashed,'A-long-password-123')
            self.assertTrue(check_password_hash(hashed,'A-long-password-123'))
        with self.a.session_transaction() as session:
            self.assertNotEqual(initial,session['csrf_token'])
            self.assertTrue(session.permanent)
        self.assertEqual(self.post(self.a,'/logout',{}).status_code,302)
        self.assertEqual(self.a.get('/api/state').status_code,401)
        response=self.a.post('/login',data=dict(code='SUNRISE',email='ADMIN@example.com',password='A-long-password-123',csrf_token=self.token(self.a)))
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.a.get('/api/state').status_code,200)

    def test_hospital_isolation_and_cross_hospital_writes(self):
        self.register(self.a,'hospital-a')
        self.register(self.b,'hospital-b',hospital_name='Second Hospital')
        patient=self.post(self.a,'/api/emergency',dict(name='Private patient',gender='female',condition='icu',severity=5)).get_json()
        state_b=self.b.get('/api/state').get_json()
        self.assertEqual(state_b['patients'],[])
        self.assertEqual(state_b['activity'],[])
        self.assertTrue(all(b['status']=='ready' for b in state_b['beds']))
        for action in ('confirm','discharge'):
            self.assertEqual(self.post(self.b,f"/api/patients/{patient['patient_id']}/{action}",{}).status_code,400)
        state_a=self.a.get('/api/state').get_json()
        self.assertEqual(state_a['patients'][0]['status'],'reserved')
        self.assertEqual(self.post(self.b,'/api/beds',dict(label='Foreign bed',ward_id=state_a['wards'][0]['id'],kind='general',distance=10)).status_code,400)
        self.assertTrue(set(b['id'] for b in state_a['beds']).isdisjoint(b['id'] for b in state_b['beds']))

    def test_csrf_missing_wrong_and_old_token(self):
        self.assertEqual(self.a.post('/register',data={}).status_code,403)
        old=self.token(self.a)
        self.register(self.a)
        self.assertEqual(self.a.post('/api/admit',json={}).status_code,403)
        self.assertEqual(self.a.post('/api/admit',json={},headers={'X-CSRF-Token':old}).status_code,403)
        self.assertEqual(self.a.post('/logout',data={}).status_code,403)
        self.assertEqual(self.a.get('/api/state').status_code,200)

    def test_invalid_and_duplicate_registration(self):
        for changes in [dict(password='short'),dict(code='../bad'),dict(email='invalid'),dict(hospital_name='')]:
            self.assertEqual(self.register(self.a,**changes).status_code,400)
        self.assertEqual(self.register(self.a).status_code,302)
        self.assertEqual(self.register(self.b).status_code,409)
        # The migrated demo hospital cannot be claimed through public registration.
        self.assertEqual(self.register(self.b,code='smart-hospital').status_code,409)

    def test_login_throttle_and_expiry(self):
        self.register(self.a)
        for _ in range(5):
            response=self.b.post('/login',data=dict(code='sunrise',email='admin@example.com',password='wrong',csrf_token=self.token(self.b)))
            self.assertEqual(response.status_code,400)
        response=self.b.post('/login',data=dict(code='sunrise',email='admin@example.com',password='A-long-password-123',csrf_token=self.token(self.b)))
        self.assertEqual(response.status_code,429)
        with connect(self.path) as db:
            db.execute('UPDATE login_attempts SET started_at=?',(time.time()-901,))
        response=self.b.post('/login',data=dict(code='sunrise',email='admin@example.com',password='A-long-password-123',csrf_token=self.token(self.b)))
        self.assertEqual(response.status_code,302)

    def test_hospital_setup_and_audit(self):
        self.register(self.a)
        ward=self.post(self.a,'/api/wards',dict(name='New ICU',gender='mixed'))
        self.assertEqual(ward.status_code,201)
        data=dict(label='ICU-NEW',ward_id=ward.get_json()['id'],kind='icu',ventilator=True,distance=4)
        self.assertEqual(self.post(self.a,'/api/beds',data).status_code,201)
        self.assertEqual(self.post(self.a,'/api/beds',data).status_code,400)
        invalid=dict(data,label='Invalid',kind='general')
        self.assertEqual(self.post(self.a,'/api/beds',invalid).status_code,400)
        admission=self.post(self.a,'/api/emergency',dict(name='Test',gender='female',condition='ventilator',severity=5)).get_json()
        self.assertEqual(admission['bed']['label'],'ICU-NEW')
        activity=self.a.get('/api/state').get_json()['activity']
        self.assertEqual(activity[0]['action'],'Emergency reservation')
        self.assertEqual(activity[0]['email'],'admin@example.com')

    def test_session_survives_restart_and_cookies(self):
        self.register(self.a)
        cookie=self.a.get_cookie('session')
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site,'Lax')
        restarted=create_app(self.path)
        client=restarted.test_client()
        client.set_cookie('session',cookie.value)
        self.assertEqual(client.get('/api/state').status_code,200)

    def test_legacy_migration_preserves_records(self):
        path=os.path.join(self.temp.name,'legacy.db')
        db=sqlite3.connect(path)
        db.executescript('''
        CREATE TABLE wards(id INTEGER PRIMARY KEY,name TEXT,gender TEXT);
        CREATE TABLE beds(id INTEGER PRIMARY KEY,ward_id INTEGER,label TEXT,kind TEXT,ventilator INTEGER,distance INTEGER,status TEXT,cleaning_until REAL);
        CREATE TABLE patients(id INTEGER PRIMARY KEY,name TEXT,gender TEXT,condition TEXT,severity INTEGER,status TEXT,bed_id INTEGER,created_at REAL);
        INSERT INTO wards VALUES(1,'Existing Ward','female');
        INSERT INTO beds VALUES(1,1,'OLD-1','general',0,10,'occupied',NULL);
        INSERT INTO patients VALUES(1,'Preserved','female','general',2,'admitted',1,1);
        ''')
        db.commit()
        db.close()
        create_app(path)
        create_app(path)
        self.assertTrue(os.path.exists(path+'.pre-login.bak'))
        with connect(path) as db:
            row=db.execute('SELECT * FROM patients').fetchone()
            self.assertEqual(row['name'],'Preserved')
            self.assertEqual(row['hospital_id'],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM patients').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)
