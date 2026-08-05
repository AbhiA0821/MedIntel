import duckdb
from datetime import datetime
from pathlib import Path

from simulator.patient_simulator import generate_vitals


# =====================================================
# Configuration
# =====================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "database" / "medintel.duckdb"

MAX_READINGS_PER_PATIENT = 50


# =====================================================
# Generate ONE Batch of Patient Vitals
# =====================================================

def generate_and_store_vitals():

    con = duckdb.connect(str(DB_PATH))

    try:

        # -------------------------------------------------
        # Get all active patients
        # -------------------------------------------------

        patients = con.execute("""
            SELECT patient_id
            FROM Patients
            ORDER BY patient_id
        """).fetchall()

        if not patients:

            print("No patients found.")

            return []

        # -------------------------------------------------
        # Find next available vital ID
        # -------------------------------------------------

        next_vital_id = con.execute("""
            SELECT COALESCE(MAX(vital_id), 0) + 1
            FROM VitalSigns
        """).fetchone()[0]

        # -------------------------------------------------
        # Generate complete batch in memory
        # -------------------------------------------------

        batch = []
        new_vital_ids = []

        batch_timestamp = datetime.now()

        for (patient_id,) in patients:

            vitals = generate_vitals()

            current_vital_id = next_vital_id

            batch.append(
                (
                    current_vital_id,
                    patient_id,
                    vitals["heart_rate"],
                    vitals["spo2"],
                    vitals["temperature"],
                    vitals["systolic_bp"],
                    vitals["diastolic_bp"],
                    vitals["respiratory_rate"],
                    batch_timestamp
                )
            )

            new_vital_ids.append(
                current_vital_id
            )

            next_vital_id += 1

        # -------------------------------------------------
        # Begin transaction
        # -------------------------------------------------

        con.execute("BEGIN TRANSACTION")

        try:

            # =============================================
            # ONE BATCH INSERT
            # =============================================

            con.executemany("""
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
            """, batch)

            # =============================================
            # ONE CLEANUP QUERY
            #
            # Keep latest 50 readings PER patient.
            # =============================================

            con.execute(f"""
                DELETE FROM VitalSigns
                WHERE vital_id IN (

                    SELECT vital_id
                    FROM (

                        SELECT
                            vital_id,

                            ROW_NUMBER() OVER (
                                PARTITION BY patient_id
                                ORDER BY
                                    recorded_at DESC,
                                    vital_id DESC
                            ) AS row_number

                        FROM VitalSigns
                    )

                    WHERE row_number >
                        {MAX_READINGS_PER_PATIENT}
                )
            """)

            con.execute("COMMIT")

        except Exception:

            con.execute("ROLLBACK")

            raise

        print(
            f"Generated {len(new_vital_ids)} "
            f"new vital readings."
        )

        return new_vital_ids

    except Exception as e:

        print(
            f"Vital generation failed: {e}"
        )

        raise

    finally:

        con.close()


# =====================================================
# Standalone Test
# =====================================================

if __name__ == "__main__":

    ids = generate_and_store_vitals()

    print("New Vital IDs:")
    print(ids)