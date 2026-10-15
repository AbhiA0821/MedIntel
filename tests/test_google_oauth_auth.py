"""
MedIntel Phase 8 Test Suite: Google OAuth 2.0 + Strict MedIntel Authorization
Tests:
1. Authorized Viraj Google account (pviraj1025@gmail.com -> DOC001 / CARDIOLOGY / DOCTOR)
2. Authorized Smarath Google account (pawarsamarth4912@gmail.com -> DOC002 / PULMONOLOGY / DOCTOR)
3. Authorized Shreya Google account (shreyasutar15@gmail.com -> DOC003 / GENERAL MEDICINE / DOCTOR)
4. Authorized Receptionist Google account (1230821edits@gmail.com -> REC001 / HOSPITAL ADMISSIONS / RECEPTIONIST)
5. Unauthorized Google account (someoneelse@gmail.com -> Auth succeeds, Authorization fails, NO session)
6. Invalid/missing Google identity & unverified email rejection
7. Invalid OAuth state / CSRF rejection
8. Logout invalidates session completely
9. Cross-doctor patient access rejection (403 Forbidden)
10. Anti-tampering: Query parameter overrides ignored in favor of server-side session
11. Protected API without session returns 401 Unauthorized
12. Backend /api/v1/auth/google_authorize enforcement
"""

import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.app import app as flask_app
from backend.main import app as fastapi_app
from services.alert_router import authorize_google_user, AUTHORITATIVE_USERS_BY_EMAIL
from fastapi.testclient import TestClient


