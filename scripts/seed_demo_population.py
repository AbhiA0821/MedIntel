"""
MedIntel Controlled 11-Patient Demo Population Seeder
Seeds the database with exactly the 11 demo patients distributed across:
  - Cardiology: P101, P102, P103 (3 patients) -> Dr. Viraj Patil
  - Pulmonology: P104, P105, P106, P107, P108, P109 (6 patients) -> Dr. Smarath Pawar
  - General Medicine: P110, P111 (2 patients) -> Dr. Shreya Sutar
Authoritative doctors are initialized in AuthorizedDoctors.
"""

import sys
from pathlib import Path
from datetime import datetime, date

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import duckdb
from database.connection import get_db_path

DEMO_DOCTORS = [
    ("DOC001", "Dr. Viraj Patil", "dr.viraj@medintel.org", "FB-DOC001", "CARDIOLOGY", "DOCTOR", True),
    ("DOC002", "Dr. Smarath Pawar", "dr.smarath@medintel.org", "FB-DOC002", "PULMONOLOGY", "DOCTOR", True),
    ("DOC003", "Dr. Shreya Sutar", "dr.shreya@medintel.org", "FB-DOC003", "GENERAL MEDICINE", "DOCTOR", True),
    ("REC001", "Reception Desk", "reception@medintel.org", "FB-REC001", "HOSPITAL ADMISSIONS", "RECEPTIONIST", True)
]

DEMO_PATIENTS = [
    # Cardiology (3)
    (101, "Rahul", "Patil", 45, "Male", "B+", "Cardiology", "201", "1", date(2026, 7, 14), "CARDIOLOGY"),
    (102, "Priya", "Sharma", 52, "Female", "O+", "Cardiology", "201", "2", date(2026, 7, 13), "CARDIOLOGY"),
    (103, "Hardik", "Jani", 38, "Male", "A+", "Cardiology", "201", "3", date(2026, 7, 12), "CARDIOLOGY"),
    # Pulmonology (6)
    (104, "Bhanumati", "Dasgupta", 61, "Female", "AB+", "Pulmonology", "202", "1", date(2026, 7, 11), "PULMONOLOGY"),
    (105, "Lavanya", "Sinha", 49, "Female", "O-", "Pulmonology", "202", "2", date(2026, 7, 10), "PULMONOLOGY"),
    (106, "Harshil", "Palla", 58, "Male", "B+", "Pulmonology", "202", "3", date(2026, 7, 9), "PULMONOLOGY"),
    (107, "Ria", "Chada", 42, "Female", "A-", "Pulmonology", "203", "1", date(2026, 7, 8), "PULMONOLOGY"),
    (108, "Rohan", "Desai", 35, "Male", "O+", "Pulmonology", "203", "2", date(2026, 7, 7), "PULMONOLOGY"),
    (109, "Ananya", "Sen", 29, "Female", "B+", "Pulmonology", "203", "3", date(2026, 7, 6), "PULMONOLOGY"),
    # General Medicine (2)
    (110, "Vikram", "Sethi", 67, "Male", "AB-", "General Medicine", "204", "1", date(2026, 7, 5), "GENERAL MEDICINE"),
    (111, "Sunita", "Rao", 33, "Female", "O+", "General Medicine", "204", "2", date(2026, 7, 4), "GENERAL MEDICINE")
]

INITIAL_VITALS = [
    # (pid, hr, spo2, temp, sbp, dbp, rr)
    (101, 126, 87, 37.2, 130, 85, 22),   # CRITICAL (SpO2 87 < 90)
    (102, 105, 96, 39.1, 135, 88, 20),   # CRITICAL (Temp 39.1 > 38.5)
    (103, 124, 95, 37.1, 138, 86, 20),   # MODERATE (HR 124 > 120)
    (104, 98, 86, 37.3, 128, 82, 26),    # CRITICAL (SpO2 86 < 90)
    (105, 102, 88, 38.7, 132, 84, 25),   # CRITICAL (SpO2 88 < 90, Temp 38.7)
    (106, 110, 85, 37.0, 126, 80, 28),   # CRITICAL (SpO2 85 < 90)
    (107, 88, 94, 37.2, 125, 80, 26),    # MODERATE (RR 26 > 24)
    (108, 76, 98, 36.8, 120, 80, 16),    # LOW (Demo Target: Deteriorate -> CRITICAL)
    (109, 78, 97, 36.9, 118, 78, 17),    # LOW
    (110, 92, 96, 38.9, 130, 84, 19),    # CRITICAL (Temp 38.9 > 38.5)
    (111, 72, 98, 36.7, 116, 76, 15)     # LOW (Demo Target: Deteriorate -> CRITICAL)
]


