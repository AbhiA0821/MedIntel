from prefect import flow
from prefect_pipeline.tasks.data_health_tasks import (
    check_database_connection,
    verify_patient_vitals_counts,
    validate_vital_ranges
)
from prefect_pipeline.tasks.ml_tasks import (
    load_ml_model,
    run_vital_risk_inference
)
from prefect_pipeline.tasks.ai_agent_tasks import (
    run_patient_analysis_agent,
    run_recommendation_alert_agent
)

@flow(name="medintel_main_pipeline")
def medintel_pipeline() -> dict:
    """
    Main finite Prefect orchestration pipeline for MedIntel platform.
    Executes Data Health checks, ML Risk Inference, and AI Agent workflows (Agent 1 -> Agent 2).
    """
    print("=" * 65)
    print("STARTING MEDINTEL PREFECT ORCHESTRATION PIPELINE")
    print("=" * 65)

    # 1. Data Health Verification
    db_health = check_database_connection()
    vitals_counts = verify_patient_vitals_counts()
    range_check = validate_vital_ranges()

    # 2. ML Flow Execution
    model_metadata = load_ml_model()
    ml_results = run_vital_risk_inference(model_metadata)

    # 3. AI Agent Flow Execution
    agent_1_analysis = run_patient_analysis_agent(ml_results)
    agent_2_alerts = run_recommendation_alert_agent(agent_1_analysis)

    print("-" * 65)
    print(f"Pipeline Health: {db_health['status'].upper()}")
    print(f"ML Evaluated: {ml_results['evaluated_records']} records")
    print(f"Agent 1 Analyzed: {agent_1_analysis['analyzed_patients_count']} patients")
    print(f"Agent 2 Generated: {agent_2_alerts['processed_records']} alerts/recommendations")
    print("=" * 65)

    return {
        "pipeline_status": "SUCCESS",
        "health": {
            "db_status": db_health,
            "counts": vitals_counts,
            "range_check": range_check
        },
        "ml_inference": ml_results,
        "ai_agents": {
            "agent_1_output": agent_1_analysis,
            "agent_2_output": agent_2_alerts
        }
    }

if __name__ == "__main__":
    summary = medintel_pipeline()
    print("MedIntel main Prefect pipeline run completed successfully.")
