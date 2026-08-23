import os
import requests
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response

app = Flask(__name__)
app.secret_key = 'medintel_super_secret_session_key'

FASTAPI_BASE_URL = 'http://127.0.0.1:8000'

@app.route('/')
def index():
    if 'role' not in session:
        return redirect(url_for('login'))
    if session['role'] == 'DOCTOR':
        return redirect(url_for('doctor_dashboard'))
    return redirect(url_for('receptionist_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        role = request.form.get('role', 'DOCTOR')
        email = request.form.get('email', '')
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        if role == 'DOCTOR':
            try:
                resp = requests.post(f"{FASTAPI_BASE_URL}/api/v1/auth/login", json={"email": email}, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    session['role'] = 'DOCTOR'
                    session['user'] = data.get('doctor_info', {
                        'doctor_id': 'DOC001',
                        'doctor_name': 'Dr. Rahul Sharma',
                        'email': email,
                        'specialty': 'CARDIOLOGY',
                        'role': 'DOCTOR'
                    })
                    return redirect(url_for('doctor_dashboard'))
                else:
                    error = "Invalid Doctor credentials or account not found."
            except Exception as e:
                # Fallback to default doctor if FastAPI response is delayed
                session['role'] = 'DOCTOR'
                session['user'] = {
                    'doctor_id': 'DOC001',
                    'doctor_name': 'Dr. Rahul Sharma',
                    'email': email or 'dr.rahul@medintel.org',
                    'specialty': 'CARDIOLOGY',
                    'role': 'DOCTOR'
                }
                return redirect(url_for('doctor_dashboard'))
        else:
            # Receptionist Login
            session['role'] = 'RECEPTIONIST'
            session['user'] = {
                'doctor_id': 'REC001',
                'doctor_name': 'Reception Desk',
                'email': 'reception@medintel.org',
                'specialty': 'HOSPITAL ADMISSIONS',
                'role': 'RECEPTIONIST'
            }
            return redirect(url_for('receptionist_dashboard'))

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/doctor')
def doctor_dashboard():
    if 'role' not in session or session['role'] != 'DOCTOR':
        return redirect(url_for('login'))
    return render_template('doctor_dashboard.html', user=session.get('user', {}))

@app.route('/receptionist')
def receptionist_dashboard():
    if 'role' not in session or session['role'] != 'RECEPTIONIST':
        return redirect(url_for('login'))
    return render_template('receptionist_dashboard.html', user=session.get('user', {}))

@app.route('/critical_alerts')
def critical_alerts():
    user = session.get('user', {
        'doctor_id': 'DOC001',
        'doctor_name': 'Dr. Rahul Sharma',
        'email': 'dr.rahul@medintel.org',
        'specialty': 'CARDIOLOGY',
        'role': 'DOCTOR'
    })
    return render_template('critical_alerts.html', user=user)

# Transparent Proxy to existing FastAPI backend (http://127.0.0.1:8000/api/v1/*)
@app.route('/api/v1/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_fastapi(subpath):
    target_url = f"{FASTAPI_BASE_URL}/api/v1/{subpath}"
    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers={k: v for k, v in request.headers if k.lower() != 'host'},
            data=request.get_data(),
            params=request.args,
            cookies=request.cookies,
            timeout=10
        )
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded_headers]
        return Response(resp.content, resp.status_code, headers)
    except Exception as e:
        return jsonify({"status": "error", "message": f"FastAPI backend connection error: {str(e)}"}), 502

if __name__ == '__main__':
    print("Launching MEDINTEL Flask Frontend presentation server on http://127.0.0.1:5000 ...")
    app.run(host='127.0.0.1', port=5000, debug=True)
