from prefect import flow
from prefect_pipeline.tasks.ml_tasks import load_ml_model, run_vital_risk_inference
from prefect_pipeline.tasks.ai_agent_tasks import (
    run_patient_analysis_agent,
    run_recommendation_alert_agent
)

@flow(name="medintel_ai_analysis_flow")
def ai_analysis_flow() -> dict:
    """
    Finite flow orchestrating Agent 1 (Patient Analysis) and Agent 2 (Recommendation & Alert).
    """
    model_metadata = load_ml_model()
    ml_inference_results = run_vital_risk_inference(model_metadata)

    # Agent 1: Patient Analysis Agent
    agent_1_output = run_patient_analysis_agent(ml_inference_results)

    # Agent 2: Recommendation & Alert Agent
    agent_2_output = run_recommendation_alert_agent(agent_1_output)

    return {
        "flow": "medintel_ai_analysis_flow",
        "agent_1_output": agent_1_output,
        "agent_2_output": agent_2_output
    }

if __name__ == "__main__":
    result = ai_analysis_flow()
    print("AI Analysis Flow completed successfully:")
    print(f"Processed {result['agent_2_output']['processed_records']} patient records.")
