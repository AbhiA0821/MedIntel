import random
from datetime import date, timedelta

from faker import Faker
from database.connection import con

fake = Faker("en_IN")

# -----------------------------
# Blood Group Distribution
# -----------------------------
blood_groups = [
    "O+", "B+", "A+", "AB+",
    "O-", "B-", "A-", "AB-"
]

blood_weights = [
    35, 30, 20, 8,
    3, 2, 1, 1
]

# -----------------------------
# Ward Distribution
# -----------------------------
wards = (
    ["ICU"] * 10 +
    ["Emergency"] * 10 +
    ["Ward-A"] * 30 +
    ["Ward-B"] * 25 +
    ["Ward-C"] * 25
)

random.shuffle(wards)


# -----------------------------
# Age Generator
# -----------------------------
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


# -----------------------------
# Main Function
# -----------------------------
def generate_patients():

    # Remove old data
    con.execute("DELETE FROM Patients")

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

        blood_group = random.choices(
            blood_groups,
            weights=blood_weights,
            k=1
        )[0]

        ward = wards[i]

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
            admission_date
        ))

    con.executemany("""
        INSERT INTO Patients
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, patients)

    print("====================================")
    print("✅ 100 Patients Generated Successfully")
    print("====================================")


# -----------------------------
# Run File
# -----------------------------
if __name__ == "__main__":
    generate_patients()