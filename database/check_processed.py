from database.connection import get_connection

con = get_connection()

try:
    print("=" * 60)
    print("ProcessedPatientVitals Table")
    print("=" * 60)

    result = con.execute("""
        SELECT *
        FROM ProcessedPatientVitals
        LIMIT 10
    """).fetchdf()

    print(result)

    total = con.execute("""
        SELECT COUNT(*)
        FROM ProcessedPatientVitals
    """).fetchone()[0]

    print("\nTotal Records :", total)

except Exception as e:
    print("Error:")
    print(e)

finally:
    con.close()