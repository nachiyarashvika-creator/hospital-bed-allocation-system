"""Hospital account routes, password hashing and session/CSRF protection."""
import hmac
import re
import secrets
import time
from datetime import timedelta
from pathlib import Path
from flask import g, session, request, redirect, url_for, jsonify, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from database import connect, seed_hospital


def install_auth(app):
    key = app.config.get('SECRET_KEY')
    if not key:
        # Stable local key across restarts; never checked into source control.
        path = Path(app.config['DATABASE'] + '.session-key')
        try:
            with path.open('x') as file:
                path.chmod(0o600)
                file.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        key = path.read_text().strip()
    app.config.update(SECRET_KEY=key, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=timedelta(hours=8))

    @app.context_processor
    def auth_context():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)
        return dict(csrf_token=session['csrf_token'], account=getattr(g,'account',None))

    @app.before_request
    def protect():
        g.account = None
        if session.get('user_id'):
            with connect(app.config['DATABASE']) as db:
                row = db.execute('SELECT u.id,u.email,u.hospital_id,h.name,h.code,h.city FROM users u JOIN hospitals h ON h.id=u.hospital_id WHERE u.id=?', (session['user_id'],)).fetchone()
            if row:
                g.account = dict(row)
            else:
                session.clear()
        public = request.endpoint in ('login','register','health','static')
        if not public and not g.account:
            if request.path.startswith('/api/'):
                return jsonify(error='Please sign in to your hospital.'),401
            return redirect(url_for('login'))
        if request.method in ('POST','PUT','PATCH','DELETE'):
            submitted = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token','')
            expected = session.get('csrf_token','')
            if not expected or not hmac.compare_digest(submitted.encode(),expected.encode()):
                return jsonify(error='Session security check failed. Reload the page and try again.'),403

    @app.after_request
    def response_security(response):
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        return response

    def start_session(user_id):
        session.clear()
        session['user_id'] = user_id
        session['csrf_token'] = secrets.token_hex(32)
        session.permanent = True

    @app.route('/login',methods=['GET','POST'])
    def login():
        if request.method == 'GET':
            return redirect(url_for('index')) if g.account else render_template('auth.html', mode='login')
        code = request.form.get('code','').strip().lower()[:60]
        email = request.form.get('email','').strip().lower()[:254]
        password = request.form.get('password','')
        now = time.time()
        # Persistent account and IP throttling. Do not trust client-supplied IP headers.
        keys = [('account:'+code+':'+email,5),('ip:'+str(request.remote_addr),30)]
        with connect(app.config['DATABASE']) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_attempts WHERE started_at < ?', (now-900,))
            for key,limit in keys:
                row = db.execute('SELECT * FROM login_attempts WHERE key=?',(key,)).fetchone()
                if row and row['failures'] >= limit:
                    return render_template('auth.html',mode='login',error='Too many attempts. Try again in 15 minutes.'),429
            user = db.execute('SELECT u.* FROM users u JOIN hospitals h ON h.id=u.hospital_id WHERE h.code=? AND u.email=?',(code,email)).fetchone()
            # Also perform hashing for nonexistent users to reduce timing leakage.
            valid = check_password_hash(user['password_hash'] if user else app.config['DUMMY_PASSWORD_HASH'], password)
            if not user or not valid:
                for key,limit in keys:
                    db.execute('INSERT INTO login_attempts VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET failures=failures+1',(key,now))
                return render_template('auth.html',mode='login',error='Hospital code, email or password is incorrect.'),400
            db.execute('DELETE FROM login_attempts WHERE key=?',(keys[0][0],))
        start_session(user['id'])
        return redirect(url_for('index'))

    @app.route('/register',methods=['GET','POST'])
    def register():
        if request.method == 'GET':
            return render_template('auth.html',mode='register')
        name = request.form.get('hospital_name','').strip()
        code = request.form.get('code','').strip().lower()
        city = request.form.get('city','').strip()
        email = request.form.get('email','').strip().lower()
        password = request.form.get('password','')
        if not 2 <= len(name) <= 100 or not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,39}',code):
            return render_template('auth.html',mode='register',error='Enter a hospital name and a 3–40 character code using lowercase letters, numbers and hyphens.'),400
        if len(city)>100 or len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or not 12<=len(password)<=128:
            return render_template('auth.html',mode='register',error='Enter a valid email, city (up to 100 characters), and a password of 12–128 characters.'),400
        password_hash = generate_password_hash(password)
        with connect(app.config['DATABASE']) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT id FROM hospitals WHERE code=?',(code,)).fetchone():
                return render_template('auth.html',mode='register',error='This hospital code is already registered. Choose another code or sign in.'),409
            hospital_id = db.execute('INSERT INTO hospitals(name,code,city) VALUES (?,?,?)',(name,code,city)).lastrowid
            user_id = db.execute('INSERT INTO users(hospital_id,email,password_hash) VALUES (?,?,?)',(hospital_id,email,password_hash)).lastrowid
            seed_hospital(db,hospital_id)
        start_session(user_id)
        return redirect(url_for('index'))

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.get('/health')
    def health():
        with connect(app.config['DATABASE']) as db:
            db.execute('SELECT 1').fetchone()
        return jsonify(status='ok')

    app.config['DUMMY_PASSWORD_HASH'] = generate_password_hash(secrets.token_hex(32))
