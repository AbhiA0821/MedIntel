"""
MedIntel Database Schema & Patient Population Migration Script
Adds assigned_doctor_id to Patients table and restores the full 100+ patient population
from ProcessedPatientVitals while strictly preserving the 11 controlled demo patients.
"""

import sys
from pathlib import Path
from datetime import datetime, date

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import duckdb
from database.connection import DB_PATH

def migrate_database():
    con = duckdb.connect(str(DB_PATH))
    try:
        print("[MIGRATION] Starting MedIntel Database Schema & Patient Population Migration...")

        # 1. Add assigned_doctor_id column if missing
        cols = [c[1] for c in con.execute("PRAGMA table_info('Patients');").fetchall()]
        if "assigned_doctor_id" not in cols:
            con.execute("ALTER TABLE Patients ADD COLUMN assigned_doctor_id VARCHAR;")
            print("[SCHEMA] Added 'assigned_doctor_id' column to Patients table.")
        else:
            print("[SCHEMA] 'assigned_doctor_id' column already present.")

        # 2. Update existing demo patients (P101-P112)
        con.execute("UPDATE Patients SET assigned_doctor_id = 'DOC001', specialty = 'CARDIOLOGY' WHERE patient_id IN (101, 102, 103);")
        con.execute("UPDATE Patients SET assigned_doctor_id = 'DOC002', specialty = 'PULMONOLOGY' WHERE patient_id IN (104, 105, 106, 107, 108, 109);")
        con.execute("UPDATE Patients SET assigned_doctor_id = 'DOC003', specialty = 'GENERAL MEDICINE' WHERE patient_id >= 110;")
        print("[DEMO POPULATION] Preserved demo patients (101-112) with authoritative doctor assignments.")

        # 3. Check existing patient IDs
        existing_pids = set(r[0] for r in con.execute("SELECT patient_id FROM Patients").fetchall())
        print(f"[STATUS] Current patient count in Patients table: {len(existing_pids)}")

        # 4. Get missing patients from ProcessedPatientVitals (patients 113-200)
        missing_rows = con.execute("""
            SELECT patient_id, first_name, last_name, age, gender, blood_group, ward, admission_date
            FROM ProcessedPatientVitals
            WHERE patient_id NOT IN (SELECT patient_id FROM Patients)
            GROUP BY ALL
            ORDER BY patient_id
        """).fetchall()

        print(f"[RESTORATION] Missing patient records found in ProcessedPatientVitals: {len(missing_rows)}")

        new_patients = []
        for r in missing_rows:
            pid, fn, ln, age, gender, bg, ward, adm_date = r
            room_no = str(200 + ((pid - 101) // 4) + 1)
            bed_no = str(((pid - 101) % 4) + 1)

            ward_str = str(ward or "General Medicine").strip()
            if ward_str in ["Cardiology", "Cardiology Ward", "Ward-A", "ICU"]:
                spec = "CARDIOLOGY"
                doc_id = "DOC001"
            elif ward_str in ["Pulmonology", "Pulmonology Ward", "Ward-B", "Ward-C"]:
                spec = "PULMONOLOGY"
                doc_id = "DOC002"
            else:
                spec = "GENERAL MEDICINE"
                doc_id = "DOC003"

            new_patients.append((pid, fn, ln, age, gender, bg, ward_str, room_no, bed_no, adm_date, spec, doc_id))

        if new_patients:
            con.executemany("""
                INSERT INTO Patients (
                    patient_id, first_name, last_name, age, gender,
                    blood_group, ward, room_no, bed_no, admission_date,
                    specialty, assigned_doctor_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, new_patients)
            print(f"[POPULATION] Inserted {len(new_patients)} patient records into Patients table.")

        total_p = con.execute("SELECT COUNT(*) FROM Patients").fetchone()[0]
        print(f"[SUCCESS] Authoritative total active patient count in Patients table: {total_p}")

        # 5. Ensure baseline vitals exist for all patients in VitalSigns table
        existing_vital_pids = set(r[0] for r in con.execute("SELECT DISTINCT patient_id FROM VitalSigns").fetchall())
        all_pids = [r[0] for r in con.execute("SELECT patient_id FROM Patients ORDER BY patient_id").fetchall()]
        missing_vital_pids = [p for p in all_pids if p not in existing_vital_pids]

        if missing_vital_pids:
            max_vid = con.execute("SELECT COALESCE(MAX(vital_id), 0) FROM VitalSigns").fetchone()[0]
            now = datetime.now()
            new_vitals = []
            vid = max_vid + 1
            for pid in missing_vital_pids:
                # 2 stable readings per patient so trend initializes cleanly to STABLE
                new_vitals.append((vid, pid, 75, 98, 36.8, 120, 80, 16, now))
                vid += 1
                new_vitals.append((vid, pid, 75, 98, 36.8, 120, 80, 16, now))
                vid += 1
            con.executemany("""
                INSERT INTO VitalSigns (vital_id, patient_id, heart_rate, spo2, temperature, systolic_bp, diastolic_bp, respiratory_rate, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, new_vitals)
            print(f"[VITALS] Inserted baseline vitals for {len(missing_vital_pids)} patients into VitalSigns.")

        # Breakdown by specialty
        breakdown = con.execute("""
            SELECT specialty, assigned_doctor_id, COUNT(*)
            FROM Patients
            GROUP BY specialty, assigned_doctor_id
            ORDER BY specialty;
        """).fetchall()
        print("[BREAKDOWN] Specialty & Doctor Breakdown in Patients table:")
        for b in breakdown:
            print(f"  * {b[0]} ({b[1]}): {b[2]} patients")

        print("[COMPLETE] Migration completed successfully!")
    finally:
        con.close()

if __name__ == "__main__":
    migrate_database()
