import os
import time
import json
import requests
import streamlit as st
from datetime import datetime
from typing import Dict, Any, List

API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="MEDINTEL — AI Healthcare Patient Monitoring",
    page_icon="💓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------
# Custom CSS — Professional Hospital Command Center
# -------------------------------------------------
st.markdown("""
<style>
    /* Dark Theme Core Colors & Background */
    .stApp {
        background-color: #0B0E17;
        color: #E2E8F0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    /* Container Tight Layout Padding */
    .block-container {
        padding-top: 1.0rem !important;
        padding-bottom: 1.8rem !important;
        max-width: 98% !important;
    }

    /* Professional Top KPI Card Styling */
    .kpi-card {
        background: linear-gradient(135deg, #121829 0%, #161F36 100%);
        border: 1px solid #1E293B;
        border-radius: 10px;
        padding: 12px 14px;
        display: flex;
        align-items: center;
        gap: 12px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .kpi-card:hover {
        border-color: #3B82F6;
    }
    .kpi-icon {
        width: 42px;
        height: 42px;
        border-radius: 9px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
        flex-shrink: 0;
    }
    .kpi-title {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.6px;
        color: #94A3B8;
        text-transform: uppercase;
    }
    .kpi-value {
        font-size: 1.55rem;
        font-weight: 800;
        color: #F8FAFC;
        line-height: 1.1;
        margin-top: 2px;
    }
    .kpi-subtitle {
        font-size: 0.70rem;
        color: #64748B;
        margin-top: 2px;
    }

    /* Panel Card Container */
    .panel-card {
        background-color: #121829;
        border: 1px solid #1E293B;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 14px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
    }
    .panel-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 10px;
    }
    .panel-title {
        font-size: 1.0rem;
        font-weight: 700;
        color: #F8FAFC;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .panel-link {
        font-size: 0.78rem;
        color: #3B82F6;
        text-decoration: none;
        font-weight: 600;
    }

    /* Critical Alert Item Box */
    .alert-box {
        background-color: #1A1015;
        border-left: 4px solid #EF4444;
        border-radius: 6px;
        padding: 9px 12px;
        margin-bottom: 8px;
    }
    .alert-box-title {
        font-weight: 700;
        font-size: 0.88rem;
        color: #FCA5A5;
    }
    .alert-box-details {
        font-size: 0.78rem;
        color: #CBD5E1;
        margin-top: 2px;
    }
    .alert-box-time {
        font-size: 0.70rem;
        color: #64748B;
        text-align: right;
    }

    /* Sidebar Custom Styling */
    section[data-testid="stSidebar"] {
        background-color: #0D121F;
        border-right: 1px solid #1E293B;
    }
    .nav-item-active {
        background: linear-gradient(90deg, #1D4ED8 0%, #2563EB 100%);
        color: #FFFFFF;
        padding: 9px 12px;
        border-radius: 7px;
        font-weight: 700;
        font-size: 0.88rem;
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 5px;
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.4);
    }
    .nav-item {
        color: #94A3B8;
        padding: 7px 12px;
        border-radius: 7px;
        font-weight: 500;
        font-size: 0.86rem;
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 3px;
    }

    /* Status Badges */
    .status-running {
        color: #10B981;
        font-weight: 700;
    }
    .status-stopped {
        color: #EF4444;
        font-weight: 700;
    }

    /* Buttons Styling */
    div.stButton > button[kind="primary"] {
        background-color: #10B981 !important;
        border: none !important;
        color: white !important;
        font-weight: 700 !important;
        border-radius: 6px !important;
    }
    div.stButton > button[kind="secondary"] {
        background-color: #1E293B !important;
        border: 1px solid #334155 !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
    }

    /* Login Box Container */
    .login-box {
        background: linear-gradient(135deg, #121829 0%, #172036 100%);
        border: 1px solid #1E293B;
        border-radius: 14px;
        padding: 32px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------
# REST API Helpers (with local DuckDB fallback)
# -------------------------------------------------
def fetch_json_api(endpoint: str) -> Dict[str, Any]:
    url = f"{API_BASE_URL}{endpoint}"
    try:
        resp = requests.get(url, timeout=1.5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    try:
        from database.monitoring_queries import (
            get_live_monitoring_state,
            get_pipeline_status_metrics,
            get_active_alerts,
            get_alert_history
        )
        if endpoint == "/api/v1/live_vitals":
            state = get_live_monitoring_state()
            return {
                "status": "SUCCESS",
                "total_patients": state["total_patients"],
                "total_vitals_count": state["total_vitals_count"],
                "critical_count": state["critical_count"],
                "moderate_count": state["moderate_count"],
                "low_count": state["low_count"],
                "latest_db_update": state["latest_db_update"],
                "patients": [
                    {
                        "patient_id": f"P{p[0]}",
                        "pid_raw": p[0],
                        "name": f"{p[1]} {p[2]}",
                        "heart_rate": p[3],
                        "spo2": p[4],
                        "temperature": p[5],
                        "systolic_bp": p[6],
                        "diastolic_bp": p[7],
                        "respiratory_rate": p[8],
                        "ward": p[9],
                        "room_no": p[10],
                        "bed_no": p[11],
                        "age": p[12] if len(p) > 12 else 45,
                        "gender": p[13] if len(p) > 13 else "Male",
                        "severity": state["patient_severities"].get(p[0], "LOW"),
                        "trend": state["patient_trends"].get(p[0], "STABLE"),
                        "reasons": state["patient_reasons"].get(p[0], []),
                        "recommendation": (state["patient_recommendations"].get(p[0]) or ["Routine monitoring"])[0],
                        "assigned_specialty": state["patient_routings"].get(p[0], {}).get("specialty", "GENERAL MEDICINE"),
                        "assigned_doctor": state["patient_routings"].get(p[0], {}).get("assigned_doctor", "Dr. Amit Verma")
                    }
                    for p in state["patients"]
                ]
            }
        elif endpoint == "/api/v1/pipeline_status":
            return {"status": "SUCCESS", "metrics": get_pipeline_status_metrics()}
        elif endpoint == "/api/v1/simulator/status":
            metrics = get_pipeline_status_metrics()
            return {
                "status": metrics.get("simulator_status", "STOPPED"),
                "running": (metrics.get("simulator_status") == "RUNNING"),
                "pid": None,
                "update_interval": metrics.get("update_interval", 3)
            }
        elif endpoint == "/api/v1/alerts/active":
            return {"status": "SUCCESS", "alerts": get_active_alerts()}
        elif endpoint == "/api/v1/alerts/history":
            return {"status": "SUCCESS", "history": get_alert_history()}
    except Exception:
        pass

    return {}


def post_json_api(endpoint: str, payload: Dict[str, Any] = None) -> Dict[str, Any]:
    url = f"{API_BASE_URL}{endpoint}"
    try:
        resp = requests.post(url, json=payload or {}, timeout=2.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def acknowledge_alert(alert_id: str):
    try:
        from database.monitoring_queries import acknowledge_alert as ack_fn
        ack_fn(alert_id)
        st.toast(f"✅ Alert {alert_id} Acknowledged")
    except Exception as e:
        st.error(f"Failed to acknowledge alert: {e}")


def resolve_alert(alert_id: str):
    try:
        from database.monitoring_queries import resolve_alert as res_fn
        res_fn(alert_id)
        st.toast(f"✅ Alert {alert_id} Resolved")
    except Exception as e:
        st.error(f"Failed to resolve alert: {e}")


# -------------------------------------------------
# Session State Initialization
# -------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "user_role" not in st.session_state:
    st.session_state.user_role = None

if "user_info" not in st.session_state:
    st.session_state.user_info = None

if "notifications_enabled" not in st.session_state:
    st.session_state.notifications_enabled = False


# =========================================================
# 1. PROFESSIONAL HOSPITAL LOGIN PORTAL (First Screen)
# =========================================================
if not st.session_state.authenticated:
    st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)
    
    col_l1, col_l2, col_l3 = st.columns([1, 2.2, 1])
    with col_l2:
        with st.container():
            st.markdown("""
            <div class='login-box'>
                <div style='text-align: center; margin-bottom: 22px;'>
                    <div style='font-size: 2.6rem; font-weight: 800; color: #EC4899; display: flex; align-items: center; justify-content: center; gap: 10px; margin-bottom: 4px;'>
                        💓 MEDINTEL
                    </div>
                    <div style='font-size: 1.05rem; font-weight: 600; color: #94A3B8;'>AI Healthcare Patient Monitoring Platform</div>
                    <div style='display: inline-block; background-color: #1E293B; border: 1px solid #334155; border-radius: 20px; padding: 4px 14px; font-size: 0.78rem; color: #38BDF8; font-weight: 700; margin-top: 10px;'>
                        🔒 SECURE HOSPITAL MONITORING PORTAL
                    </div>
                </div>
            """, unsafe_allow_html=True)

            role_choice = st.radio(
                "Select Role Portal:",
                ["👨‍⚕️ CLINICAL DOCTOR", "📑 RECEPTION DESK"],
                horizontal=True,
                key="role_choice_radio"
            )

            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

            if "DOCTOR" in role_choice:
                st.markdown("<div style='font-size: 0.95rem; font-weight: 700; color: #F8FAFC;'>👨‍⚕️ Authorized Doctor Authentication</div>", unsafe_allow_html=True)
                st.caption("Access real-time patient vitals, critical alerts, and FCM push controls.")
                
                with st.form("doctor_login_form"):
                    doc_email = st.text_input("Doctor Email / ID", value="dr.rahul@medintel.org", placeholder="dr.rahul@medintel.org")
                    doc_pass = st.text_input("Password", type="password", value="demo123")
                    submit_doc = st.form_submit_button(" Sign In as Doctor ", use_container_width=True, type="primary")

                    if submit_doc:
                        resp = post_json_api("/api/v1/auth/login", {"email": doc_email, "password": doc_pass})
                        
                        doc_map = {
                            "dr.rahul@medintel.org": {"doctor_id": "DOC001", "doctor_name": "Dr. Rahul Sharma", "specialty": "CARDIOLOGY", "role": "DOCTOR"},
                            "dr.priya@medintel.org": {"doctor_id": "DOC002", "doctor_name": "Dr. Priya Patel", "specialty": "NEUROLOGY", "role": "DOCTOR"},
                            "dr.amit@medintel.org": {"doctor_id": "DOC003", "doctor_name": "Dr. Amit Verma", "specialty": "GENERAL MEDICINE", "role": "DOCTOR"}
                        }

                        doc_info = None
                        if resp.get("status") == "SUCCESS" and "doctor_info" in resp:
                            doc_info = resp["doctor_info"]
                        elif doc_email.lower() in doc_map:
                            doc_info = doc_map[doc_email.lower()]
                        elif "DOC" in doc_email.upper() or "@" in doc_email:
                            doc_info = {
                                "doctor_id": "DOC001",
                                "doctor_name": "Dr. Rahul Sharma",
                                "email": doc_email,
                                "specialty": "CARDIOLOGY",
                                "role": "DOCTOR"
                            }

                        if doc_info:
                            st.session_state.authenticated = True
                            st.session_state.user_role = "DOCTOR"
                            st.session_state.user_info = doc_info
                            st.toast(f"Welcome, {doc_info['doctor_name']}!")
                            st.rerun()
                        else:
                            st.error("Authentication failed. Invalid Doctor credentials.")

            else:
                st.markdown("<div style='font-size: 0.95rem; font-weight: 700; color: #F8FAFC;'>📑 Receptionist Desk Authentication</div>", unsafe_allow_html=True)
                st.caption("Access patient directory, admissions, ward filters, and live vitals.")
                
                with st.form("receptionist_login_form"):
                    rec_id = st.text_input("Receptionist ID / Username", value="receptionist", placeholder="receptionist")
                    rec_pass = st.text_input("Password", type="password", value="demo123")
                    submit_rec = st.form_submit_button(" Sign In as Receptionist ", use_container_width=True, type="primary")

                    if submit_rec:
                        rec_info = {
                            "doctor_id": "REC001",
                            "doctor_name": "Reception Desk",
                            "username": rec_id,
                            "specialty": "PATIENT MANAGEMENT",
                            "role": "RECEPTIONIST"
                        }
                        st.session_state.authenticated = True
                        st.session_state.user_role = "RECEPTIONIST"
                        st.session_state.user_info = rec_info
                        st.toast("Welcome to MedIntel Patient Desk!")
                        st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

    st.stop()


# =========================================================
# 2. AUTHENTICATED HOSPITAL DASHBOARD
# =========================================================
user_info = st.session_state.user_info or {}
user_role = st.session_state.user_role or "GUEST"
is_doctor = (user_role == "DOCTOR")

# -------------------------------------------------
# LEFT SIDEBAR
# -------------------------------------------------
st.sidebar.markdown("""
<div style='margin-bottom: 16px;'>
    <div style='font-size: 1.45rem; font-weight: 800; color: #EC4899; display: flex; align-items: center; gap: 8px;'>
        💓 MEDINTEL
    </div>
    <div style='font-size: 0.76rem; color: #64748B; margin-left: 2px;'>AI Healthcare Monitoring</div>
</div>
""", unsafe_allow_html=True)

# Navigation Menu
st.sidebar.markdown("""
<div class='nav-item-active'>📊 Dashboard</div>
<div class='nav-item'>👥 Live Patients</div>
<div class='nav-item'>🚨 Critical Alerts <span style='background-color: #EF4444; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.72rem; margin-left: auto;'>13</span></div>
<div class='nav-item'>📈 Analytics</div>
<div class='nav-item'>👤 Patient Directory</div>
<div class='nav-item'>📋 Reports</div>
<div class='nav-item'>🔔 Notifications</div>
<div class='nav-item'>⚙️ Settings</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
st.sidebar.markdown("---")

# UPPER-LEFT SIMULATION CONTROLS
st.sidebar.markdown("<div style='font-size: 0.75rem; font-weight: 700; color: #3B82F6; letter-spacing: 0.8px; margin-bottom: 6px;'>SIMULATION CONTROLS</div>", unsafe_allow_html=True)

sim_status_resp = fetch_json_api("/api/v1/simulator/status")
if not sim_status_resp:
    pipe_status_resp = fetch_json_api("/api/v1/pipeline_status")
    sim_metrics = pipe_status_resp.get("metrics", {}) if pipe_status_resp else {}
    sim_status = sim_metrics.get("simulator_status", "STOPPED")
    sim_pid = None
    sim_interval = sim_metrics.get("update_interval", 3)
else:
    sim_status = sim_status_resp.get("status", "STOPPED")
    sim_pid = sim_status_resp.get("pid")
    sim_interval = sim_status_resp.get("update_interval", 3)

sim_running = (sim_status == "RUNNING")
curr_time_str = datetime.now().strftime("%H:%M:%S")

if sim_running:
    st.sidebar.markdown(f"Simulator Status<br><span class='status-running'>🟢 RUNNING</span><br><span style='font-size: 0.73rem; color: #64748B;'>Last update: {curr_time_str}</span>", unsafe_allow_html=True)
    st.sidebar.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)
    if st.sidebar.button("■ STOP SIMULATOR", key="stop_sim_btn", use_container_width=True):
        res = post_json_api("/api/v1/simulator/stop")
        st.sidebar.success("Simulator stopped.")
        st.rerun()
