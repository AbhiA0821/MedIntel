from prefect import flow
from prefect_pipeline.tasks.ml_tasks import (
    load_ml_model,
    run_vital_risk_inference
)

@flow(name="medintel_ml_flow")
def ml_flow() -> dict:
    """
    Finite flow for ML model loading and batch risk inference.
    """
    model_metadata = load_ml_model()
    inference_results = run_vital_risk_inference(model_metadata)

    return {
        "flow": "medintel_ml_flow",
        "model_metadata": model_metadata,
        "inference_results": inference_results
    }

if __name__ == "__main__":
    result = ml_flow()
    print("ML Flow completed successfully:")
    print(result)
