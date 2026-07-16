import duckdb
con=duckdb.connect("database/medintel.duckdb")

def get_critical_patients():
    query="""
    SELECT
    p.first_name,
    p.last_name,
    v.heart_rate,
    v.spo2,
    v.temperature,
    v.systolic_bp
FROM Patients p
INNER JOIN VitalSigns v
ON p.patient_id = v.patient_id
WHERE
    v.spo2 < 92
    OR v.heart_rate > 100
    OR v.temperature > 38
    OR v.systolic_bp > 140;
    """

    return con.execute(query).fetchall()

critical_patients = get_critical_patients()

for patient in critical_patients:
    print(patient)

con.close()