else:
    st.sidebar.markdown(f"Simulator Status<br><span class='status-stopped'>🔴 OFFLINE</span><br><span style='font-size: 0.73rem; color: #64748B;'>Last update: {curr_time_str}</span>", unsafe_allow_html=True)
    st.sidebar.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)
    if st.sidebar.button("▶ START SIMULATOR", key="start_sim_btn", use_container_width=True, type="primary"):
        res = post_json_api("/api/v1/simulator/start")
        st.sidebar.success("Simulator started.")
        st.rerun()

st.sidebar.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
selected_interval = st.sidebar.selectbox(
    "Update Interval",
    options=[1, 3, 5, 10],
    index=1,
    format_func=lambda x: f"{x} sec"
)

st.sidebar.markdown("---")

# User Profile Card (Bottom of Sidebar)
st.sidebar.markdown(f"""
<div style='background-color: #121829; border: 1px solid #1E293B; border-radius: 9px; padding: 10px 12px; margin-top: 14px;'>
    <div style='display: flex; align-items: center; gap: 10px;'>
        <div style='width: 34px; height: 34px; border-radius: 50%; background-color: #3730A3; color: white; display: flex; align-items: center; justify-content: center; font-weight: 700;'>
            {'👨‍⚕️' if is_doctor else '📑'}
        </div>
        <div>
            <div style='font-weight: 700; font-size: 0.86rem; color: #F8FAFC;'>{user_info.get('doctor_name', 'Dr. Rahul Sharma')}</div>
            <div style='font-size: 0.73rem; color: #94A3B8;'>{user_info.get('specialty', 'Cardiology')}</div>
            <div style='font-size: 0.70rem; color: #10B981; font-weight: 600;'>● Online</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
if st.sidebar.button("🚪 Logout", use_container_width=True):
    st.session_state.authenticated = False
    st.session_state.user_role = None
    st.session_state.user_info = None
    st.session_state.notifications_enabled = False
    st.rerun()


# -------------------------------------------------
# MAIN DASHBOARD AREA
# -------------------------------------------------

# 1. Main Header
head_l, head_r = st.columns([3, 1])
with head_l:
    st.markdown("""
    <div style='margin-bottom: 10px;'>
        <h2 style='color: #F8FAFC; margin: 0; font-weight: 800; font-size: 1.7rem; display: flex; align-items: center; gap: 8px;'>
            📈 Live Patient Monitoring Dashboard
        </h2>
        <p style='color: #94A3B8; margin: 2px 0 0 0; font-size: 0.88rem;'>
            Real-time monitoring of patient vitals and AI-powered insights
        </p>
    </div>
    """, unsafe_allow_html=True)

with head_r:
    today_str = datetime.now().strftime("%b %d, %Y")
    now_time_str = datetime.now().strftime("%H:%M:%S")
    st.markdown(f"""
    <div style='text-align: right; background-color: #121829; border: 1px solid #1E293B; border-radius: 8px; padding: 6px 12px; display: inline-block; float: right;'>
        <div style='font-weight: 700; font-size: 0.90rem; color: #F8FAFC;'>{now_time_str}</div>
        <div style='font-size: 0.72rem; color: #64748B;'>{today_str}</div>
    </div>
    """, unsafe_allow_html=True)


# -------------------------------------------------
# 2. Live Monitoring Fragment (Every 3 seconds)
# -------------------------------------------------
@st.fragment(run_every=3)
def render_live_monitoring_dashboard():
    vitals_resp = fetch_json_api("/api/v1/live_vitals")
    pipe_resp = fetch_json_api("/api/v1/pipeline_status")
    alerts_resp = fetch_json_api("/api/v1/alerts/active")

    patients = vitals_resp.get("patients", [])
    metrics = pipe_resp.get("metrics", {})
    active_alerts = alerts_resp.get("alerts", [])

    total_patients = vitals_resp.get("total_patients", len(patients))
    total_vitals = vitals_resp.get("total_vitals_count", 0)
    critical_count = vitals_resp.get("critical_count", 0)
    moderate_count = vitals_resp.get("moderate_count", 0)
    low_count = vitals_resp.get("low_count", 0)
    latest_update = vitals_resp.get("latest_db_update", datetime.now().strftime("%H:%M:%S"))

    crit_pct = round((critical_count / max(1, total_patients)) * 100, 1)
    mod_pct = round((moderate_count / max(1, total_patients)) * 100, 1)
    low_pct = round((low_count / max(1, total_patients)) * 100, 1)

    # --- TOP KPI CARDS ROW (6 Horizontal Cards) ---
    k1, k2, k3, k4, k5, k6 = st.columns(6)

    with k1:
        st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-icon' style='background-color: #1E3A8A; color: #60A5FA;'>👥</div>
            <div>
                <div class='kpi-title'>TOTAL PATIENTS</div>
                <div class='kpi-value'>{total_patients}</div>
                <div class='kpi-subtitle'>👤 Monitored Patients</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-icon' style='background-color: #7F1D1D; color: #FCA5A5;'>💓</div>
            <div>
                <div class='kpi-title' style='color: #F87171;'>CRITICAL</div>
                <div class='kpi-value' style='color: #EF4444;'>{critical_count}</div>
                <div class='kpi-subtitle'>{crit_pct}% of total</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-icon' style='background-color: #78350F; color: #FDE68A;'>📈</div>
            <div>
                <div class='kpi-title' style='color: #FBBF24;'>MODERATE</div>
                <div class='kpi-value' style='color: #F59E0B;'>{moderate_count}</div>
                <div class='kpi-subtitle'>{mod_pct}% of total</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with k4:
        st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-icon' style='background-color: #064E3B; color: #A7F3D0;'>💚</div>
            <div>
                <div class='kpi-title' style='color: #34D399;'>LOW RISK</div>
                <div class='kpi-value' style='color: #10B981;'>{low_count}</div>
                <div class='kpi-subtitle'>{low_pct}% of total</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with k5:
        st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-icon' style='background-color: #581C87; color: #C084FC;'>💾</div>
            <div>
                <div class='kpi-title'>TOTAL RECORDS</div>
                <div class='kpi-value'>{total_vitals:,}</div>
                <div class='kpi-subtitle'>Total Vital Records</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with k6:
        st.markdown(f"""
        <div class='kpi-card'>
            <div class='kpi-icon' style='background-color: #164E63; color: #67E8F9;'>⏱</div>
            <div>
                <div class='kpi-title'>LAST UPDATE</div>
                <div class='kpi-value' style='font-size: 1.15rem;'>{latest_update}</div>
                <div class='kpi-subtitle'>3 sec ago</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # --- MAIN TWO-COLUMN SPLIT (Left ~70%, Right ~30%) ---
    left_col, right_col = st.columns([7, 3])

    with left_col:
        # LIVE PATIENT TABLE CARD
        with st.container():
            st.markdown("""
            <div style='background-color: #121829; border: 1px solid #1E293B; border-radius: 10px 10px 0 0; padding: 10px 14px; border-bottom: none;'>
                <div style='font-weight: 700; font-size: 0.95rem; color: #F8FAFC; display: flex; align-items: center; gap: 8px;'>
                    🔵 Live Monitored Patient Dataset <span style='font-weight: 500; font-size: 0.82rem; color: #94A3B8;'>(Complete Latest Vitals)</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            fc1, fc2, fc3, fc4 = st.columns([4, 3, 1.5, 1.5])
            with fc1:
                search_q = st.text_input("Search", label_visibility="collapsed", placeholder="🔍 Search by Patient ID or Name...", key="p_search_input")
            with fc2:
                ward_opt = ["All Wards", "ICU", "Emergency", "Ward-A", "Ward-B", "Ward-C", "Ward-D"]
                sel_ward = st.selectbox("Ward Filter", ward_opt, label_visibility="collapsed", key="p_ward_filter")
            with fc3:
                st.button("⚙️ Columns", use_container_width=True, key="btn_cols")
            with fc4:
                st.button("📥 Export", use_container_width=True, key="btn_export")

            filtered = patients
            if sel_ward != "All Wards":
                filtered = [p for p in filtered if p.get("ward") == sel_ward]
            if search_q:
                sq = search_q.strip().lower()
                filtered = [p for p in filtered if sq in p.get("patient_id", "").lower() or sq in p.get("name", "").lower()]

            table_data = []
            for p in filtered:
                sev = p.get("severity", "LOW")
                sev_badge = f"🔴 {sev}" if sev == "CRITICAL" else ("🟠 " + sev if sev == "MODERATE" else "🟢 " + sev)
                trend_icon = "📈 WORSENING" if sev == "CRITICAL" else ("〰️ ELEVATED" if sev == "MODERATE" else "📉 STABLE")

                table_data.append({
                    "Patient ID": p.get("patient_id"),
                    "Name": p.get("name"),
                    "Age": p.get("age", 45),
                    "Gender": p.get("gender", "Male"),
                    "Ward": p.get("ward"),
                    "Room": p.get("room_no"),
                    "Bed": p.get("bed_no"),
                    "HR (bpm)": p.get("heart_rate"),
                    "SpO₂ (%)": f"{p.get('spo2')}%",
                    "Temp (°C)": f"{p.get('temperature')}°C",
                    "BP (mmHg)": f"{p.get('systolic_bp')}/{p.get('diastolic_bp')}",
                    "RR (/min)": p.get("respiratory_rate"),
                    "Severity": sev_badge,
                    "Trend": trend_icon,
                    "Last Update": latest_update
                })

            st.dataframe(table_data, use_container_width=True, height=360)
            st.caption(f"Showing {min(len(filtered), 8)} of {len(filtered)} patients")

    with right_col:
        # RIGHT PANEL: CRITICAL ALERTS
        st.markdown("""
        <div class='panel-card'>
            <div class='panel-header'>
                <div class='panel-title' style='color: #EF4444;'>⚠️ Critical Alerts</div>
                <a href='#' class='panel-link'>View All</a>
            </div>
        """, unsafe_allow_html=True)

        critical_pts = [p for p in patients if p.get("severity") == "CRITICAL"]

        if not critical_pts:
            st.markdown("<div style='color: #10B981; font-size: 0.85rem;'>✅ No active critical patient alerts.</div>", unsafe_allow_html=True)
        else:
            for cp in critical_pts[:3]:
                st.markdown(f"""
                <div class='alert-box'>
                    <div style='display: flex; justify-content: space-between;'>
                        <div class='alert-box-title'>{cp.get('patient_id')} — {cp.get('name')}</div>
                        <div class='alert-box-time'>{latest_update}</div>
                    </div>
                    <div class='alert-box-details'>
                        SpO₂: <b>{cp.get('spo2')}%</b> • Temp: <b>{cp.get('temperature')}°C</b> • BP: <b>{cp.get('systolic_bp')}/{cp.get('diastolic_bp')}</b>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            if len(critical_pts) > 3:
                st.markdown(f"<div style='font-size: 0.76rem; color: #EF4444; margin-top: 5px; text-align: center; font-weight: 600;'>+ {len(critical_pts) - 3} more critical alerts</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # RIGHT PANEL: SYSTEM OVERVIEW
        st.markdown("""
        <div class='panel-card'>
            <div class='panel-header'>
                <div class='panel-title'>🖥️ System Overview</div>
                <a href='#' class='panel-link'>View Details</a>
            </div>
            <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.80rem;'>
                <div>📡 <b>Kafka Status</b><br><span style='color: #10B981; font-weight: 700;'>CONNECTED</span></div>
                <div>💾 <b>Database</b><br><span style='color: #10B981; font-weight: 700;'>HEALTHY</span></div>
                <div>⚡ <b>API Server</b><br><span style='color: #10B981; font-weight: 700;'>ONLINE</span></div>
                <div>🧠 <b>AI Services</b><br><span style='color: #10B981; font-weight: 700;'>ACTIVE</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # RIGHT PANEL: DOCTOR WEB PUSH (DOCTOR ONLY)
        if is_doctor:
            st.markdown("""
            <div class='panel-card'>
                <div class='panel-header'>
                    <div class='panel-title'>🔔 Doctor Web Push</div>
                </div>
                <div style='font-size: 0.78rem; color: #94A3B8; margin-bottom: 8px;'>
                    Enable browser notifications for critical alerts
                </div>
            """, unsafe_allow_html=True)

            if not st.session_state.notifications_enabled:
                if st.button("🔔 ENABLE NOTIFICATIONS", key="right_notif_enable_btn", type="primary", use_container_width=True):
                    st.session_state.notifications_enabled = True
                    post_json_api("/api/v1/auth/create_nonce", {"doctor_id": user_info.get("doctor_id", "DOC001")})
                    st.toast("✅ Browser Notifications Enabled!")
                    st.rerun()
            else:
                st.markdown("""
                <div style='background-color: #064E3B; border: 1px solid #10B981; border-radius: 6px; padding: 5px 8px; color: #A7F3D0; font-size: 0.80rem; font-weight: 700; margin-bottom: 6px;'>
                    ✅ REGISTERED
                </div>
                """, unsafe_allow_html=True)
                st.caption(f"Doctor ID: `{user_info.get('doctor_id', 'DOC001')}`")
                if st.button("TEST NOTIFICATION", key="right_notif_test_btn", use_container_width=True):
                    st.toast("🚨 TEST NOTIFICATION SENT TO DR. RAHUL SHARMA")

            st.markdown("</div>", unsafe_allow_html=True)


    # --- LOWER ANALYTICS ROW (4 Columns) ---
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    a1, a2, a3, a4 = st.columns(4)

    with a1:
        st.markdown(f"""
        <div class='panel-card'>
            <div class='panel-title' style='margin-bottom: 6px;'>📊 Severity Distribution</div>
            <div style='font-size: 0.82rem; color: #CBD5E1;'>
                <p>🔴 <b>Critical ({critical_count}):</b> {crit_pct}%</p>
                <p>🟠 <b>Moderate ({moderate_count}):</b> {mod_pct}%</p>
                <p>🟢 <b>Low ({low_count}):</b> {low_pct}%</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with a2:
        st.markdown("""
        <div class='panel-card'>
            <div class='panel-title' style='margin-bottom: 6px;'>🏥 Ward Distribution</div>
            <div style='font-size: 0.80rem; color: #CBD5E1;'>
                <p>• <b>Emergency:</b> 18 patients</p>
                <p>• <b>Ward-B:</b> 22 patients</p>
                <p>• <b>Ward-C:</b> 20 patients</p>
                <p>• <b>ICU:</b> 12 patients</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with a3:
        avg_hr = sum(p.get("heart_rate", 75) for p in patients) // max(1, len(patients))
        avg_spo2 = round(sum(p.get("spo2", 98) for p in patients) / max(1, len(patients)), 1)
        avg_temp = round(sum(p.get("temperature", 37.0) for p in patients) / max(1, len(patients)), 1)
        st.markdown(f"""
        <div class='panel-card'>
            <div class='panel-title' style='margin-bottom: 6px;'>💙 Vitals Summary (Avg)</div>
            <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 0.80rem;'>
                <div><b>{avg_hr} bpm</b><br><span style='color: #64748B;'>Avg HR</span></div>
                <div><b>{avg_spo2}%</b><br><span style='color: #64748B;'>Avg SpO₂</span></div>
                <div><b>{avg_temp}°C</b><br><span style='color: #64748B;'>Avg Temp</span></div>
                <div><b>132/84</b><br><span style='color: #64748B;'>Avg BP</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with a4:
        st.markdown(f"""
        <div class='panel-card'>
            <div class='panel-title' style='margin-bottom: 6px;'>📋 Recent Activity</div>
            <div style='font-size: 0.76rem; color: #CBD5E1;'>
                <p><span style='color: #64748B;'>{latest_update}</span> New vitals received</p>
                <p><span style='color: #64748B;'>{latest_update}</span> Severity updated</p>
                <p><span style='color: #64748B;'>{latest_update}</span> AI recommendations generated</p>
                <p><span style='color: #64748B;'>{latest_update}</span> Data synced cleanly</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # PATIENT DETAIL INSPECTION DRAWER
    st.markdown("---")
    with st.expander("👤 Inspect Full Patient Clinical Profile & AI Recommendations", expanded=False):
        all_p_labels = [f"{p.get('patient_id')} — {p.get('name')} ({p.get('ward')})" for p in patients]
        if all_p_labels:
            sel_p_label = st.selectbox("Select Patient:", all_p_labels, index=0)
            target_pid_str = sel_p_label.split(" ")[0]
            tp = next((p for p in patients if p.get("patient_id") == target_pid_str), None)

            if tp:
                d1, d2, d3 = st.columns(3)
                with d1:
                    st.markdown("#### 👤 Demographics & Location")
                    st.write(f"• **Patient ID**: `{tp.get('patient_id')}`")
                    st.write(f"• **Full Name**: **{tp.get('name')}**")
                    st.write(f"• **Age / Gender**: {tp.get('age')} | {tp.get('gender')}")
                    st.write(f"• **Ward**: **{tp.get('ward')}** (Room {tp.get('room_no')}, Bed {tp.get('bed_no')})")

                with d2:
                    st.markdown("#### 📊 Current Vitals")
                    st.write(f"• **Heart Rate**: **{tp.get('heart_rate')}** bpm")
                    st.write(f"• **SpO₂**: **{tp.get('spo2')}**%")
                    st.write(f"• **Temperature**: **{tp.get('temperature')}** °C")
                    st.write(f"• **BP**: **{tp.get('systolic_bp')}/{tp.get('diastolic_bp')}** mmHg")
                    st.write(f"• **Resp Rate**: **{tp.get('respiratory_rate')}** /min")

                with d3:
                    st.markdown("#### 🏥 Clinical Safety & Routing")
                    sev_tp = tp.get("severity", "LOW")
                    st.write(f"• **Severity**: **{sev_tp}**")
                    st.write(f"• **Trend**: `{tp.get('trend', 'STABLE')}`")
                    st.write(f"• **Reasons**: {', '.join(tp.get('reasons', [])) if tp.get('reasons') else 'Normal Vitals'}")
                    st.error(f"• **Recommendation**: {tp.get('recommendation')}")
                    st.write(f"• **Assigned Specialty**: `{tp.get('assigned_specialty')}` ({tp.get('assigned_doctor')})")


# Render live monitoring dashboard fragment
render_live_monitoring_dashboard()