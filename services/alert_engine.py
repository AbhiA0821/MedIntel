from services.severity_engine import classify_severity

def generate_alert(patient):
    severity = classify_severity(patient)

    if severity=="Critical":
        return{
            "health_status": "Critical",
            "alert_level": "Critical",
            "alert_color": "red",
            "alert_icon": "🔴",
            "alert_message": "Immediate medical attention required."
        }
    
    elif severity=="Moderate":
        return{
            "health_status": "Moderate",
            "alert_level": "Moderate",
            "alert_color": "orange",
            "alert_icon": "🟡",
            "alert_message": "Patient requires close monitoring."
        }
    
    else:
        return{
            "health_status": "Good",
            "alert_level": "Low",
            "alert_color": "green",
            "alert_icon": "🟢",
            "alert_message": "Patient condition is stable."
        }

# -------------------------------
# Testing
# -------------------------------        
if __name__ == "__main__":

    patient = (
        1,
        "Rahul Sharma",
        130,
        84,
        39.2,
        170,
        105
    )

    alert = generate_alert(patient)

    print("=" * 50)
    print("MEDINTEL ALERT ENGINE")
    print("=" * 50)

    print(f"Health Status : {alert['health_status']}")
    print(f"Alert Level   : {alert['alert_level']}")
    print(f"Alert Color   : {alert['alert_color']}")
    print(f"Alert Icon    : {alert['alert_icon']}")
    print(f"Message       : {alert['alert_message']}")       
    