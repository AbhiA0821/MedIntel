from database.connection import con

patients = con.execute("SELECT * FROM Patients").fetchall()

print(f"Total Patients: {len(patients)}\n")

for patient in patients[:10]:   # Show first 10 patients
    print(patient)