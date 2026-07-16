import duckdb
con=duckdb.connect("database/medintel.duckdb")


#Cheaking which are criical
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


#Reason for patient critical conditon
def get_patient_reasons(patient):
    reasons=[]
    heart_rate = patient[2]
    spo2 = patient[3]
    temperature = patient[4]
    systolic_bp = patient[5]
    if spo2 < 92:
        reasons.append("Low Oxygen")
    if heart_rate > 100:
        reasons.append("High Heart Rate")
    if temperature > 38:
        reasons.append("High Temperature")    
    if systolic_bp > 140:
        reasons.append("High Blood Pressure")

    return reasons


critical_patients = get_critical_patients()

#calling function for eah patientthat return name and reason
for patient in critical_patients:
    reasons = get_patient_reasons(patient)
    print("=" * 50)
    print(f"Patient : {patient[0]} {patient[1]}")
    
    print("Reasons:")
    for reason in reasons:
        print(f"{reason}")




con.close()