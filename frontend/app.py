import os
import sys
import secrets
import urllib.parse
from datetime import timedelta
from pathlib import Path
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response

# Ensure project root is on sys.path for robust module resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

app = Flask(__name__)

is_production = os.getenv('FLASK_ENV', '').lower() == 'production' or os.getenv('SESSION_COOKIE_SECURE', '').lower() == 'true'

flask_secret = os.getenv('FLASK_SECRET_KEY')
if not flask_secret:
    if is_production:
        raise RuntimeError("CRITICAL: FLASK_SECRET_KEY environment variable must be explicitly configured in production.")
    flask_secret = 'medintel_super_secret_session_key_2026'

app.secret_key = flask_secret

# Secure session cookies
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=is_production,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8)
)

FASTAPI_BASE_URL = os.getenv('FASTAPI_BASE_URL', 'http://127.0.0.1:8000')

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://127.0.0.1:5000/auth/google/callback')


@app.route('/')
def index():
    if 'role' not in session or 'user' not in session:
        return redirect(url_for('login'))
    if session['role'] == 'DOCTOR':
        return redirect(url_for('doctor_dashboard'))
    return redirect(url_for('receptionist_dashboard'))


@app.route('/auth/google/login')
def google_login():
    """Initiates Google OAuth 2.0 Authorization Code Flow."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return render_template('login.html', error="Google OAuth 2.0 credentials not configured. Check .env file.")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    session['oauth_nonce'] = nonce

    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'nonce': nonce,
        'prompt': 'select_account',
        'access_type': 'offline'
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return redirect(auth_url)


@app.route('/auth/google/callback')
def google_callback():
    """Handles Google OAuth 2.0 callback, verifies identity, and applies strict MedIntel authorization."""
    error_arg = request.args.get('error')
    if error_arg:
        return render_template('login.html', error=f"Google authentication failed or was cancelled: {error_arg}")

    # 1. CSRF State Validation
    saved_state = session.pop('oauth_state', None)
    query_state = request.args.get('state')
    if not saved_state or saved_state != query_state:
        return render_template('login.html', error="Security verification failed: Invalid OAuth state (CSRF detected). Please try again.")

    code = request.args.get('code')
    if not code:
        return render_template('login.html', error="Google did not return an authorization code.")

    # 2. Token Exchange
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    try:
        token_resp = requests.post(token_url, data=token_data, timeout=10)
        if token_resp.status_code != 200:
            return render_template('login.html', error="Failed to exchange authorization code with Google.")
        tokens = token_resp.json()
    except Exception as e:
        return render_template('login.html', error=f"Google token exchange connection error: {str(e)}")

    id_token_jwt = tokens.get('id_token')
    if not id_token_jwt:
        return render_template('login.html', error="Google authentication did not return an ID token.")

    # 3. ID Token Verification (aud, iss, exp, email_verified)
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        claims = id_token.verify_oauth2_token(
            id_token_jwt,
            google_requests.Request(),
            audience=GOOGLE_CLIENT_ID
        )
    except Exception as e:
        return render_template('login.html', error=f"Google ID token signature verification failed: {str(e)}")

    if claims.get('iss') not in ['accounts.google.com', 'https://accounts.google.com']:
        return render_template('login.html', error="Invalid Google ID token issuer.")

    if not claims.get('email_verified'):
        return render_template('login.html', error="Unverified Google accounts cannot access MedIntel.")

    saved_nonce = session.pop('oauth_nonce', None)
    if saved_nonce and claims.get('nonce') and claims.get('nonce') != saved_nonce:
        return render_template('login.html', error="Security verification failed: OAuth nonce mismatch.")

    google_email = claims.get('email', '').strip().lower()

    # 4. Strict MedIntel User Authorization
    from services.alert_router import authorize_google_user
    user_info = authorize_google_user(google_email)

    if not user_info:
        # Mandatory: Deny access, create NO session, expose NO dashboard or patient data
        session.clear()
        return render_template(
            'login.html',
            error=f"Access denied: Google account '{google_email}' is not authorized for MedIntel. Please sign in with an authorized hospital Google account."
        )

    # 5. Establish authorized MedIntel session
    session.clear()
    session['role'] = user_info['role']
    session['user'] = {
        'doctor_id': user_info['doctor_id'],
        'doctor_name': user_info['doctor_name'],
        'email': user_info['email'],
        'specialty': user_info['specialty'],
        'role': user_info['role'],
        'auth_provider': 'google'
    }

    if user_info['role'] == 'DOCTOR':
        return redirect(url_for('doctor_dashboard'))
    return redirect(url_for('receptionist_dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        role = request.form.get('role', 'DOCTOR')
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username', '').strip()

        login_identifier = email if role == 'DOCTOR' else (username or email or 'REC001')

        password = request.form.get('password') or 'medintel123'
        try:
            resp = requests.post(f"{FASTAPI_BASE_URL}/api/v1/auth/login", json={"email": login_identifier, "password": password}, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                doc_info = data.get('doctor_info', {})
                session.clear()
                session['role'] = doc_info.get('role', role)
                session['user'] = {
                    'doctor_id': doc_info.get('doctor_id', 'DOC001'),
                    'doctor_name': doc_info.get('doctor_name', 'Dr. Viraj Patil'),
                    'email': doc_info.get('email', email),
                    'specialty': doc_info.get('specialty', 'CARDIOLOGY'),
                    'role': doc_info.get('role', role),
                    'auth_provider': 'credential'
                }
                if session['role'] == 'DOCTOR':
                    return redirect(url_for('doctor_dashboard'))
                return redirect(url_for('receptionist_dashboard'))
            else:
                error = "Invalid credentials or account not found in authorized registry."
        except Exception:
            # Fallback to authoritative registry directly if FastAPI is restarting
            from services.alert_router import authorize_google_user
            user_info = authorize_google_user(login_identifier)
            if user_info:
                session.clear()
                session['role'] = user_info['role']
                session['user'] = {
                    'doctor_id': user_info['doctor_id'],
                    'doctor_name': user_info['doctor_name'],
                    'email': user_info['email'],
                    'specialty': user_info['specialty'],
                    'role': user_info['role'],
                    'auth_provider': 'credential'
                }
                if user_info['role'] == 'DOCTOR':
                    return redirect(url_for('doctor_dashboard'))
                return redirect(url_for('receptionist_dashboard'))
            error = "Invalid credentials or account not found."

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/doctor')
def doctor_dashboard():
    if 'role' not in session or session.get('role') != 'DOCTOR' or 'user' not in session:
        return redirect(url_for('login'))
    return render_template('doctor_dashboard.html', user=session.get('user', {}))


@app.route('/receptionist')
def receptionist_dashboard():
    if 'role' not in session or session.get('role') != 'RECEPTIONIST' or 'user' not in session:
        return redirect(url_for('login'))
    return render_template('receptionist_dashboard.html', user=session.get('user', {}))


@app.route('/critical_alerts')
def critical_alerts():
    if 'role' not in session or 'user' not in session:
        return redirect(url_for('login'))
    return render_template('critical_alerts.html', user=session.get('user', {}))


# Public endpoints that bypass proxy session checks
PUBLIC_PROXY_ENDPOINTS = {'health', 'pipeline_status', 'auth/login', 'auth/google_authorize', 'hospital/summary', 'monitoring/summary'}


# Anti-Tampering Transparent Proxy to FastAPI backend (http://127.0.0.1:8000/api/v1/*)
@app.route('/api/v1/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_fastapi(subpath):
    clean_subpath = subpath.strip('/')
    is_public = any(clean_subpath == p or clean_subpath.startswith(p + '/') for p in PUBLIC_PROXY_ENDPOINTS)

    # 1. Reject unauthenticated requests to protected endpoints
    if not is_public and 'user' not in session:
        return jsonify({"status": "error", "message": "Authentication required. Please log in to MedIntel."}), 401

    target_url = f"{FASTAPI_BASE_URL}/api/v1/{subpath}"
    try:
        params = dict(request.args)

        # 2. Strict Anti-Tampering: Enforce server-side session identity
        if clean_subpath in ['hospital/summary', 'monitoring/summary']:
            # Hospital-wide summary statistics are never constrained by doctor specialty
            params.pop('doctor_id', None)
            params.pop('specialty', None)
        elif 'user' in session:
            user = session['user']
            if user.get('role') == 'DOCTOR':
                # Force doctor identity from session, overriding any client query param tampering
                params['doctor_id'] = user['doctor_id']
                params['specialty'] = user['specialty']
                if 'alerts/voice' in clean_subpath:
                    params['destination'] = user['specialty']
            elif user.get('role') == 'RECEPTIONIST':
                params['doctor_id'] = user.get('doctor_id', 'REC001')
                # Receptionist is hospital-wide; do not constrain to single specialty
                params.pop('specialty', None)
                if 'alerts/voice' in clean_subpath:
                    params['destination'] = 'RECEPTIONIST'

        resp = requests.request(
            method=request.method,
            url=target_url,
            headers={k: v for k, v in request.headers if k.lower() != 'host'},
            data=request.get_data(),
            params=params,
            cookies=request.cookies,
            timeout=10
        )
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded_headers]
        return Response(resp.content, resp.status_code, headers)
    except Exception as e:
        return jsonify({"status": "error", "message": f"FastAPI backend connection error: {str(e)}"}), 502


# Fallback direct serving for static audio alerts
@app.route('/static/audio/alerts/<path:filename>')
def serve_audio_alerts(filename):
    from flask import send_from_directory
    audio_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'audio', 'alerts')
    return send_from_directory(audio_dir, filename, mimetype='audio/wav')


if __name__ == '__main__':
    host = os.getenv("FLASK_HOST", "0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", 5000)))
    print(f"Launching MEDINTEL Flask Frontend presentation server on http://{host}:{port} ...")
    app.run(host=host, port=port, debug=not is_production)
