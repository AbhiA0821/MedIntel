from database.connection import get_connection

MAX_PROCESSED_READINGS_PER_PATIENT = 50


def save_streaming_processed_data(df, epoch_id=None):
    """
    Save a newly processed streaming PySpark micro-batch into DuckDB ProcessedPatientVitals.

    Incoming streaming records are enriched with patient demographics from the Patients table,
    duplicate vital IDs are avoided, existing records are preserved, and only the latest 50
    processed readings per patient are retained.
    """
    pandas_df = df.toPandas()

    if pandas_df.empty:
        print("No streaming processed records to save.")
        return

    con = get_connection()

    try:
        # Register new streaming batch as temporary DuckDB view
        con.register("new_streaming_batch", pandas_df)

        # --------------------------------------------------
        # Create table on first run if it does not exist
        # --------------------------------------------------
        con.execute("""
            CREATE TABLE IF NOT EXISTS ProcessedPatientVitals AS
            SELECT
                b.vital_id,
                b.patient_id,
                p.first_name,
                p.last_name,
                p.age,
                p.gender,
                p.blood_group,
                p.ward,
                p.admission_date,

                b.heart_rate,
                b.spo2,
                b.temperature,
                b.systolic_bp,
                b.diastolic_bp,
                b.respiratory_rate,

                b.hr_valid,
                b.spo2_valid,
                b.temperature_valid,
                b.systolic_valid,
                b.diastolic_valid,
                b.respiratory_valid,

                b.status,
                CAST(b.recorded_at AS TIMESTAMP) AS recorded_at
            FROM new_streaming_batch b
            LEFT JOIN Patients p ON b.patient_id = p.patient_id
            WHERE 1 = 0
        """)

        # --------------------------------------------------
        # Remove duplicate vital IDs if batch is retried
        # --------------------------------------------------
        con.execute("""
            DELETE FROM ProcessedPatientVitals
            WHERE vital_id IN (
                SELECT vital_id
                FROM new_streaming_batch
            )
        """)

        # --------------------------------------------------
        # Insert new processed streaming batch with patient metadata
        # --------------------------------------------------
        con.execute("""
            INSERT INTO ProcessedPatientVitals
            SELECT
                b.vital_id,
                b.patient_id,
                p.first_name,
                p.last_name,
                p.age,
                p.gender,
                p.blood_group,
                p.ward,
                p.admission_date,

                b.heart_rate,
                b.spo2,
                b.temperature,
                b.systolic_bp,
                b.diastolic_bp,
                b.respiratory_rate,

                b.hr_valid,
                b.spo2_valid,
                b.temperature_valid,
                b.systolic_valid,
                b.diastolic_valid,
                b.respiratory_valid,

                b.status,
                CAST(b.recorded_at AS TIMESTAMP) AS recorded_at
            FROM new_streaming_batch b
            LEFT JOIN Patients p ON b.patient_id = p.patient_id
        """)

        # --------------------------------------------------
        # Keep latest 50 processed readings per patient
        # --------------------------------------------------
        con.execute(f"""
            DELETE FROM ProcessedPatientVitals
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
                    FROM ProcessedPatientVitals
                )
                WHERE row_number > {MAX_PROCESSED_READINGS_PER_PATIENT}
            )
        """)

        total = con.execute("""
            SELECT COUNT(*)
            FROM ProcessedPatientVitals
        """).fetchone()[0]

        patients = con.execute("""
            SELECT COUNT(DISTINCT patient_id)
            FROM ProcessedPatientVitals
        """).fetchone()[0]

        epoch_str = f"Batch {epoch_id} | " if epoch_id is not None else ""
        print(
            f"[DuckDB Writer] {epoch_str}Saved {len(pandas_df)} records. "
            f"Total Processed Patient Vitals in DB: {total}, Patients: {patients}"
        )

    except Exception as e:
        print(f"Error saving streaming processed data: {e}")
        raise

    finally:
        try:
            con.unregister("new_streaming_batch")
        except Exception:
            pass
        con.close()


if __name__ == "__main__":
    print("Use this module through the MedIntel streaming processing pipeline.")
