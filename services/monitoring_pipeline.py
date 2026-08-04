import time
from datetime import datetime

from simulator.simulator_runner import (
    generate_and_store_vitals
)

from pyspark_pipeline.preprocessing import (
    create_spark_session,
    process_batch
)


# =====================================================
# Configuration
# =====================================================

MONITORING_INTERVAL_SECONDS = 5


# =====================================================
# MedIntel Continuous Monitoring Service
# =====================================================

def run_monitoring_pipeline():

    print("=" * 65)
    print("MEDINTEL CONTINUOUS MONITORING PIPELINE")
    print("=" * 65)

    print(
        f"Target monitoring interval: "
        f"{MONITORING_INTERVAL_SECONDS} seconds"
    )

    print("Starting PySpark...")
    print("Press Ctrl+C to stop.")
    print("=" * 65)

    # IMPORTANT:
    # Spark starts ONCE and stays alive.
    spark = create_spark_session()

    cycle_number = 1

    try:

        while True:

            cycle_start = time.monotonic()

            print()
            print("=" * 65)

            print(
                f"CYCLE {cycle_number} | "
                f"{datetime.now().strftime('%H:%M:%S')}"
            )

            print("=" * 65)

            # ==========================================
            # STEP 1 - Generate Raw Vitals
            # ==========================================

            print(
                "[1/5] Generating patient vital signs..."
            )

            new_vital_ids = (
                generate_and_store_vitals()
            )

            if not new_vital_ids:

                print(
                    "No patient vital records generated."
                )

            else:

                print(
                    f"Generated batch size: "
                    f"{len(new_vital_ids)}"
                )

                # ======================================
                # STEP 2 - PySpark Preprocessing
                # ======================================

                print(
                    "[2/5] Running PySpark preprocessing..."
                )

                processed_df = process_batch(
                    spark,
                    new_vital_ids
                )

                # ======================================
                # STEP 3 - ML Prediction
                # ======================================

                print(
                    "[3/5] ML prediction: "
                    "waiting for model integration."
                )

                # Later:
                #
                # predictions = predict(
                #     processed_df
                # )

                # ======================================
                # STEP 4 - Recommendation
                # ======================================

                print(
                    "[4/5] Recommendation engine: "
                    "waiting for integration."
                )

                # Later:
                #
                # recommendations = (
                #     generate_recommendations(
                #         predictions
                #     )
                # )

                # ======================================
                # STEP 5 - Alert
                # ======================================

                print(
                    "[5/5] Alert service: "
                    "waiting for integration."
                )

                # Later:
                #
                # send_critical_alerts(
                #     predictions,
                #     recommendations
                # )

            # ==========================================
            # Timing
            # ==========================================

            elapsed = (
                time.monotonic() -
                cycle_start
            )

            print(
                f"Cycle processing time: "
                f"{elapsed:.2f} seconds"
            )

            remaining_time = max(
                0,
                MONITORING_INTERVAL_SECONDS - elapsed
            )

            if remaining_time > 0:

                print(
                    f"Next cycle in "
                    f"{remaining_time:.2f} seconds."
                )

                time.sleep(
                    remaining_time
                )

            else:

                print(
                    "Processing exceeded the "
                    "5-second target."
                )

                print(
                    "Starting next cycle immediately "
                    "without overlap."
                )

            cycle_number += 1

    except KeyboardInterrupt:

        print()
        print("=" * 65)
        print(
            "Stopping MedIntel monitoring pipeline..."
        )
        print("=" * 65)

    finally:

        print("Stopping PySpark...")

        spark.stop()

        print(
            "MedIntel monitoring pipeline stopped."
        )


# =====================================================
# Application Entry Point
# =====================================================

if __name__ == "__main__":

    run_monitoring_pipeline()