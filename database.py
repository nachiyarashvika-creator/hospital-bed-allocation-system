import sqlite3
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS wards (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, gender TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS beds (
 id INTEGER PRIMARY KEY, ward_id INTEGER NOT NULL REFERENCES wards(id),
 label TEXT NOT NULL, kind TEXT NOT NULL, ventilator INTEGER NOT NULL DEFAULT 0,
 distance INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'ready'
 CHECK(status IN ('ready','occupied','cleaning','reserved')),
 cleaning_until REAL);
CREATE TABLE IF NOT EXISTS patients (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, gender TEXT NOT NULL,
 condition TEXT NOT NULL, severity INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 5),
 status TEXT NOT NULL CHECK(status IN ('waiting','admitted','reserved','discharged')),
 bed_id INTEGER UNIQUE REFERENCES beds(id), created_at REAL NOT NULL);
'''


def connect(path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript(SCHEMA)
        if db.execute('SELECT COUNT(*) FROM wards').fetchone()[0]:
            return
        db.executemany('INSERT INTO wards VALUES (?,?,?)', [
            (1, 'General • Female', 'female'), (2, 'General • Male', 'male'),
            (3, 'Critical Care', 'mixed'), (4, 'Isolation', 'mixed'),
            (5, 'General • Inclusive', 'mixed')])
        beds = [
            (1,1,'F-01','general',0,40), (2,1,'F-02','general',0,42),
            (3,2,'M-01','general',0,35), (4,2,'M-02','general',0,38),
            (5,3,'ICU-01','icu',0,8), (6,3,'ICU-02','icu',1,12),
            (7,3,'ICU-03','icu',1,16), (8,4,'ISO-01','isolation',0,50),
            (9,4,'ISO-02','isolation',0,52), (10,5,'G-01','general',0,30),
            (11,5,'G-02','general',0,32), (12,5,'G-03','general',0,34)]
        db.executemany('INSERT INTO beds(id,ward_id,label,kind,ventilator,distance) VALUES (?,?,?,?,?,?)', beds)
        db.executemany('INSERT INTO patients VALUES (?,?,?,?,?,?,?,?)', [
            (1,'Demo Asha','female','general',2,'admitted',1,1),
            (2,'Demo Ravi','male','icu',4,'admitted',5,2),
            (3,'Demo Sam','other','general',1,'admitted',10,3)])
        db.execute("UPDATE beds SET status='occupied' WHERE id IN (1,5,10)")
