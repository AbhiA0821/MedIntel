import streamlit as st

from database.monitoring_queries import get_critical_patients
from services.reason_detection import get_patient_reasons
from services.severity_engine import classify_severity
from services.recommendation_engine import generate_recommendation


# -------------------------------
# Page Configuration
# -------------------------------
st.set_page_config(
    page_title="MedIntel",
    page_icon="🏥",
    layout="wide"
)

# -------------------------------
# Dashboard Title
# -------------------------------
st.title("🏥 MedIntel")
st.subheader("AI Healthcare Patient Monitoring Dashboard")

st.markdown("---")

# -------------------------------
# Get Patient Data
# -------------------------------
patients = get_critical_patients()

# -------------------------------
# Summary Metrics
# -------------------------------
col1, col2, col3, col4 = st.columns(4)

total_patients = len(patients)
critical = 0
moderate = 0
low = 0

for patient in patients:

    severity = classify_severity(patient)

    if severity == "Critical":
        critical += 1

    elif severity == "Moderate":
        moderate += 1

    else:
        low += 1


with col1:
    st.metric("👨 Monitored Patients", total_patients)

with col2:
    st.metric("🔴 Critical", critical)

with col3:
    st.metric("🟡 Moderate", moderate)

with col4:
    st.metric("🟢 Low Risk", low)


# -------------------------------
# Critical Patient Table
# -------------------------------
st.markdown("---")
st.subheader("🚨 Critical Patient Details")

table_data = []

for patient in patients:

    severity = classify_severity(patient)
    reasons = ", ".join(get_patient_reasons(patient))

    table_data.append({
        "Patient ID": patient[0],
        "Name": f"{patient[1]} {patient[2]}",
        "Heart Rate": patient[3],
        "SpO₂": patient[4],
        "Temperature": patient[5],
        "Blood Pressure": f"{patient[6]}/{patient[7]}",
        "Severity": severity,
        "Reason": reasons
    })

st.dataframe(
    table_data,
    use_container_width=True,
    hide_index=True
)


# -------------------------------
# AI Recommendations
# -------------------------------
st.markdown("---")
st.subheader("📋 AI Recommendations")

for patient in patients:

    recommendation = generate_recommendation(patient)

    st.info(
        f"**{patient[1]} {patient[2]}**\n\n"
        f"{recommendation}"
    )