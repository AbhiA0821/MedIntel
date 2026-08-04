from database.connection import get_connection


MAX_PROCESSED_READINGS_PER_PATIENT = 50


def save_processed_data(df):
    """
    Save a newly processed PySpark batch into DuckDB.

    Existing processed records are preserved, duplicate vital IDs
    are avoided, and only the latest 50 processed readings per
    patient are retained.
    """

    pandas_df = df.toPandas()

    if pandas_df.empty:
        print("No processed records to save.")
        return

    con = get_connection()

    try:

        # Register new processed batch
        con.register(
            "new_processed_batch",
            pandas_df
        )

        # --------------------------------------------------
        # Create table on first run
        # --------------------------------------------------

        con.execute("""
            CREATE TABLE IF NOT EXISTS ProcessedPatientVitals AS

            SELECT
                vital_id,
                patient_id,
                first_name,
                last_name,
                age,
                gender,
                blood_group,
                ward,
                admission_date,

                heart_rate,
                spo2,
                temperature,
                systolic_bp,
                diastolic_bp,
                respiratory_rate,

                hr_valid,
                spo2_valid,
                temperature_valid,
                systolic_valid,
                diastolic_valid,
                respiratory_valid,

                status,
                recorded_at

            FROM new_processed_batch

            WHERE 1 = 0
        """)

        # --------------------------------------------------
        # Remove duplicate vital IDs if batch is retried
        # --------------------------------------------------

        con.execute("""
            DELETE FROM ProcessedPatientVitals
            WHERE vital_id IN (
                SELECT vital_id
                FROM new_processed_batch
            )
        """)

        # --------------------------------------------------
        # Insert new processed batch
        # --------------------------------------------------

        con.execute("""
            INSERT INTO ProcessedPatientVitals

            SELECT
                vital_id,
                patient_id,
                first_name,
                last_name,
                age,
                gender,
                blood_group,
                ward,
                admission_date,

                heart_rate,
                spo2,
                temperature,
                systolic_bp,
                diastolic_bp,
                respiratory_rate,

                hr_valid,
                spo2_valid,
                temperature_valid,
                systolic_valid,
                diastolic_valid,
                respiratory_valid,

                status,
                recorded_at

            FROM new_processed_batch
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

                WHERE row_number >
                    {MAX_PROCESSED_READINGS_PER_PATIENT}
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

        print(
            f"Processed batch saved. "
            f"Stored records: {total}, "
            f"Patients: {patients}"
        )

    except Exception as e:

        print(
            f"Error saving processed data: {e}"
        )

        raise

    finally:

        try:
            con.unregister(
                "new_processed_batch"
            )
        except Exception:
            pass

        con.close()


if __name__ == "__main__":

    print(
        "Use this module through "
        "the MedIntel processing pipeline."
    )