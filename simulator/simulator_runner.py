import sys
import time
from pathlib import Path

# Ensure project root is on sys.path for robust module resolution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import get_connection
from database.monitoring_queries import update_pipeline_status_metrics, get_live_update_interval
from simulator.patient_simulator import generate_and_store_vitals, process_background_alert_pipeline

_api_server_thread = None


def run_simulation_cycle():
    """Executes a single end-to-end background simulation cycle with timing metrics."""
    con = get_connection()
    t0 = time.monotonic()

    t_gen0 = time.monotonic()
    new_ids = generate_and_store_vitals()
    t_gen = time.monotonic() - t_gen0

    t_pipe0 = time.monotonic()
    process_background_alert_pipeline(con=con)
    t_pipe = time.monotonic() - t_pipe0

    cycle_dur = time.monotonic() - t0
    print(f"[TIMING BREAKDOWN] Raw Vitals Gen: {t_gen:.3f}s | Alert Pipeline: {t_pipe:.3f}s | Total Cycle: {cycle_dur:.3f}s")

    update_pipeline_status_metrics(status="RUNNING", cycle_duration=cycle_dur, con=con)
    return new_ids, cycle_dur


def _run_uvicorn_server(server):
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())
    except Exception as e:
        print(f"[UVICORN ERROR] {e}", flush=True)


def start_in_process_api_server(host="127.0.0.1", port=8000):
    """Starts the FastAPI monitoring endpoint server in a daemon thread inside the simulator process."""
    global _api_server_thread
    if _api_server_thread is not None and _api_server_thread.is_alive():
        return

    import threading
    import uvicorn
    from backend.main import app

    config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    t = threading.Thread(target=_run_uvicorn_server, args=(server,), daemon=True)
    t.start()
    _api_server_thread = t
    print(f"[SIMULATOR MANAGER] In-process API server active on http://{host}:{port}")


def run_continuous_simulator_loop():
    """Independent continuous simulator loop for Layer 1 Background Pipeline."""
    start_in_process_api_server()

    print("=" * 65)
    print("MEDINTEL INDEPENDENT BACKGROUND SIMULATOR RUNNER")
    print("Layer 1 Pipeline: Patients -> Vitals -> DuckDB -> Alerts -> FCM")
    print("=" * 65)

    update_pipeline_status_metrics(status="RUNNING", cycle_duration=0.0)

    try:
        cycle_count = 1
        while True:
            interval = get_live_update_interval()
            new_ids, cycle_dur = run_simulation_cycle()

            if cycle_dur > interval:
                print(f"[SIMULATOR WARNING] Cycle {cycle_count}: Exceeded target interval! Duration: {cycle_dur:.3f}s > Target: {interval}s")
            else:
                print(f"[SIMULATOR] Cycle {cycle_count}: Generated {len(new_ids)} vitals in {cycle_dur:.3f}s (Interval target: {interval}s)")

            remaining_sleep = max(0.1, interval - cycle_dur)
            time.sleep(remaining_sleep)
            cycle_count += 1
    except KeyboardInterrupt:
        print("\n[SIMULATOR] Stopped by user.")
        update_pipeline_status_metrics(status="IDLE", cycle_duration=0.0)
    except Exception as e:
        print(f"\n[SIMULATOR ERROR] Loop crashed: {e}")
        update_pipeline_status_metrics(status="IDLE", cycle_duration=0.0)


if __name__ == "__main__":
    run_continuous_simulator_loop()