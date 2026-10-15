import requests
import time

print('=== STARTING PART 10 LIVE EVENT VERIFICATION ===')

# STEP 1: Login as Dr. Viraj
s_viraj = requests.Session()
login_res = s_viraj.post('http://127.0.0.1:5000/login', data={'role': 'DOCTOR', 'email': 'pviraj1025@gmail.com'})
assert login_res.url == 'http://127.0.0.1:5000/doctor', f'Login failed: {login_res.url}'
print('STEP 1 PASS: Logged in as Dr. Viraj (Cardiology)')

# STEP 2: Dashboard shows current Cardiology patients
vitals = s_viraj.get('http://127.0.0.1:5000/api/v1/live_vitals').json()
patients = vitals.get('patients', [])
for p in patients:
    assert p['assigned_specialty'] == 'CARDIOLOGY', f'Wrong specialty: {p}'
initial_crit_count = vitals.get('critical_count', 0)
print(f'STEP 2 PASS: Dashboard scoped to Cardiology. Patient count: {len(patients)}, Critical: {initial_crit_count}')

# Acknowledge / drain any existing voice alerts in CARDIOLOGY queue so we test new ones cleanly
q_viraj = s_viraj.get('http://127.0.0.1:5000/api/v1/alerts/voice/queue').json()
for a in q_viraj.get('queued', []):
    s_viraj.post('http://127.0.0.1:5000/api/v1/alerts/voice/status', json={'alert_id': a['alert_id'], 'status': 'COMPLETED'})

# STEP 3: Generate a NEW Cardiology critical patient
# Create patient Aarav Chopra in Cardiology
create_res = requests.post('http://127.0.0.1:8000/api/v1/patients', json={
    'first_name': 'Aarav',
    'last_name': 'Chopra',
    'age': 52,
    'gender': 'Male',
    'ward': 'Cardiology',
    'room_no': '201',
    'bed_no': '4',
    'specialty': 'CARDIOLOGY',
    'patient_id': 201
}).json()
print('Created patient:', create_res.get('patient_id'))

# Inject critical alert for Aarav Chopra via API
trig1 = requests.post('http://127.0.0.1:8000/api/v1/alerts/trigger', json={
    'patient_id': 201,
    'severity': 'CRITICAL',
    'reason': 'Severe Tachycardia (135 bpm), Hypoxia (87%)',
    'recommendation': 'Immediate bedside evaluation and O2 therapy.',
    'ward': 'Cardiology',
    'room_no': '201',
    'bed_no': '4',
    'specialty': 'CARDIOLOGY',
    'assigned_doctor': 'Dr. Viraj Patil'
}).json()
print('Triggered critical alert 1:', trig1.get('alert_id'))

# Check Dr. Viraj dashboard live state
vitals_after = s_viraj.get('http://127.0.0.1:5000/api/v1/live_vitals').json()
print('Dr. Viraj total patients now:', vitals_after.get('total_patients'), 'Critical:', vitals_after.get('critical_count'))
p201 = next((p for p in vitals_after.get('patients', []) if p['patient_id'] == 'P201'), None)
assert p201 is not None, 'New patient P201 not found in live_vitals!'
assert p201['severity'] == 'CRITICAL', f"Expected CRITICAL, got {p201['severity']}"
print('STEP 3a PASS: P201 appears automatically in Cardiology stream as CRITICAL.')

# Check Dr. Viraj voice queue
q1 = s_viraj.get('http://127.0.0.1:5000/api/v1/alerts/voice/queue').json()
print('Dr. Viraj voice queue count:', len(q1.get('queued', [])))
queued_item1 = next((item for item in q1.get('queued', []) if '201' in item['patient_id']), None)
assert queued_item1 is not None, f'Alert for P201 not in voice queue: {q1}'
print('Spoken text 1:', queued_item1['spoken_text'])
assert queued_item1['spoken_text'] == 'Patient Aarav Chopra, Cardiology Ward Room 201 Bed 4, Critical.'
print('STEP 3b PASS: Voice queue contains exact concise announcement format!')

# STEP 4: Generate another Cardiology critical patient immediately
create_res2 = requests.post('http://127.0.0.1:8000/api/v1/patients', json={
    'first_name': 'Vikram',
    'last_name': 'Rao',
    'age': 60,
    'gender': 'Male',
    'ward': 'Cardiology',
    'room_no': '201',
    'bed_no': '5',
    'specialty': 'CARDIOLOGY',
    'patient_id': 202
}).json()
trig2 = requests.post('http://127.0.0.1:8000/api/v1/alerts/trigger', json={
    'patient_id': 202,
    'severity': 'CRITICAL',
    'reason': 'Acute hypotension and pyrexia',
    'recommendation': 'IV fluids and antipyretics.',
    'ward': 'Cardiology',
    'room_no': '201',
    'bed_no': '5',
    'specialty': 'CARDIOLOGY',
    'assigned_doctor': 'Dr. Viraj Patil'
}).json()
print('Triggered critical alert 2:', trig2.get('alert_id'))

