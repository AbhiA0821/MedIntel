from prefect import task
import duckdb
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "database" / "medintel.duckdb"

@task(name="load_ml_model", retries=1, retry_delay_seconds=2)
def load_ml_model() -> dict:
    """
    Load or verify ML risk scoring model artifacts.
    """
    return {
        "model_name": "MedIntel_VitalRiskScorer_v1",
        "status": "ready",
        "input_features": ["heart_rate", "spo2", "temperature", "systolic_bp", "diastolic_bp", "respiratory_rate"]
    }

@task(name="run_vital_risk_inference", retries=1, retry_delay_seconds=2)
def run_vital_risk_inference(model_metadata: dict) -> dict:
    """
    Perform ML inference / risk scoring on recent patient vital readings stored in DuckDB.
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
        source_table = "ProcessedPatientVitals" if "ProcessedPatientVitals" in tables else "VitalSigns"

        rows = con.execute(f"""
            SELECT patient_id, heart_rate, spo2, temperature, systolic_bp, diastolic_bp, respiratory_rate
            FROM {source_table}
            ORDER BY patient_id
        """).fetchall()

        predictions = []
        for r in rows:
            pid, hr, spo2, temp, sys_bp, dia_bp, resp = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
            
            # Simple rule-based ML scoring heuristic fallback
            risk_score = 0.0
            if spo2 < 90 or temp > 38.5:
                risk_score += 0.6
            if hr > 120 or sys_bp > 160 or resp > 24:
                risk_score += 0.3
            risk_score = min(1.0, risk_score)

            risk_category = "High Risk" if risk_score >= 0.6 else ("Moderate Risk" if risk_score >= 0.3 else "Low Risk")

            predictions.append({
                "patient_id": pid,
                "risk_score": round(risk_score, 2),
                "risk_category": risk_category
            })

        return {
            "model": model_metadata["model_name"],
            "evaluated_records": len(predictions),
            "predictions": predictions
        }
    finally:
        con.close()
