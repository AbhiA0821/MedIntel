import duckdb
from database.connection import get_connection


def save_processed_data(df):
    """
    Save the processed Spark DataFrame into DuckDB.
    """

    # Convert Spark DataFrame to Pandas
    pandas_df = df.toPandas()

    # Connect to DuckDB
    con = get_connection()

    try:
        # Drop table if it already exists
        con.execute("""
            DROP TABLE IF EXISTS ProcessedPatientVitals
        """)

        # Register the Pandas DataFrame as a temporary table
        con.register("patient_df", pandas_df)

        # Create a new table from the DataFrame
        con.execute("""
            CREATE TABLE ProcessedPatientVitals AS
            SELECT
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
                status
            FROM patient_df
        """)

        # Remove temporary registration
        con.unregister("patient_df")

        print("=" * 50)
        print("ProcessedPatientVitals table created successfully!")
        print("=" * 50)

        # Show total rows inserted
        total = con.execute("""
            SELECT COUNT(*)
            FROM ProcessedPatientVitals
        """).fetchone()[0]

        print(f"Total Records Saved : {total}")

    except Exception as e:
        print("Error while saving processed data:")
        print(e)

    finally:
        con.close()


# ---------------------------------------------------------
# Optional Test
# ---------------------------------------------------------

if __name__ == "__main__":
    print("This module is intended to be imported into preprocessing.py")