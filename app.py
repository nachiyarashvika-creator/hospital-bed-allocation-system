"""REST API with transaction-protected allocation and persistent SQLite state."""
import os
import time
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from database import connect, initialize
from models import Patient, Doctor, Nurse, Hospital, Ward, BedAllocator, bed_from_row

BED_QUERY = '''SELECT b.*, w.name AS ward_name, w.gender FROM beds b
 JOIN wards w ON w.id=b.ward_id'''


def create_app(database_path=None):
    app = Flask(__name__)
    app.config['DATABASE'] = database_path or os.environ.get('DATABASE_PATH') or os.path.join(app.instance_path, 'hospital.db')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
    initialize(app.config['DATABASE'])
    allocator = BedAllocator()
    doctor, nurse = Doctor('Dr. Meera'), Nurse('Nurse Arun')

    def patient_from_row(row):
        return Patient(row['name'], row['gender'], row['condition'], row['severity'])

    def rows(db):
        return db.execute(BED_QUERY).fetchall()

    def assign_waiting(db):
        # Highest severity first; FIFO ties. Incompatible patients stay queued.
        for row in db.execute("SELECT * FROM patients WHERE status='waiting' ORDER BY severity DESC, created_at, id").fetchall():
            bed = allocator.suggest(patient_from_row(row), rows(db))
            if bed:
                db.execute("UPDATE beds SET status='occupied' WHERE id=?", (bed['id'],))
                db.execute("UPDATE patients SET status='admitted',bed_id=? WHERE id=?", (bed['id'], row['id']))

    def maintain(db):
        now = time.time()
        for row in db.execute(BED_QUERY + " WHERE b.status='cleaning'").fetchall():
            if nurse.can_release(bed_from_row(row), now):
                db.execute("UPDATE beds SET status='ready',cleaning_until=NULL WHERE id=?", (row['id'],))
        assign_waiting(db)

    def body_patient():
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError('Send a JSON object.')
        patient = Patient(data.get('name'), data.get('gender'), data.get('condition'), data.get('severity'))
        if len(patient.name) > 100:
            raise ValueError('Name must be at most 100 characters.')
        return patient

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/api/state')
    def state():
        with connect(app.config['DATABASE']) as db:
            db.execute('BEGIN IMMEDIATE')
            maintain(db)
            wards = [dict(r) for r in db.execute('SELECT * FROM wards')]
            hospital = Hospital('Smart Hospital', [Ward(w['name'], w['gender']) for w in wards])
            beds = [dict(r) for r in rows(db)]
            patients = [dict(r) for r in db.execute('SELECT * FROM patients ORDER BY severity DESC,created_at,id')]
        return jsonify(hospital=hospital.name, wards=wards, beds=beds, patients=patients,
                       staff=[{'name': p.name, 'role': p.role} for p in (doctor, nurse)], server_time=time.time())

    @app.post('/api/suggest')
    def suggest():
        patient = body_patient()
        with connect(app.config['DATABASE']) as db:
            db.execute('BEGIN IMMEDIATE')
            maintain(db)
            bed = allocator.suggest(patient, rows(db))
        return jsonify(bed=dict(bed) if bed else None)

    def admit(emergency=False):
        patient = body_patient()
        if emergency and patient.condition not in ('icu', 'ventilator'):
            raise ValueError('Emergency reservation requires ICU or ventilator condition.')
        with connect(app.config['DATABASE']) as db:
            # Serialize writes: two simultaneous requests cannot claim one bed.
            db.execute('BEGIN IMMEDIATE')
            maintain(db)
            bed = allocator.suggest(patient, rows(db), emergency=emergency)
            status = ('reserved' if emergency else 'admitted') if bed else 'waiting'
            cursor = db.execute('INSERT INTO patients(name,gender,condition,severity,status,bed_id,created_at) VALUES (?,?,?,?,?,?,?)',
                (patient.name, patient.gender, patient.condition, patient.severity, status, bed['id'] if bed else None, time.time()))
            if bed:
                db.execute('UPDATE beds SET status=? WHERE id=?', ('reserved' if emergency else 'occupied', bed['id']))
            shifts = []
            if emergency and not bed:
                for row in db.execute("SELECT p.*,b.label FROM patients p JOIN beds b ON b.id=p.bed_id WHERE p.status='admitted' AND b.kind='icu'"):
                    source = next(b for b in rows(db) if b['id'] == row['bed_id'])
                    if not bed_from_row(source).supports(patient) or not Ward(source['ward_name'], source['gender']).accepts(patient):
                        continue
                    candidate = patient_from_row(row)
                    target = allocator.suggest(candidate, [b for b in rows(db) if b['kind'] == 'general'])
                    if doctor.can_shift(candidate) and target:
                        shifts.append({'patient_id': row['id'], 'name': row['name'], 'from': row['label'], 'to': target['label']})
        return jsonify(patient_id=cursor.lastrowid, status=status, bed=dict(bed) if bed else None,
                       shift_suggestions=shifts,
                       message='Transfer suggestions require doctor approval; no patient was moved.' if shifts else ''), 201

    @app.post('/api/admit')
    def admit_route():
        return admit()

    @app.post('/api/emergency')
    def emergency_route():
        return admit(True)

    @app.post('/api/patients/<int:patient_id>/confirm')
    def confirm(patient_id):
        with connect(app.config['DATABASE']) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM patients WHERE id=?', (patient_id,)).fetchone()
            if not row or row['status'] != 'reserved':
                raise ValueError('Patient has no active reservation.')
            db.execute("UPDATE patients SET status='admitted' WHERE id=?", (patient_id,))
            db.execute("UPDATE beds SET status='occupied' WHERE id=?", (row['bed_id'],))
        return jsonify(message='Emergency admission confirmed.')

    @app.post('/api/patients/<int:patient_id>/discharge')
    def discharge(patient_id):
        with connect(app.config['DATABASE']) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM patients WHERE id=?', (patient_id,)).fetchone()
            if not row or row['status'] not in ('admitted', 'reserved', 'waiting'):
                raise ValueError('Patient is not active.')
            if row['bed_id']:
                bed_row = db.execute(BED_QUERY + ' WHERE b.id=?', (row['bed_id'],)).fetchone()
                if row['status'] == 'reserved':
                    db.execute("UPDATE beds SET status='ready' WHERE id=?", (row['bed_id'],))
                else:
                    deadline = time.time() + bed_from_row(bed_row).cleaning_seconds
                    db.execute("UPDATE beds SET status='cleaning',cleaning_until=? WHERE id=?", (deadline,row['bed_id']))
            db.execute("UPDATE patients SET status='discharged',bed_id=NULL WHERE id=?", (patient_id,))
            maintain(db)
        return jsonify(message='Patient discharged/cancelled. Occupied beds must finish cleaning before reuse.')

    return app


app = create_app()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '5000')), debug=False)
