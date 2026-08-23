CREATE TABLE IF NOT EXISTS Patients (
    patient_id INTEGER PRIMARY KEY,
    first_name VARCHAR NOT NULL,
    last_name VARCHAR NOT NULL,
    age INTEGER,
    gender VARCHAR,
    blood_group VARCHAR,
    ward VARCHAR,
    room_no VARCHAR,
    bed_no VARCHAR,
    admission_date DATE
);


CREATE TABLE IF NOT EXISTS VitalSigns (
    vital_id INTEGER PRIMARY KEY,
    patient_id INTEGER,
    heart_rate INTEGER,
    spo2 INTEGER,
    temperature DOUBLE,
    systolic_bp INTEGER,
    diastolic_bp INTEGER,
    respiratory_rate INTEGER,
    recorded_at TIMESTAMP
);


CREATE TABLE IF NOT EXISTS AlertHistory (
    alert_id VARCHAR PRIMARY KEY,
    patient_id INTEGER,
    severity VARCHAR,
    reason VARCHAR,
    recommendation VARCHAR,
    priority VARCHAR,
    ward VARCHAR,
    room_no VARCHAR,
    bed_no VARCHAR,
    specialty VARCHAR,
    assigned_doctor VARCHAR,
    created_at TIMESTAMP,
    notification_status VARCHAR,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP,
    active BOOLEAN DEFAULT TRUE
);


CREATE TABLE IF NOT EXISTS AuthorizedDoctors (
    doctor_id VARCHAR PRIMARY KEY,
    doctor_name VARCHAR NOT NULL,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR,
    firebase_uid VARCHAR,
    specialty VARCHAR NOT NULL,
    role VARCHAR DEFAULT 'DOCTOR',
    active BOOLEAN DEFAULT TRUE,
    notification_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP
);


CREATE TABLE IF NOT EXISTS DoctorDevices (
    device_id VARCHAR PRIMARY KEY,
    doctor_id VARCHAR,
    firebase_uid VARCHAR,
    doctor_name VARCHAR,
    specialty VARCHAR,
    fcm_token VARCHAR NOT NULL,
    registered_at TIMESTAMP,
    last_seen_at TIMESTAMP,
    active BOOLEAN DEFAULT TRUE
);


CREATE TABLE IF NOT EXISTS PendingRegistrationNonces (
    nonce VARCHAR PRIMARY KEY,
    doctor_id VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE
);


CREATE TABLE IF NOT EXISTS SystemSettings (
    setting_key VARCHAR PRIMARY KEY,
    setting_value VARCHAR NOT NULL,
    updated_at TIMESTAMP
);