def _seed_authorized_doctors(con):
    """Upserts authoritative doctors without altering patient records."""
    print("Verifying Authoritative Doctors...", flush=True)
    for doc in DEMO_DOCTORS:
        doc_id, name, email, fb_uid, specialty, role, active = doc
        exists = con.execute("SELECT 1 FROM AuthorizedDoctors WHERE doctor_id = ?", [doc_id]).fetchone()
        if exists:
            con.execute("""
                UPDATE AuthorizedDoctors
                SET doctor_name = ?, email = ?, specialty = ?, role = ?, active = ?
                WHERE doctor_id = ?;
            """, [name, email, specialty, role, active, doc_id])
        else:
            con.execute("""
                INSERT INTO AuthorizedDoctors (doctor_id, doctor_name, email, firebase_uid, specialty, role, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, [doc_id, name, email, fb_uid, specialty, role, active, datetime.now()])


def seed_demo_population(force: bool = False, db_path=None):
    target_path = Path(db_path) if db_path else get_db_path()
    con = duckdb.connect(str(target_path))
    try:
        print("Ensuring schema integrity...")
        # Check if tables exist
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        if "Patients" not in tables:
            from database.setup_database import init_database
            init_database(target_path)

        # Check Patients schema and add specialty column if missing
        cols = [c[1] for c in con.execute("PRAGMA table_info('Patients');").fetchall()]
        if "specialty" not in cols:
            con.execute("ALTER TABLE Patients ADD COLUMN specialty VARCHAR;")
            print("Added 'specialty' column to Patients table.")

        # Check if already populated
        existing_patients = con.execute("SELECT COUNT(*) FROM Patients").fetchone()[0]
        if existing_patients > 0 and not force:
            print(f"[SEED] Database already populated with {existing_patients} patients. Preserving existing clinical records.")
            _seed_authorized_doctors(con)
            return

        # Seed AuthorizedDoctors
        _seed_authorized_doctors(con)

        # Clear old patient records and seed exactly 11 demo patients
        print("Seeding 11 Controlled Demo Patients...")
        con.execute("DELETE FROM Patients;")
        con.executemany("""
            INSERT INTO Patients (
                patient_id, first_name, last_name, age, gender,
                blood_group, ward, room_no, bed_no, admission_date, specialty
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, DEMO_PATIENTS)

        # Clear existing alerts and reset vitals
        print("Initializing Baseline Vitals and Alert History...")
        con.execute("DELETE FROM AlertHistory;")
        con.execute("DELETE FROM VitalSigns;")

        now = datetime.now()
        vital_id = 1
        vitals_data = []
        for v in INITIAL_VITALS:
            pid, hr, spo2, temp, sbp, dbp, rr = v
            # Insert two consecutive records so trends initialize to STABLE
            vitals_data.append((vital_id, pid, hr, spo2, temp, sbp, dbp, rr, now))
            vital_id += 1
            vitals_data.append((vital_id, pid, hr, spo2, temp, sbp, dbp, rr, now))
            vital_id += 1

        con.executemany("""
            INSERT INTO VitalSigns (vital_id, patient_id, heart_rate, spo2, temperature, systolic_bp, diastolic_bp, respiratory_rate, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, vitals_data)

        # Verify counts
        p_count = con.execute("SELECT COUNT(*) FROM Patients").fetchone()[0]
        d_count = con.execute("SELECT COUNT(*) FROM AuthorizedDoctors").fetchone()[0]
        v_count = con.execute("SELECT COUNT(*) FROM VitalSigns").fetchone()[0]
        print(f"[SUCCESS] Database seeded successfully: {p_count} patients, {d_count} authorized staff, {v_count} baseline vitals.")
    finally:
        con.close()


if __name__ == "__main__":
    force_seed = "--force" in sys.argv
    seed_demo_population(force=force_seed)
