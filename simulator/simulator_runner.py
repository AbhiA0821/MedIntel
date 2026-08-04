import duckdb
import time
from datetime import datetime
from pathlib import Path

from simulator.patient_simulator import generate_vitals


# --------------------------------------------------
# Configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "database" / "medintel.duckdb"

# Generate new patient readings every 5 seconds
INTERVAL_SECONDS = 5

# Keep only the latest 50 readings for each patient
MAX_READINGS_PER_PATIENT = 50


# --------------------------------------------------
# Generate and Store Patient Vitals
# --------------------------------------------------

def generate_and_store_vitals():

    conn = duckdb.connect(str(DB_PATH))

    try:
        # Get all registered patients
        patients = conn.execute("""
            SELECT patient_id
            FROM Patients
            ORDER BY patient_id
        """).fetchall()

        if not patients:
            print("No patients found in Patients table.")
            return

        # Get next available vital_id
        next_vital_id = conn.execute("""
            SELECT COALESCE(MAX(vital_id), 0) + 1
            FROM VitalSigns
        """).fetchone()[0]

        inserted_count = 0

        # Generate one new reading for every patient
        for (patient_id,) in patients:

            vitals = generate_vitals()

            # Insert new vital reading
            conn.execute("""
                INSERT INTO VitalSigns (
                    vital_id,
                    patient_id,
                    heart_rate,
                    spo2,
                    temperature,
                    systolic_bp,
                    diastolic_bp,
                    respiratory_rate,
                    recorded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                next_vital_id,
                patient_id,
                vitals["heart_rate"],
                vitals["spo2"],
                vitals["temperature"],
                vitals["systolic_bp"],
                vitals["diastolic_bp"],
                vitals["respiratory_rate"],
                datetime.now()
            ])

            # --------------------------------------------------
            # Keep only latest 50 readings for this patient
            # --------------------------------------------------

            conn.execute("""
                DELETE FROM VitalSigns
                WHERE vital_id IN (
                    SELECT vital_id
                    FROM VitalSigns
                    WHERE patient_id = ?
                    ORDER BY recorded_at DESC, vital_id DESC
                    OFFSET ?
                )
            """, [
                patient_id,
                MAX_READINGS_PER_PATIENT
            ])

            next_vital_id += 1
            inserted_count += 1

        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"Generated vitals for {inserted_count} patients."
        )

    except Exception as e:

        print(f"Error while generating patient vitals: {e}")

    finally:

        conn.close()


# --------------------------------------------------
# Continuous Patient Monitoring Simulator
# --------------------------------------------------

def run_simulator():

    print("=" * 60)
    print("MedIntel Patient Vital Simulator Started")
    print("=" * 60)

    print(
        f"Generating patient vitals every "
        f"{INTERVAL_SECONDS} seconds."
    )

    print(
        f"Keeping latest "
        f"{MAX_READINGS_PER_PATIENT} readings per patient."
    )

    print("Press Ctrl+C to stop.")
    print("=" * 60)
    print()

    try:

        while True:

            generate_and_store_vitals()

            time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:

        print()
        print("=" * 60)
        print("MedIntel Patient Vital Simulator stopped.")
        print("=" * 60)


# --------------------------------------------------
# Application Entry Point
# --------------------------------------------------

if __name__ == "__main__":

    run_simulator()