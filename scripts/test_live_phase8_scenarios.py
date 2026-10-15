"""
Live Phase 8 Verification Script
Exercises Sections 4 through 11 against the live MedIntel application:
- Viraj (DOC001 / Cardiology)
- Smarath (DOC002 / Pulmonology)
- Shreya (DOC003 / General Medicine)
- Receptionist (REC001 / Hospital-wide)
- Unauthorized account rejection (someoneelse@gmail.com)
- Logout invalidation
- Cross-doctor 403 authorization
- Anti-tampering parameter enforcement
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
from frontend.app import app as flask_app
from services.alert_router import authorize_google_user

def run_live_tests():
    print("=" * 65)
    print("MEDINTEL PHASE 8 LIVE AUTHENTICATION VERIFICATION")
    print("=" * 65)

    results = []

    # 1. Authoritative User Registry Verification
    test_cases = [
        ("Viraj", "pviraj1025@gmail.com", "DOC001", "Dr. Viraj Patil", "DOCTOR", "CARDIOLOGY"),
        ("Smarath", "pawarsamarth4912@gmail.com", "DOC002", "Dr. Smarath Pawar", "DOCTOR", "PULMONOLOGY"),
        ("Shreya", "shreyasutar15@gmail.com", "DOC003", "Dr. Shreya Sutar", "DOCTOR", "GENERAL MEDICINE"),
        ("Receptionist", "1230821edits@gmail.com", "REC001", "Reception Desk", "RECEPTIONIST", "HOSPITAL ADMISSIONS"),
    ]

    for label, email, expected_id, expected_name, expected_role, expected_spec in test_cases:
        user = authorize_google_user(email)
        passed = (
            user is not None
            and user.get("doctor_id") == expected_id
            and user.get("doctor_name") == expected_name
            and user.get("role") == expected_role
            and user.get("specialty") == expected_spec
        )
        status = "PASS" if passed else "FAIL"
        actual = f"{user.get('doctor_id')}/{user.get('role')}/{user.get('specialty')}" if user else "None"
        expected = f"{expected_id}/{expected_role}/{expected_spec}"
        results.append((f"{label} Registry Mapping", expected, actual, status))
        print(f"[{status}] {label} Registry Mapping: {actual}")

    # 2. Live Callback & Session Creation Test via Flask Test Client (Simulating Google OAuth Token Exchange)
    client = flask_app.test_client()

    for label, email, expected_dest in [
        ("Viraj OAuth Flow", "pviraj1025@gmail.com", "/doctor"),
        ("Smarath OAuth Flow", "pawarsamarth4912@gmail.com", "/doctor"),
        ("Shreya OAuth Flow", "shreyasutar15@gmail.com", "/doctor"),
        ("Receptionist OAuth Flow", "1230821edits@gmail.com", "/receptionist"),
    ]:
        with patch('requests.post') as mock_token_post, patch('google.oauth2.id_token.verify_oauth2_token') as mock_verify:
            mock_token_resp = MagicMock()
            mock_token_resp.status_code = 200
            mock_token_resp.json.return_value = {"id_token": "mock_jwt"}
            mock_token_post.return_value = mock_token_resp

            mock_verify.return_value = {
                "iss": "https://accounts.google.com",
                "email": email,
                "email_verified": True,
                "nonce": "test_nonce"
            }

            with client.session_transaction() as sess:
                sess['oauth_state'] = 'test_state'
                sess['oauth_nonce'] = 'test_nonce'

            resp = client.get('/auth/google/callback?state=test_state&code=test_code')
            passed = resp.status_code == 302 and expected_dest in resp.headers.get('Location', '')
            status = "PASS" if passed else "FAIL"
            results.append((label, f"Redirect to {expected_dest}", f"{resp.status_code} -> {resp.headers.get('Location')}", status))
            print(f"[{status}] {label}: Redirected to {resp.headers.get('Location')}")

    # 3. Unauthorized User Test
    with patch('requests.post') as mock_token_post, patch('google.oauth2.id_token.verify_oauth2_token') as mock_verify:
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"id_token": "mock_jwt"}
        mock_token_post.return_value = mock_token_resp

        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "email": "someoneelse@gmail.com",
            "email_verified": True,
            "nonce": "test_nonce"
        }

        with client.session_transaction() as sess:
            sess['oauth_state'] = 'test_state'
            sess['oauth_nonce'] = 'test_nonce'

        resp = client.get('/auth/google/callback?state=test_state&code=test_code')
        with client.session_transaction() as sess:
            has_no_session = 'user' not in sess and 'role' not in sess

        passed = resp.status_code == 200 and b"Access denied" in resp.data and has_no_session
        status = "PASS" if passed else "FAIL"
        results.append(("Unauthorized Account", "Access denied / No session", "Denied banner shown & Session empty", status))
        print(f"[{status}] Unauthorized Account: Access denied, no session created")

    # 4. Logout Test
    with client.session_transaction() as sess:
        sess['role'] = 'DOCTOR'
        sess['user'] = {'doctor_id': 'DOC001', 'doctor_name': 'Dr. Viraj Patil', 'specialty': 'CARDIOLOGY', 'role': 'DOCTOR'}

    resp_logout = client.get('/logout')
    resp_after = client.get('/doctor')
    resp_api = client.get('/api/v1/patients/101')

    passed_logout = (
        resp_logout.status_code == 302
        and resp_after.status_code == 302
        and '/login' in resp_after.headers.get('Location', '')
        and resp_api.status_code == 401
    )
    status = "PASS" if passed_logout else "FAIL"
    results.append(("Logout Invalidation", "Session cleared & 401 on API", f"Redirect to login & API 401", status))
    print(f"[{status}] Logout Test: Session cleared, protected routes blocked with 401")

    # 5. Cross-Doctor Access via Live FastAPI (8000)
    try:
        # Viraj (DOC001 / Cardiology) accessing Pulmonology patient 104
        r_cross1 = requests.get('http://127.0.0.1:8000/api/v1/patients/104?doctor_id=DOC001', timeout=5)
        # Smarath (DOC002 / Pulmonology) accessing Cardiology patient 101
        r_cross2 = requests.get('http://127.0.0.1:8000/api/v1/patients/101?doctor_id=DOC002', timeout=5)
        # Viraj accessing his own patient 101
        r_own = requests.get('http://127.0.0.1:8000/api/v1/patients/101?doctor_id=DOC001', timeout=5)
        # Receptionist accessing patient 104
        r_rec = requests.get('http://127.0.0.1:8000/api/v1/patients/104?doctor_id=REC001', timeout=5)

        passed_cross = (
            r_cross1.status_code == 403
            and r_cross2.status_code == 403
            and r_own.status_code == 200
            and r_rec.status_code == 200
        )
        status = "PASS" if passed_cross else "FAIL"
        actual = f"Cross1: {r_cross1.status_code}, Cross2: {r_cross2.status_code}, Own: {r_own.status_code}, Rec: {r_rec.status_code}"
        results.append(("Cross-Doctor Authorization", "403 on cross-specialty, 200 on own/reception", actual, status))
        print(f"[{status}] Cross-Doctor Authorization: {actual}")
    except Exception as e:
        results.append(("Cross-Doctor Authorization", "403 Forbidden", str(e), "FAIL"))
        print(f"[FAIL] Cross-Doctor Authorization: {e}")

    # 6. Anti-Tampering Parameter Test
    with client.session_transaction() as sess:
        sess['role'] = 'DOCTOR'
        sess['user'] = {'doctor_id': 'DOC001', 'doctor_name': 'Dr. Viraj Patil', 'specialty': 'CARDIOLOGY', 'role': 'DOCTOR'}

    with patch('requests.request') as mock_proxy:
        mock_r = MagicMock()
        mock_r.status_code = 200
        mock_r.content = b'{"status": "SUCCESS"}'
        mock_r.raw.headers.items.return_value = []
        mock_proxy.return_value = mock_r

        # Client attempts tampering: supplying DOC002 / PULMONOLOGY
        client.get('/api/v1/patients?doctor_id=DOC002&specialty=PULMONOLOGY')
        sent_params = mock_proxy.call_args[1].get('params', {})

        passed_tamper = (sent_params.get('doctor_id') == 'DOC001' and sent_params.get('specialty') == 'CARDIOLOGY')
        status = "PASS" if passed_tamper else "FAIL"
        actual = f"doctor_id={sent_params.get('doctor_id')}, specialty={sent_params.get('specialty')}"
        results.append(("Parameter Tampering", "Forced DOC001/CARDIOLOGY", actual, status))
        print(f"[{status}] Parameter Tampering Defense: Client tampering overridden -> {actual}")

    print("\n" + "=" * 65)
    print("LIVE VERIFICATION SUMMARY TABLE")
    print("=" * 65)
    print(f"{'Test':<30} | {'Expected':<30} | {'Actual':<30} | {'Result'}")
    print("-" * 105)
    for test, exp, act, res in results:
        print(f"{test:<30} | {exp[:30]:<30} | {act[:30]:<30} | {res}")

    return all(r[3] == "PASS" for r in results)

if __name__ == "__main__":
    success = run_live_tests()
    sys.exit(0 if success else 1)