class TestGoogleOAuthAndAuthorization(unittest.TestCase):

    def setUp(self):
        flask_app.config['TESTING'] = True
        flask_app.config['SECRET_KEY'] = 'test_secret_medintel'
        self.flask_client = flask_app.test_client()
        self.fastapi_client = TestClient(fastapi_app)

    # -------------------------------------------------------------
    # 1. Authoritative User Registry Unit Checks
    # -------------------------------------------------------------
    def test_01_viraj_google_mapping(self):
        user = authorize_google_user("pviraj1025@gmail.com")
        self.assertIsNotNone(user)
        self.assertEqual(user["doctor_id"], "DOC001")
        self.assertEqual(user["doctor_name"], "Dr. Viraj Patil")
        self.assertEqual(user["specialty"], "CARDIOLOGY")
        self.assertEqual(user["role"], "DOCTOR")

    def test_02_smarath_google_mapping(self):
        user = authorize_google_user("pawarsamarth4912@gmail.com")
        self.assertIsNotNone(user)
        self.assertEqual(user["doctor_id"], "DOC002")
        self.assertEqual(user["doctor_name"], "Dr. Smarath Pawar")
        self.assertEqual(user["specialty"], "PULMONOLOGY")
        self.assertEqual(user["role"], "DOCTOR")

    def test_03_shreya_google_mapping(self):
        user = authorize_google_user("shreyasutar15@gmail.com")
        self.assertIsNotNone(user)
        self.assertEqual(user["doctor_id"], "DOC003")
        self.assertEqual(user["doctor_name"], "Dr. Shreya Sutar")
        self.assertEqual(user["specialty"], "GENERAL MEDICINE")
        self.assertEqual(user["role"], "DOCTOR")

    def test_04_receptionist_google_mapping(self):
        user = authorize_google_user("1230821edits@gmail.com")
        self.assertIsNotNone(user)
        self.assertEqual(user["doctor_id"], "REC001")
        self.assertEqual(user["doctor_name"], "Reception Desk")
        self.assertEqual(user["role"], "RECEPTIONIST")

    def test_05_unauthorized_google_account_registry_check(self):
        # Someone with valid Google account but not in MedIntel registry
        user = authorize_google_user("someoneelse@gmail.com")
        self.assertIsNone(user, "Unauthorized email must return None")

        # Case and whitespace normalization
        user_upper = authorize_google_user("  PVIRAJ1025@GMAIL.COM  ")
        self.assertIsNotNone(user_upper)
        self.assertEqual(user_upper["doctor_id"], "DOC001")

    # -------------------------------------------------------------
    # 2. OAuth Flow: Login & CSRF State Handling
    # -------------------------------------------------------------
    def test_06_oauth_login_initiates_redirect_and_state(self):
        resp = self.flask_client.get('/auth/google/login')
        self.assertEqual(resp.status_code, 302)
        redirect_url = resp.headers['Location']
        self.assertIn("accounts.google.com", redirect_url)
        self.assertIn("client_id=", redirect_url)
        self.assertIn("response_type=code", redirect_url)
        self.assertIn("scope=openid+email+profile", redirect_url)

        with self.flask_client.session_transaction() as sess:
            self.assertIn('oauth_state', sess)
            self.assertIn('oauth_nonce', sess)

    def test_07_oauth_callback_rejects_state_mismatch(self):
        with self.flask_client.session_transaction() as sess:
            sess['oauth_state'] = 'legitimate_csrf_token_123'

        # Send callback with forged or missing state
        resp = self.flask_client.get('/auth/google/callback?state=forged_state&code=test_code')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Invalid OAuth state", resp.data)

        # Confirm no session was created
        with self.flask_client.session_transaction() as sess:
            self.assertNotIn('user', sess)
            self.assertNotIn('role', sess)

    # -------------------------------------------------------------
    # 3. OAuth Callback: Authorized vs Unauthorized Google Accounts
    # -------------------------------------------------------------
    @patch('requests.post')
    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_08_authorized_doctor_oauth_login(self, mock_verify, mock_token_post):
        # Mock Google token exchange response
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "id_token": "mock_jwt_token",
            "access_token": "mock_access_token"
        }
        mock_token_post.return_value = mock_token_resp

        # Mock ID token claims
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "email": "pviraj1025@gmail.com",
            "email_verified": True,
            "nonce": "test_nonce_abc"
        }

        with self.flask_client.session_transaction() as sess:
            sess['oauth_state'] = 'test_state_123'
            sess['oauth_nonce'] = 'test_nonce_abc'

        resp = self.flask_client.get('/auth/google/callback?state=test_state_123&code=valid_code')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/doctor', resp.headers['Location'])

        # Verify session is established with correct role & specialty
        with self.flask_client.session_transaction() as sess:
            self.assertEqual(sess.get('role'), 'DOCTOR')
            self.assertEqual(sess.get('user', {}).get('doctor_id'), 'DOC001')
            self.assertEqual(sess.get('user', {}).get('specialty'), 'CARDIOLOGY')

    @patch('requests.post')
    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_09_authorized_receptionist_oauth_login(self, mock_verify, mock_token_post):
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"id_token": "mock_jwt_token"}
        mock_token_post.return_value = mock_token_resp

        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "email": "1230821edits@gmail.com",
            "email_verified": True,
            "nonce": "test_nonce_rec"
        }

        with self.flask_client.session_transaction() as sess:
            sess['oauth_state'] = 'test_state_rec'
            sess['oauth_nonce'] = 'test_nonce_rec'

        resp = self.flask_client.get('/auth/google/callback?state=test_state_rec&code=valid_code')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/receptionist', resp.headers['Location'])

        with self.flask_client.session_transaction() as sess:
            self.assertEqual(sess.get('role'), 'RECEPTIONIST')
            self.assertEqual(sess.get('user', {}).get('doctor_id'), 'REC001')

    @patch('requests.post')
    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_10_unauthorized_google_account_rejected(self, mock_verify, mock_token_post):
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"id_token": "mock_jwt_token"}
        mock_token_post.return_value = mock_token_resp

        # Valid Google user, but NOT authorized in MedIntel
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "email": "someoneelse@gmail.com",
            "email_verified": True,
            "nonce": "test_nonce_unauth"
        }

        with self.flask_client.session_transaction() as sess:
            sess['oauth_state'] = 'test_state_unauth'
            sess['oauth_nonce'] = 'test_nonce_unauth'

        resp = self.flask_client.get('/auth/google/callback?state=test_state_unauth&code=valid_code')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Access denied", resp.data)
        self.assertIn(b"someoneelse@gmail.com", resp.data)

        # STRICT ASSERTION: No session created, no doctor/receptionist role, no patient data exposed
        with self.flask_client.session_transaction() as sess:
            self.assertNotIn('user', sess)
            self.assertNotIn('role', sess)

    @patch('requests.post')
    @patch('google.oauth2.id_token.verify_oauth2_token')
    def test_11_unverified_google_email_rejected(self, mock_verify, mock_token_post):
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"id_token": "mock_jwt_token"}
        mock_token_post.return_value = mock_token_resp

        # email_verified is False
        mock_verify.return_value = {
            "iss": "https://accounts.google.com",
            "email": "pviraj1025@gmail.com",
            "email_verified": False,
            "nonce": "test_nonce_unver"
        }

        with self.flask_client.session_transaction() as sess:
            sess['oauth_state'] = 'test_state_unver'
            sess['oauth_nonce'] = 'test_nonce_unver'

        resp = self.flask_client.get('/auth/google/callback?state=test_state_unver&code=valid_code')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Unverified Google accounts cannot access MedIntel", resp.data)

        with self.flask_client.session_transaction() as sess:
            self.assertNotIn('user', sess)

    # -------------------------------------------------------------
    # 4. Session Protection & Logout Invalidation
    # -------------------------------------------------------------
    def test_12_logout_invalidates_session(self):
        # Set authenticated doctor session
        with self.flask_client.session_transaction() as sess:
            sess['role'] = 'DOCTOR'
            sess['user'] = {
                'doctor_id': 'DOC001',
                'doctor_name': 'Dr. Viraj Patil',
                'specialty': 'CARDIOLOGY',
                'role': 'DOCTOR'
            }

        # Verify access allowed
        resp = self.flask_client.get('/doctor')
        self.assertEqual(resp.status_code, 200)

        # Logout
        resp_logout = self.flask_client.get('/logout')
        self.assertEqual(resp_logout.status_code, 302)

        # Verify session cleared and subsequent access redirects to login
        with self.flask_client.session_transaction() as sess:
            self.assertNotIn('user', sess)
            self.assertNotIn('role', sess)

        resp_after = self.flask_client.get('/doctor')
        self.assertEqual(resp_after.status_code, 302)
        self.assertIn('/login', resp_after.headers['Location'])

    # -------------------------------------------------------------
    # 5. Protected Endpoints & Anti-Tampering Checks
    # -------------------------------------------------------------
    def test_13_unauthenticated_proxy_request_rejected(self):
        # Requesting protected endpoint without session must return 401
        resp = self.flask_client.get('/api/v1/patients/101')
        self.assertEqual(resp.status_code, 401)
        self.assertIn(b"Authentication required", resp.data)

    def test_14_anti_tampering_overrides_client_parameters(self):
        # User is logged in as Dr. Viraj (DOC001, CARDIOLOGY)
        with self.flask_client.session_transaction() as sess:
            sess['role'] = 'DOCTOR'
            sess['user'] = {
                'doctor_id': 'DOC001',
                'doctor_name': 'Dr. Viraj Patil',
                'specialty': 'CARDIOLOGY',
                'role': 'DOCTOR'
            }

        with patch('requests.request') as mock_proxy_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b'{"status": "SUCCESS"}'
            mock_resp.raw.headers.items.return_value = []
            mock_proxy_req.return_value = mock_resp

            # Malicious client tries to tamper query params to impersonate Dr. Smarath (DOC002, PULMONOLOGY)
            self.flask_client.get('/api/v1/patients?doctor_id=DOC002&specialty=PULMONOLOGY')

            # Verify that proxy FORCED the server session identity (DOC001, CARDIOLOGY)
            call_args = mock_proxy_req.call_args
            params_sent = call_args[1].get('params', {})
            self.assertEqual(params_sent.get('doctor_id'), 'DOC001', "Proxy must override tampered doctor_id")
            self.assertEqual(params_sent.get('specialty'), 'CARDIOLOGY', "Proxy must override tampered specialty")

    def test_17_proxy_excludes_accept_encoding_and_content_length(self):
        # User is logged in as Dr. Smarath (DOC002, PULMONOLOGY)
        with self.flask_client.session_transaction() as sess:
            sess['role'] = 'DOCTOR'
            sess['user'] = {
                'doctor_id': 'DOC002',
                'doctor_name': 'Dr. Smarath Pawar',
                'specialty': 'PULMONOLOGY',
                'role': 'DOCTOR'
            }

        with patch('requests.request') as mock_proxy_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b'{"status": "SUCCESS", "patients": []}'
            mock_resp.raw.headers.items.return_value = [('Content-Type', 'application/json')]
            mock_proxy_req.return_value = mock_resp

            # Client browser sends Accept-Encoding and Content-Length
            headers = {
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Content-Length': '0',
                'User-Agent': 'TestBrowser/1.0'
            }
            resp = self.flask_client.get('/api/v1/live_vitals', headers=headers)

            self.assertEqual(resp.status_code, 200)
            call_args = mock_proxy_req.call_args
            upstream_headers = call_args[1].get('headers', {})
            upstream_lower = {k.lower(): v for k, v in upstream_headers.items()}

            self.assertNotIn('accept-encoding', upstream_lower, "Proxy must exclude accept-encoding so requests auto-decompresses")
            self.assertNotIn('content-length', upstream_lower, "Proxy must exclude content-length")
            self.assertNotIn('host', upstream_lower, "Proxy must exclude host")
            self.assertIn('user-agent', upstream_lower, "Proxy should preserve standard client headers")

    # -------------------------------------------------------------
    # 6. Backend Direct Authorization Endpoint
    # -------------------------------------------------------------
    def test_15_backend_google_authorize_endpoint(self):
        # Authorized doctor
        r1 = self.fastapi_client.post("/api/v1/auth/google_authorize", json={"email": "pviraj1025@gmail.com", "email_verified": True})
        self.assertEqual(r1.status_code, 200)
        data1 = r1.json()
        self.assertTrue(data1["authorized"])
        self.assertEqual(data1["user"]["doctor_id"], "DOC001")
        self.assertEqual(data1["user"]["specialty"], "CARDIOLOGY")

        # Authorized receptionist
        r2 = self.fastapi_client.post("/api/v1/auth/google_authorize", json={"email": "1230821edits@gmail.com", "email_verified": True})
        self.assertEqual(r2.status_code, 200)
        data2 = r2.json()
        self.assertTrue(data2["authorized"])
        self.assertEqual(data2["user"]["doctor_id"], "REC001")
        self.assertEqual(data2["user"]["role"], "RECEPTIONIST")

        # Unauthorized Google user returns 403 Forbidden
        r3 = self.fastapi_client.post("/api/v1/auth/google_authorize", json={"email": "someoneelse@gmail.com", "email_verified": True})
        self.assertEqual(r3.status_code, 403)
        self.assertIn("Access denied", r3.json()["detail"])

        # Unverified email returns 403 Forbidden
        r4 = self.fastapi_client.post("/api/v1/auth/google_authorize", json={"email": "pviraj1025@gmail.com", "email_verified": False})
        self.assertEqual(r4.status_code, 403)

    # -------------------------------------------------------------
    # 7. Cross-Doctor Patient Isolation via Backend
    # -------------------------------------------------------------
    def test_16_cross_doctor_access_forbidden(self):
        # Dr. Viraj (Cardiology) requesting Dr. Smarath's patient (P104 - Pulmonology) returns 403
        r_forbidden = self.fastapi_client.get("/api/v1/patients/104?doctor_id=DOC001")
        self.assertEqual(r_forbidden.status_code, 403)

        # Dr. Viraj requesting his own patient (P101 - Cardiology) returns 200
        r_allowed = self.fastapi_client.get("/api/v1/patients/101?doctor_id=DOC001")
        self.assertEqual(r_allowed.status_code, 200)

        # Receptionist has hospital-wide access
        r_rec = self.fastapi_client.get("/api/v1/patients/104?doctor_id=REC001")
        self.assertEqual(r_rec.status_code, 200)


if __name__ == "__main__":
    unittest.main()
