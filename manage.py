"""Operator-only account provisioning; passwords are entered with a hidden prompt."""
import argparse
import getpass
import os
import re
from pathlib import Path
from werkzeug.security import generate_password_hash
from database import initialize, connect


def main():
    parser = argparse.ArgumentParser(description='Create an administrator for an existing hospital.')
    parser.add_argument('command', choices=['create-admin'])
    parser.add_argument('--hospital', default='smart-hospital', help='Existing hospital code')
    parser.add_argument('--email', required=True)
    args = parser.parse_args()
    email = args.email.strip().lower()
    if len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
        parser.error('Enter a valid email.')
    path = os.environ.get('DATABASE_PATH') or str(Path(__file__).parent/'instance'/'hospital.db')
    initialize(path)
    password = getpass.getpass('Choose a password (12–128 characters): ')
    if not 12<=len(password)<=128 or password != getpass.getpass('Confirm password: '):
        parser.error('Passwords must match and have 12–128 characters.')
    with connect(path) as db:
        hospital = db.execute('SELECT id FROM hospitals WHERE code=?',(args.hospital,)).fetchone()
        if not hospital:
            parser.error('Hospital does not exist. Use the registration page for a new hospital.')
        if db.execute('SELECT id FROM users WHERE hospital_id=? AND email=?',(hospital['id'],email)).fetchone():
            parser.error('This administrator already exists.')
        db.execute('INSERT INTO users(hospital_id,email,password_hash) VALUES (?,?,?)',(hospital['id'],email,generate_password_hash(password)))
    print('Administrator created. Sign in using hospital code:',args.hospital)


if __name__ == '__main__':
    main()
