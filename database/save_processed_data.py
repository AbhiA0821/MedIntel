from database.connection import get_connection


def save_processed_data(df):
    """
    Save processed patient vital records from PySpark into DuckDB.

    The table is refreshed with the currently retained raw vital-sign
    readings. VitalSigns already keeps only the latest 50 readings
    per patient.
    """

    # Convert Spark DataFrame to Pandas
    pandas_df = df.toPandas()

    if pandas_df.empty:
        print("No processed records available to save.")
        return

    con = get_connection()

    try:

        # --------------------------------------------------
        # Replace previous processed snapshot
        # --------------------------------------------------

        con.execute("""
            DROP TABLE IF EXISTS ProcessedPatientVitals
        """)

        # Register Pandas DataFrame temporarily
        con.register(
            "patient_df",
            pandas_df
        )

        # --------------------------------------------------
        # Create Processed Table
        # --------------------------------------------------

        con.execute("""
            CREATE TABLE ProcessedPatientVitals AS

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

            FROM patient_df

            ORDER BY
                patient_id,
                recorded_at DESC
        """)

        con.unregister("patient_df")

        # --------------------------------------------------
        # Verification
        # --------------------------------------------------

        total = con.execute("""
            SELECT COUNT(*)
            FROM ProcessedPatientVitals
        """).fetchone()[0]

        patients = con.execute("""
            SELECT COUNT(DISTINCT patient_id)
            FROM ProcessedPatientVitals
        """).fetchone()[0]

        print("=" * 60)
        print("ProcessedPatientVitals created successfully!")
        print("=" * 60)

        print(f"Total processed records : {total}")
        print(f"Patients represented    : {patients}")

        print("=" * 60)

    except Exception as e:

        print("Error while saving processed data:")
        print(e)

        raise

    finally:

        con.close()


# =====================================================
# Optional Test
# =====================================================

if __name__ == "__main__":

    print(
        "This module is intended to be "
        "used by pyspark_pipeline.preprocessing"
    )