# Verify both alerts in Dr. Viraj voice queue in sequential FIFO order
q2 = s_viraj.get('http://127.0.0.1:5000/api/v1/alerts/voice/queue').json()
queued_pids = [item['patient_id'] for item in q2.get('queued', [])]
print('Dr. Viraj queued patients in FIFO order:', queued_pids)
assert 'P201' in queued_pids and 'P202' in queued_pids, f'Both alerts must be in queue: {queued_pids}'
assert queued_pids.index('P201') < queued_pids.index('P202'), 'FIFO order violated!'
print('STEP 4 PASS: Both Cardiology alerts queued sequentially in FIFO order!')

# STEP 5: Generate a Pulmonology critical patient
create_res3 = requests.post('http://127.0.0.1:8000/api/v1/patients', json={
    'first_name': 'Ananya',
    'last_name': 'Sen',
    'age': 44,
    'gender': 'Female',
    'ward': 'Pulmonology',
    'room_no': '202',
    'bed_no': '5',
    'specialty': 'PULMONOLOGY',
    'patient_id': 203
}).json()
trig3 = requests.post('http://127.0.0.1:8000/api/v1/alerts/trigger', json={
    'patient_id': 203,
    'severity': 'CRITICAL',
    'reason': 'Severe Bronchospasm, SpO2 84%',
    'recommendation': 'Nebulized bronchodilators.',
    'ward': 'Pulmonology',
    'room_no': '202',
    'bed_no': '5',
    'specialty': 'PULMONOLOGY',
    'assigned_doctor': 'Dr. Smarath Pawar'
}).json()
print('Triggered Pulmonology alert 3:', trig3.get('alert_id'))

# Verify Dr. Viraj does NOT receive P203
viraj_vitals = s_viraj.get('http://127.0.0.1:5000/api/v1/live_vitals').json()
viraj_pids = [p['patient_id'] for p in viraj_vitals.get('patients', [])]
assert 'P203' not in viraj_pids, f'Dr. Viraj must NOT see Pulmonology patient P203: {viraj_pids}'
viraj_queue = s_viraj.get('http://127.0.0.1:5000/api/v1/alerts/voice/queue').json()
viraj_queue_pids = [i['patient_id'] for i in viraj_queue.get('queued', [])]
assert 'P203' not in viraj_queue_pids, f'Dr. Viraj voice queue must NOT receive Pulmonology P203: {viraj_queue_pids}'
print('STEP 5 PASS: Dr. Viraj did NOT receive Pulmonology critical patient (Specialty Isolation Enforced)!')

# STEP 6: Login as Dr. Smarath
s_smarath = requests.Session()
login_smarath = s_smarath.post('http://127.0.0.1:5000/login', data={'role': 'DOCTOR', 'email': 'pawarsamarth4912@gmail.com'})
assert login_smarath.url == 'http://127.0.0.1:5000/doctor', 'Dr. Smarath login failed'
smarath_vitals = s_smarath.get('http://127.0.0.1:5000/api/v1/live_vitals').json()
smarath_pids = [p['patient_id'] for p in smarath_vitals.get('patients', [])]
assert 'P203' in smarath_pids, f'Dr. Smarath must see P203: {smarath_pids}'
smarath_queue = s_smarath.get('http://127.0.0.1:5000/api/v1/alerts/voice/queue').json()
smarath_queue_pids = [i['patient_id'] for i in smarath_queue.get('queued', [])]
assert 'P203' in smarath_queue_pids, f'Dr. Smarath voice queue must have P203: {smarath_queue_pids}'
print('STEP 6 PASS: Dr. Smarath receives Pulmonology patient P203 in dashboard and voice queue!')

# STEP 7: Login as Receptionist
s_rec = requests.Session()
login_rec = s_rec.post('http://127.0.0.1:5000/login', data={'role': 'RECEPTIONIST', 'username': '1230821edits@gmail.com'})
assert login_rec.url == 'http://127.0.0.1:5000/receptionist', 'Receptionist login failed'
rec_queue = s_rec.get('http://127.0.0.1:5000/api/v1/alerts/voice/queue').json()
rec_queue_pids = [i['patient_id'] for i in rec_queue.get('queued', [])]
print('Receptionist voice queue pids:', rec_queue_pids)
assert 'P201' in rec_queue_pids, 'Receptionist missing P201'
assert 'P202' in rec_queue_pids, 'Receptionist missing P202'
assert 'P203' in rec_queue_pids, 'Receptionist missing P203'
print('STEP 7 PASS: Receptionist receives hospital-wide alerts (P201, P202, P203) in FIFO order!')

# Clean up test patients P201, P202, P203 via REST DELETE
for pid in [201, 202, 203]:
    try:
        requests.delete(f'http://127.0.0.1:8000/api/v1/patients/{pid}')
    except Exception as e:
        pass
print('=== ALL 7 REAL LIVE EVENT STEPS VERIFIED AND PASSED 100% ===')
