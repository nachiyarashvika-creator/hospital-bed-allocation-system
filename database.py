"""Persistent storage with a safe migration of the original single-hospital demo."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS hospitals (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL UNIQUE,
 city TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, hospital_id INTEGER NOT NULL REFERENCES hospitals(id),
 email TEXT NOT NULL, password_hash TEXT NOT NULL,
 UNIQUE(hospital_id,email));
CREATE TABLE IF NOT EXISTS wards (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, gender TEXT NOT NULL,
 hospital_id INTEGER NOT NULL DEFAULT 1 REFERENCES hospitals(id));
CREATE TABLE IF NOT EXISTS beds (
 id INTEGER PRIMARY KEY, ward_id INTEGER NOT NULL REFERENCES wards(id),
 label TEXT NOT NULL, kind TEXT NOT NULL, ventilator INTEGER NOT NULL DEFAULT 0,
 distance INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'ready'
 CHECK(status IN ('ready','occupied','cleaning','reserved')), cleaning_until REAL);
CREATE TABLE IF NOT EXISTS patients (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, gender TEXT NOT NULL,
 condition TEXT NOT NULL, severity INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 5),
 status TEXT NOT NULL CHECK(status IN ('waiting','admitted','reserved','discharged')),
 bed_id INTEGER UNIQUE REFERENCES beds(id), created_at REAL NOT NULL,
 hospital_id INTEGER NOT NULL DEFAULT 1 REFERENCES hospitals(id));
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY, hospital_id INTEGER NOT NULL REFERENCES hospitals(id),
 user_id INTEGER NOT NULL REFERENCES users(id), action TEXT NOT NULL,
 patient_id INTEGER REFERENCES patients(id), created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts (
 key TEXT PRIMARY KEY, failures INTEGER NOT NULL, started_at REAL NOT NULL);
'''


@contextmanager
def connect(path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def seed_hospital(db, hospital_id, demo=False):
    # Composition: each hospital owns its own wards and beds.
    definitions = [
        ('General • Female','female', [('F-01','general',0,40),('F-02','general',0,42)]),
        ('General • Male','male', [('M-01','general',0,35),('M-02','general',0,38)]),
        ('Critical Care','mixed', [('ICU-01','icu',0,8),('ICU-02','icu',1,12),('ICU-03','icu',1,16)]),
        ('Isolation','mixed', [('ISO-01','isolation',0,50),('ISO-02','isolation',0,52)]),
        ('General • Inclusive','mixed', [('G-01','general',0,30),('G-02','general',0,32),('G-03','general',0,34)])]
    bed_ids = []
    for name, gender, beds in definitions:
        ward_id = db.execute('INSERT INTO wards(name,gender,hospital_id) VALUES (?,?,?)', (name,gender,hospital_id)).lastrowid
        for label,kind,ventilator,distance in beds:
            bed_ids.append(db.execute('INSERT INTO beds(ward_id,label,kind,ventilator,distance) VALUES (?,?,?,?,?)', (ward_id,label,kind,ventilator,distance)).lastrowid)
    if demo:
        for name,gender,condition,severity,index in [('Demo Asha','female','general',2,0),('Demo Ravi','male','icu',4,4),('Demo Sam','other','general',1,9)]:
            bed_id = bed_ids[index]
            db.execute('INSERT INTO patients(name,gender,condition,severity,status,bed_id,created_at,hospital_id) VALUES (?,?,?,?,?,?,?,?)', (name,gender,condition,severity,'admitted',bed_id,index+1,hospital_id))
            db.execute("UPDATE beds SET status='occupied' WHERE id=?", (bed_id,))


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        existing = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='wards'").fetchone()
        legacy = existing and 'hospital_id' not in [r['name'] for r in db.execute('PRAGMA table_info(wards)')]
        if legacy:
            backup = Path(str(path) + '.pre-login.bak')
            if not backup.exists():
                target = sqlite3.connect(backup)
                try:
                    db.backup(target)
                finally:
                    target.close()
        db.executescript(SCHEMA)
        db.execute("INSERT OR IGNORE INTO hospitals(id,name,code,city) VALUES (1,'Smart Hospital','smart-hospital','Demo city')")
        if legacy:
            db.execute('ALTER TABLE wards ADD COLUMN hospital_id INTEGER REFERENCES hospitals(id)')
            db.execute('ALTER TABLE patients ADD COLUMN hospital_id INTEGER REFERENCES hospitals(id)')
            db.execute('UPDATE wards SET hospital_id=1 WHERE hospital_id IS NULL')
            db.execute('UPDATE patients SET hospital_id=1 WHERE hospital_id IS NULL')
        if not db.execute('SELECT COUNT(*) FROM wards WHERE hospital_id=1').fetchone()[0]:
            seed_hospital(db, 1, demo=True)
