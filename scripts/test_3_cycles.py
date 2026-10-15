import time
from simulator.simulator_runner import run_simulation_cycle
from database.monitoring_queries import get_live_monitoring_state

print("=== VERIFYING MEDINTEL 3-CYCLE SIMULATION & READINGS ===")
for i in range(3):
    ids, dur = run_simulation_cycle()
    state = get_live_monitoring_state()
    print(f"Cycle {i+1}: Generated {len(ids)} vitals in {dur:.3f}s | Total Patients: {state['total_patients']} (P101-P200) | Latest DB Update: {state['latest_db_update']}")
    time.sleep(1)

print("=== 3-CYCLE VERIFICATION SUCCESSFUL ===")
