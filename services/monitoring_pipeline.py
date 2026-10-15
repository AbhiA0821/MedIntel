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

    # Spark starts only ONCE
    spark_start = time.monotonic()

    spark = create_spark_session()

    print(
        f"PySpark startup time: "
        f"{time.monotonic() - spark_start:.3f}s"
    )

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
            # STEP 1 - Generate + Store Raw Vitals
            # ==========================================

            generation_start = time.monotonic()

            print(
                "[1/5] Generating patient vital signs..."
            )

            new_vital_ids = (
                generate_and_store_vitals()
            )

            generation_time = (
                time.monotonic() -
                generation_start
            )

            print(
                f"TIMING | Raw generation + DuckDB: "
                f"{generation_time:.3f}s"
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

                preprocessing_start = time.monotonic()

                print(
                    "[2/5] Running PySpark preprocessing..."
                )

                processed_df = process_batch(
                    spark,
                    new_vital_ids
                )

                preprocessing_time = (
                    time.monotonic() -
                    preprocessing_start
                )

                print(
                    f"TIMING | PySpark + processed save: "
                    f"{preprocessing_time:.3f}s"
                )

                # ======================================
                # STEP 3 - ML Prediction
                # ======================================

                ml_start = time.monotonic()

                print(
                    "[3/5] ML prediction: "
                    "waiting for model integration."
                )

                ml_time = (
                    time.monotonic() -
                    ml_start
                )

                print(
                    f"TIMING | ML: "
                    f"{ml_time:.3f}s"
                )

                # ======================================
                # STEP 4 - Recommendation
                # ======================================

                recommendation_start = time.monotonic()

                print(
                    "[4/5] Recommendation engine: "
                    "waiting for integration."
                )

                recommendation_time = (
                    time.monotonic() -
                    recommendation_start
                )

                print(
                    f"TIMING | Recommendation: "
                    f"{recommendation_time:.3f}s"
                )

                # ======================================
                # STEP 5 - Alert
                # ======================================

                alert_start = time.monotonic()

                print(
                    "[5/5] Alert service: "
                    "waiting for integration."
                )

                alert_time = (
                    time.monotonic() -
                    alert_start
                )

                print(
                    f"TIMING | Alert: "
                    f"{alert_time:.3f}s"
                )

            # ==========================================
            # Total Cycle Timing
            # ==========================================

            elapsed = (
                time.monotonic() -
                cycle_start
            )

            print("-" * 65)

            print(
                f"TOTAL CYCLE TIME: "
                f"{elapsed:.3f}s"
            )

            remaining_time = max(
                0,
                MONITORING_INTERVAL_SECONDS - elapsed
            )

            if remaining_time > 0:

                print(
                    f"Waiting: "
                    f"{remaining_time:.3f}s"
                )

                print(
                    "Cycle completed within "
                    "5-second target."
                )

                time.sleep(
                    remaining_time
                )

            else:

                print(
                    f"TARGET EXCEEDED BY: "
                    f"{elapsed - MONITORING_INTERVAL_SECONDS:.3f}s"
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