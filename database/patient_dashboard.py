#This file represents the query your Flask dashboard will eventually use.
#Join in sql

import duckdb
con=duckdb.connect("database/medintel.duckdb")

query="""
SELECT
    p.patient_id,
    p.first_name,
    p.last_name,
    p.ward,
     v.heart_rate,
    v.spo2,
    v.temperature,
    v.systolic_bp,
    v.diastolic_bp,
    v.respiratory_rate
FROM Patients p    
INNER JOIN VitalSigns v
ON p.patient_id=v.patient_id;
"""

rows = con.execute(query).fetchall()

print("===== Patient Monitoring Dashboard =====\n")

for row in rows:
    print(row)

con.close()    