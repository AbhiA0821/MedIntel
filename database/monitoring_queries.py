from database.connection import get_connection


def get_critical_patients():
    """Return patients whose latest stored vitals meet alert conditions."""

    query = """
    SELECT
        p.patient_id,
        p.first_name,
        p.last_name,
        v.heart_rate,
        v.spo2,
        v.temperature,
        v.systolic_bp,
        v.diastolic_bp
    FROM Patients p
    INNER JOIN VitalSigns v
        ON p.patient_id = v.patient_id
    WHERE
        v.spo2 < 92
        OR v.heart_rate > 100
        OR v.temperature > 38
        OR v.systolic_bp > 140;
    """

    con = get_connection()

    try:
        return con.execute(query).fetchall()
    finally:
        con.close()


def get_total_patients():
    """Return the total number of registered patients."""

    query = """
    SELECT COUNT(*)
    FROM Patients;
    """

    con = get_connection()

    try:
        return con.execute(query).fetchone()[0]
    finally:
        con.close()