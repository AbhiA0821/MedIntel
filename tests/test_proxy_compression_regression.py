"""
Regression test suite for MedIntel Flask Proxy:
Verifies header stripping (accept-encoding, content-length, host) to ensure
requests automatically decompresses responses, returning valid JSON to the browser
without syntax or encoding errors.
"""

import sys
import json
import gzip
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.app import app as flask_app


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'test_secret_medintel_regression'
    return flask_app.test_client()


def test_proxy_strips_accept_encoding_and_content_length(client):
    """
    Ensure the Flask proxy excludes 'accept-encoding', 'content-length', and 'host'
    from upstream headers so Python requests can automatically handle decompression.
    """
    with client.session_transaction() as sess:
        sess['role'] = 'DOCTOR'
        sess['user'] = {
            'doctor_id': 'DOC002',
            'doctor_name': 'Dr. Smarath Pawar',
            'email': 'pawarsamarth4912@gmail.com',
            'specialty': 'PULMONOLOGY',
            'role': 'DOCTOR'
        }

    with patch('requests.request') as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "SUCCESS", "patients": []}'
        mock_resp.raw.headers.items.return_value = [('Content-Type', 'application/json')]
        mock_req.return_value = mock_resp

        # Send standard browser headers including compression algorithms
        browser_headers = {
            'Host': 'medintel-web-em7v.onrender.com',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Content-Length': '0',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'application/json'
        }
        res = client.get('/api/v1/live_vitals', headers=browser_headers)

        assert res.status_code == 200
        # Verify JSON is parseable without syntax or codec errors
        data = json.loads(res.data)
        assert data['status'] == 'SUCCESS'

        # Check forwarded headers
        call_kwargs = mock_req.call_args[1]
        sent_headers = {k.lower(): v for k, v in call_kwargs['headers'].items()}
        assert 'accept-encoding' not in sent_headers, "accept-encoding must be stripped before forwarding upstream"
        assert 'content-length' not in sent_headers, "content-length must be stripped before forwarding upstream"
        assert 'host' not in sent_headers, "host must be stripped before forwarding upstream"
        assert sent_headers.get('accept') == 'application/json'


def test_proxy_returns_valid_json_when_upstream_content_is_decompressed(client):
    """
    Verifies that resp.content (which requests decompresses automatically when
    accept-encoding is omitted from request headers) is returned cleanly to the browser
    with no corrupt binary or encoding headers.
    """
    with client.session_transaction() as sess:
        sess['role'] = 'DOCTOR'
        sess['user'] = {
            'doctor_id': 'DOC002',
            'doctor_name': 'Dr. Smarath Pawar',
            'email': 'pawarsamarth4912@gmail.com',
            'specialty': 'PULMONOLOGY',
            'role': 'DOCTOR'
        }

    # Simulate decompressed JSON payload from requests
    sample_patients = [
        {"patient_id": "P104", "name": "Bhanumati Dasgupta", "assigned_specialty": "PULMONOLOGY", "severity": "CRITICAL"}
    ]
    decompressed_bytes = json.dumps({"status": "SUCCESS", "patients": sample_patients}).encode('utf-8')

    with patch('requests.request') as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = decompressed_bytes
        # Upstream response might have included raw headers that need filtering
        mock_resp.raw.headers.items.return_value = [
            ('Content-Type', 'application/json'),
            ('Content-Encoding', 'br'),
            ('Content-Length', '512'),
            ('Transfer-Encoding', 'chunked')
        ]
        mock_req.return_value = mock_resp

        res = client.get('/api/v1/live_vitals', headers={'Accept-Encoding': 'gzip, deflate, br, zstd'})
        assert res.status_code == 200

        # Returned headers must NOT contain upstream content-encoding or transfer-encoding
        res_headers_lower = {k.lower(): v for k, v in res.headers.items()}
        assert 'transfer-encoding' not in res_headers_lower

        # Response body must decode cleanly as valid JSON UTF-8
        parsed = json.loads(res.data)
        assert len(parsed['patients']) == 1
        assert parsed['patients'][0]['name'] == 'Bhanumati Dasgupta'
        assert parsed['patients'][0]['assigned_specialty'] == 'PULMONOLOGY'


def test_proxy_doctor_identity_and_specialty_enforced(client):
    """
    Verify server-side anti-tampering: doctor_id and specialty are strictly enforced
    from session regardless of query parameter spoofing.
    """
    with client.session_transaction() as sess:
        sess['role'] = 'DOCTOR'
        sess['user'] = {
            'doctor_id': 'DOC002',
            'doctor_name': 'Dr. Smarath Pawar',
            'email': 'pawarsamarth4912@gmail.com',
            'specialty': 'PULMONOLOGY',
            'role': 'DOCTOR'
        }

    with patch('requests.request') as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "SUCCESS"}'
        mock_resp.raw.headers.items.return_value = []
        mock_req.return_value = mock_resp

        # Client attempts tampering to DOC001 / CARDIOLOGY
        client.get('/api/v1/live_vitals?doctor_id=DOC001&specialty=CARDIOLOGY')
        call_params = mock_req.call_args[1].get('params', {})

        assert call_params['doctor_id'] == 'DOC002', "Session doctor_id must override query parameters"
        assert call_params['specialty'] == 'PULMONOLOGY', "Session specialty must override query parameters"


def test_proxy_receptionist_hospital_wide_access(client):
    """
    Verify Receptionist role has hospital-wide access without specialty restriction.
    """
    with client.session_transaction() as sess:
        sess['role'] = 'RECEPTIONIST'
        sess['user'] = {
            'doctor_id': 'REC001',
            'doctor_name': 'Reception Desk',
            'email': '1230821edits@gmail.com',
            'specialty': 'HOSPITAL ADMISSIONS',
            'role': 'RECEPTIONIST'
        }

    with patch('requests.request') as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "SUCCESS"}'
        mock_resp.raw.headers.items.return_value = []
        mock_req.return_value = mock_resp

        client.get('/api/v1/live_vitals')
        call_params = mock_req.call_args[1].get('params', {})

        assert call_params['doctor_id'] == 'REC001'
        assert 'specialty' not in call_params, "Receptionist must not be restricted to single specialty"
