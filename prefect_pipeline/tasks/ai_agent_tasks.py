from prefect import task
import duckdb
from pathlib import Path
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "database" / "medintel.duckdb"

# ==============================================================================
# AGENT 1: PATIENT ANALYSIS AGENT
# ==============================================================================

@task(name="run_patient_analysis_agent", retries=1, retry_delay_seconds=2)
def run_patient_analysis_agent(ml_inference_results: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Agent 1: Patient Analysis Agent
    
    Responsibilities:
    - Analyze processed patient vitals.
    - Analyze recent patient history.
    - Interpret ML output.
    - Identify abnormal patterns/trends.
    - Produce structured patient analysis.
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        source_table = "ProcessedPatientVitals" if "ProcessedPatientVitals" in tables else "VitalSigns"

        vitals = con.execute(f"""
            SELECT p.patient_id, p.first_name, p.last_name, v.heart_rate, v.spo2, v.temperature, v.systolic_bp, v.diastolic_bp, v.respiratory_rate
            FROM Patients p
            INNER JOIN {source_table} v ON p.patient_id = v.patient_id
            ORDER BY p.patient_id
        """).fetchall()

        ml_predictions_map = {}
        if ml_inference_results and "predictions" in ml_inference_results:
            for pred in ml_inference_results["predictions"]:
                ml_predictions_map[pred["patient_id"]] = pred

        analyses = []
        for v in vitals:
            pid, fname, lname = v[0], v[1], v[2]
            hr, spo2, temp, sys_bp, dia_bp, resp = v[3], v[4], v[5], v[6], v[7], v[8]

            ml_pred = ml_predictions_map.get(pid, {"risk_score": 0.0, "risk_category": "Unknown"})

            abnormal_patterns = []
            if spo2 < 92:
                abnormal_patterns.append(f"Hypoxia (SpO2: {spo2}%)")
            if temp > 38.0:
                abnormal_patterns.append(f"Pyrexia/Fever (Temp: {temp}°C)")
            if hr > 100:
                abnormal_patterns.append(f"Tachycardia (HR: {hr} bpm)")
            if sys_bp > 140:
                abnormal_patterns.append(f"Hypertension (BP: {sys_bp}/{dia_bp} mmHg)")
            if resp > 24:
                abnormal_patterns.append(f"Tachypnea (Resp Rate: {resp}/min)")

            trend = "Deteriorating" if len(abnormal_patterns) >= 2 else ("Stable with Anomalies" if len(abnormal_patterns) == 1 else "Stable")

            analyses.append({
                "patient_id": pid,
                "patient_name": f"{fname} {lname}",
                "vital_summary": {
                    "heart_rate": hr,
                    "spo2": spo2,
                    "temperature": temp,
                    "blood_pressure": f"{sys_bp}/{dia_bp}",
                    "respiratory_rate": resp
                },
                "ml_risk_evaluation": ml_pred,
                "abnormal_patterns": abnormal_patterns,
                "overall_trend": trend
            })

        return {
            "agent_name": "Agent 1 — Patient Analysis Agent",
            "analyzed_patients_count": len(analyses),
            "patient_analyses": analyses
        }
    finally:
        con.close()


# ==============================================================================
# AGENT 2: RECOMMENDATION & ALERT AGENT
# ==============================================================================

@task(name="run_recommendation_alert_agent", retries=1, retry_delay_seconds=2)
def run_recommendation_alert_agent(patient_analysis_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Agent 2: Recommendation & Alert Agent
    
    Responsibilities:
    - Receive Agent 1 analysis.
    - Generate grounded recommendations.
    - Determine alert priority.
    - Generate dashboard-ready recommendations/alerts.
    """
    analyses = patient_analysis_output.get("patient_analyses", [])
    recommendations_and_alerts = []

    for analysis in analyses:
        pid = analysis["patient_id"]
        name = analysis["patient_name"]
        patterns = analysis["abnormal_patterns"]
        trend = analysis["overall_trend"]
        ml_eval = analysis.get("ml_risk_evaluation", {})

        recommendations = []
        if any("Hypoxia" in p for p in patterns):
            recommendations.append("Administer supplemental O2 and notify respiratory therapy.")
        if any("Pyrexia" in p for p in patterns):
            recommendations.append("Administer antipyretics and draw blood cultures if clinically indicated.")
        if any("Tachycardia" in p for p in patterns):
            recommendations.append("Perform 12-lead ECG and check telemetry.")
        if any("Hypertension" in p for p in patterns):
            recommendations.append("Recheck BP in 15 minutes; evaluate for antihypertensive protocol.")

        if not recommendations:
            recommendations.append("Continue routine vital sign monitoring.")

        # Determine Alert Priority
        if trend == "Deteriorating" or ml_eval.get("risk_category") == "High Risk" or len(patterns) >= 2:
            alert_priority = "CRITICAL"
            alert_color = "red"
        elif len(patterns) == 1 or ml_eval.get("risk_category") == "Moderate Risk":
            alert_priority = "MODERATE"
            alert_color = "orange"
        else:
            alert_priority = "LOW"
            alert_color = "green"

        recommendations_and_alerts.append({
            "patient_id": pid,
            "patient_name": name,
            "alert_priority": alert_priority,
            "alert_color": alert_color,
            "grounded_recommendations": recommendations,
            "dashboard_ready_payload": {
                "patient_id": pid,
                "name": name,
                "priority": alert_priority,
                "color": alert_color,
                "reasons": patterns if patterns else ["Normal vitals"],
                "actions": recommendations
            }
        })

    return {
        "agent_name": "Agent 2 — Recommendation & Alert Agent",
        "processed_records": len(recommendations_and_alerts),
        "alerts_summary": recommendations_and_alerts
    }
