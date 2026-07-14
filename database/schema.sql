CREATE TABLE Patients (
    patient_id INTEGER PRIMARY KEY,
    first_name VARCHAR NOT NULL,
    last_name VARCHAR NOT NULL,
    age INTEGER,
    gender VARCHAR,
    blood_group VARCHAR,
    ward VARCHAR,
    admission_date DATE
);


CREATE TABLE VitalSigns (
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