import random
from datetime import date, timedelta
from faker import Faker
from database.connection import get_connection

fake = Faker("en_IN")

blood_groups = [
    "O+", "B+", "A+", "AB+",
    "O-", "B-", "A-", "AB-"
]

blood_weights = [
    35, 30, 20, 8,
    3, 2, 1, 1
]

wards = (
    ["ICU"] * 10 +
    ["Emergency"] * 10 +
    ["General Medicine"] * 30 +
    ["Cardiology"] * 25 +
    ["Neurology"] * 25
)
random.shuffle(wards)


def generate_age():
    r = random.randint(1, 100)
    if r <= 10:
        return random.randint(1, 12)
    elif r <= 15:
        return random.randint(13, 17)
    elif r <= 50:
        return random.randint(18, 40)
    elif r <= 80:
        return random.randint(41, 60)
    else:
        return random.randint(61, 90)


def generate_patients():
    con = get_connection()
    try:
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        if "Patients" not in tables:
            con.execute("""
                CREATE TABLE Patients (
                    patient_id INTEGER PRIMARY KEY,
                    first_name VARCHAR NOT NULL,
                    last_name VARCHAR NOT NULL,
                    age INTEGER,
                    gender VARCHAR,
                    blood_group VARCHAR,
                    ward VARCHAR,
                    room_no VARCHAR,
                    bed_no VARCHAR,
                    admission_date DATE
                );
            """)

        con.execute("DELETE FROM Patients;")

        patients = []
        for i in range(100):
            patient_id = 101 + i
            gender = random.choice(["Male", "Female"])

            if gender == "Male":
                first_name = fake.first_name_male()
            else:
                first_name = fake.first_name_female()

            last_name = fake.last_name()
            age = generate_age()
            blood_group = random.choices(blood_groups, weights=blood_weights, k=1)[0]
            ward = wards[i]
            room_no = str(200 + (i // 4) + 1)
            bed_no = str((i % 4) + 1)

            admission_date = (
                date.today()
                - timedelta(days=random.randint(0, 30))
            )

            patients.append((
                patient_id,
                first_name,
                last_name,
                age,
                gender,
                blood_group,
                ward,
                room_no,
                bed_no,
                admission_date
            ))

        con.executemany("""
            INSERT INTO Patients (
                patient_id, first_name, last_name, age, gender,
                blood_group, ward, room_no, bed_no, admission_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, patients)

        print("====================================")
        print("[SUCCESS] 100 Patients (P101-P200) Generated Successfully with Location Metadata")
        print("====================================")
    finally:
        con.close()


if __name__ == "__main__":
    generate_patients()