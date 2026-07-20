import streamlit as st

from database.monitoring_queries import get_critical_patients
from services.reason_detection import get_patient_reasons
from services.severity_engine import classify_severity
from services.recommendation_engine import get_recommendations

# -------------------------------------------------
# Page Configuration
# -------------------------------------------------

st.set_page_config(
    page_title="MedIntel",
    page_icon="🏥",
    layout="wide"
)

# -------------------------------------------------
# Title
# -------------------------------------------------

st.title("🏥 MedIntel")
st.subheader("AI Healthcare Patient Monitoring Dashboard")

st.markdown("---")

# -------------------------------------------------
# Fetch Patient Data
# -------------------------------------------------

patients = get_critical_patients()

# -------------------------------------------------
# Dashboard Metrics
# -------------------------------------------------

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

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("👨 Total Patients", total_patients)

with col2:
    st.metric("🔴 Critical", critical)

with col3:
    st.metric("🟠 Moderate", moderate)

with col4:
    st.metric("🟢 Low Risk", low)

# -------------------------------------------------
# Critical Patient Cards
# -------------------------------------------------

st.markdown("---")
st.subheader("🚨 Critical Patients")

if "selected_patient" not in st.session_state:
    st.session_state.selected_patient = None

for patient in patients:

    severity = classify_severity(patient)

    with st.container(border=True):

        left, right = st.columns([5, 1])

        with left:

            st.markdown(f"### 👤 {patient[1]} {patient[2]}")

            st.write(f"❤️ Heart Rate : {patient[3]}")
            st.write(f"🫁 SpO₂ : {patient[4]}")
            st.write(f"🌡 Temperature : {patient[5]}")
            st.write(f"🩸 Blood Pressure : {patient[6]}/{patient[7]}")

            if severity == "Critical":
                st.error("🔴 Critical")

            elif severity == "Moderate":
                st.warning("🟠 Moderate")

            else:
                st.success("🟢 Low")

        with right:

            st.write("")

            if st.button("View Details", key=f"btn_{patient[0]}"):
                st.session_state.selected_patient = patient

# -------------------------------------------------
# Selected Patient Details
# -------------------------------------------------

if st.session_state.selected_patient:

    patient = st.session_state.selected_patient

    reasons = get_patient_reasons(patient)
    recommendations = get_recommendations(patient)
    severity = classify_severity(patient)

    st.markdown("---")
    st.header("👤 Patient Details")

    st.subheader(f"{patient[1]} {patient[2]}")

    c1, c2 = st.columns(2)

    with c1:

        st.write("### ❤️ Vital Signs")

        st.write(f"Heart Rate : {patient[3]}")
        st.write(f"SpO₂ : {patient[4]}")
        st.write(f"Temperature : {patient[5]}")
        st.write(f"Blood Pressure : {patient[6]}/{patient[7]}")

    with c2:

        st.write("### 🚦 Severity")

        if severity == "Critical":
            st.error("🔴 Critical")

        elif severity == "Moderate":
            st.warning("🟠 Moderate")

        else:
            st.success("🟢 Low")

    st.write("### ⚠️ Problems Detected")

    for reason in reasons:
        st.write(f"• {reason}")

    st.write("### 📋 Immediate Actions")

    for rec in recommendations:
        st.write(f"✅ {rec}")