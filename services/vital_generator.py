import random


# ----------------------------------------
# Heart Rate
# ----------------------------------------
def generate_heart_rate():
    chance = random.randint(1, 100)

    if chance <= 80:
        return random.randint(60, 100)      # Normal

    elif chance <= 95:
        return random.randint(101, 140)     # High

    else:
        return random.randint(40, 59)       # Low


# ----------------------------------------
# SpO2
# ----------------------------------------
def generate_spo2():
    chance = random.randint(1, 100)

    if chance <= 85:
        return random.randint(95, 100)      # Normal

    elif chance <= 95:
        return random.randint(88, 91)       # Low

    else:
        return random.randint(80, 87)       # Critical


# ----------------------------------------
# Temperature
# ----------------------------------------
def generate_temperature():
    chance = random.randint(1, 100)

    if chance <= 85:
        return round(random.uniform(36.5, 37.5), 1)

    else:
        return round(random.uniform(38.0, 39.5), 1)


# ----------------------------------------
# Blood Pressure
# ----------------------------------------
def generate_blood_pressure():
    chance = random.randint(1, 100)

    if chance <= 80:

        systolic = random.randint(100, 120)
        diastolic = random.randint(65, 80)

    else:

        systolic = random.randint(141, 170)
        diastolic = random.randint(90, 110)

    return systolic, diastolic


# ----------------------------------------
# Generate Complete Vitals
# ----------------------------------------
def generate_vitals():

    systolic_bp, diastolic_bp = generate_blood_pressure()

    vitals = {
        "heart_rate": generate_heart_rate(),
        "spo2": generate_spo2(),
        "temperature": generate_temperature(),
        "systolic_bp": systolic_bp,
        "diastolic_bp": diastolic_bp
    }

    return vitals


# ----------------------------------------
# Testing
# ----------------------------------------
if __name__ == "__main__":

    print("Sample Generated Vitals\n")

    for i in range(10):

        print(f"Patient {i+1}")
        print(generate_vitals())
        print("-" * 50)