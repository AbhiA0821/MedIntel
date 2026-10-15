# MEDINTEL Backend Multi-Doctor Routing & Voice Queue Walkthrough

## Summary of Completed Implementation (Phases 1–7)

Backend multi-doctor isolation, authoritative specialty routing, 4 independent voice queues, receptionist hospital-wide alerts, and doctor-specific FCM routing have been successfully implemented and verified across all automated test suites.

---

### Files Changed

1. [`services/alert_router.py`](file:///f:/Projects/MedIntel/services/alert_router.py):
   - Defined `AUTHORITATIVE_DOCTORS` registry with authoritative doctor details, specialty assignments, emails, and extensions:
     - `DOC001`: Dr. Viraj Patil (`dr.viraj@medintel.org`, CARDIOLOGY)
     - `DOC002`: Dr. Smarath Pawar (`dr.smarath@medintel.org`, PULMONOLOGY)
     - `DOC003`: Dr. Shreya Sutar (`dr.shreya@medintel.org`, GENERAL MEDICINE)
     - `REC001`: Reception Desk (`reception@medintel.org`, HOSPITAL ADMISSIONS, role="RECEPTIONIST")
   - Updated `SPECIALTY_TO_DOCTOR` and `SPECIALTY_MAP` to strictly map specialties to these authoritative doctors.
   - Updated `route_alert()` to prioritize authoritative specialty from the patient record rather than inferring from vital values.

2. [`database/schema.sql`](file:///f:/Projects/MedIntel/database/schema.sql) & `database/medintel.duckdb`:
   - Added `specialty VARCHAR` column to `Patients` table.
   - Initialized database schema with `AuthorizedDoctors` and `DoctorDevices`.

3. [`scripts/seed_demo_population.py`](file:///f:/Projects/MedIntel/scripts/seed_demo_population.py):
   - Seeded controlled 11-patient demo population (P101–P111):
     - **Cardiology (3 patients)**: P101 (CRITICAL), P102 (CRITICAL), P103 (MODERATE)
     - **Pulmonology (6 patients)**: P104 (CRITICAL), P105 (CRITICAL), P106 (CRITICAL), P107 (MODERATE), P108 (LOW), P109 (LOW)
     - **General Medicine (2 patients)**: P110 (CRITICAL), P111 (LOW)
   - Total initial critical patients: 6 (within target range of 6–8).
   - Seeded 4 staff records in `AuthorizedDoctors` and 22 baseline vitals.

4. [`database/monitoring_queries.py`](file:///f:/Projects/MedIntel/database/monitoring_queries.py):
   - `get_critical_patients()`: selects `p.specialty`.
   - `get_live_monitoring_state(con, doctor_id, specialty)`: applies specialty filtering when `doctor_id` or `specialty` is provided. Receptionist (`REC001`) and non-filtered calls retrieve all 11 patients.
   - `get_patient_by_id(patient_id)`: retrieves full patient profile and latest vitals.
   - `get_active_alerts(con, doctor_id, specialty)` & `get_alert_history(limit, con, doctor_id, specialty)`: filter alerts by specialty when requested.
   - `register_doctor_device()`: deletes existing token/device_id records before insert to prevent primary key constraint collisions.
   - `record_or_update_critical_alert()`: generates unique millisecond-precision alert IDs (`ALT-P{pid}-{timestamp_ms}`).

5. [`services/voice/alert_voice.py`](file:///f:/Projects/MedIntel/services/voice/alert_voice.py):
   - Implemented 4 independent logical voice queues: `CARDIOLOGY`, `PULMONOLOGY`, `GENERAL_MEDICINE`, `RECEPTIONIST`.
   - Each queue maintains an independent `PriorityQueue`, dedicated background worker thread, isolated `_DESTINATION_LATEST` dictionary, and isolated deduplication set `_SPOKEN_ALERT_IDS`.
   - Critical alerts dispatch in parallel to the assigned doctor's specialty queue and to the hospital-wide `RECEPTIONIST` queue.
   - Added `get_latest_voice_alert(destination)` supporting destination-keyed polling.

6. [`services/notification_service.py`](file:///f:/Projects/MedIntel/services/notification_service.py):
   - Enriched doctor FCM data payload with `doctor_id`, `specialty`, `patient_id`, `ward`, `bed`, `abnormal_vital`, `value`, `unit`.
   - Added `send_receptionist_push()` routing critical alerts to `REC001` with hospital-wide notifications.

7. [`backend/main.py`](file:///f:/Projects/MedIntel/backend/main.py):
   - Added `doctor_id` and `specialty` query parameters to `/api/v1/live_vitals`, `/api/v1/patients`, `/api/v1/alerts/active`, `/api/v1/alerts/history`.
   - Added `GET /api/v1/patients/{patient_id}` enforcing cross-doctor 403 Forbidden checks.
   - Added `destination` parameter to `GET /api/v1/alerts/voice/latest`.
   - Updated `/api/v1/auth/login` and `/api/v1/auth/register_device` default doctor fallbacks to match authoritative doctors.

8. [`simulator/patient_simulator.py`](file:///f:/Projects/MedIntel/simulator/patient_simulator.py):
   - Initialized `TARGET_CRITICAL_PIDS` to match the demo population baseline `{101, 102, 104, 105, 106, 110}`.
   - Updated `process_background_alert_pipeline()` to resolve specialty directly from patient record.

9. [`frontend/app.py`](file:///f:/Projects/MedIntel/frontend/app.py) & Templates:
   - `proxy_fastapi`: automatically injects logged-in `doctor_id` and `specialty` from session into proxied backend calls.
   - `login.html`: updated default credentials and added one-click quick selectors for Dr. Viraj, Dr. Smarath, and Dr. Shreya.
   - `doctor_dashboard.html`: header displays dynamic specialty command title and voice alert polling passes `destination={{ user.specialty }}`.

---

### Test Verification Results

| Test Suite | Purpose | Tests Ran | Result |
| :--- | :--- | :--- | :--- |
| `tests/test_multi_doctor_routing.py` | Targeted tests for authoritative registry, demo population, specialty isolation, 403 authorization, 4 voice queues, deduplication, recovery/re-critical, FCM payload | 10 | **10 / 10 PASSED** (100%) |
| `tests/test_fcm_voice_alerts.py` | 20-point comprehensive alert & voice lifecycle suite | 20 | **20 / 20 PASSED** (100%) |
| `tests/test_demo_scenarios.py` | Core demo scenarios & deterministic severity rules | 4 | **4 / 4 PASSED** (100%) |
| `tests/test_llm_rag.py` | Agent 2 clinical reasoning, LLM explanation & RAG pipeline | 10 | **10 / 10 PASSED** (100%) |
| `scripts/verify_live_backend.py` | Live HTTP endpoint verification across all Phase 1–7 endpoints | 19 | **19 / 19 PASSED** (100%) |

**Total Automated Tests Passed**: **63 / 63 tests passing (0 failures)**.

---

### Risks & Conflicts
- **None**. Agent 1 (`services/severity_engine.py`) was not modified and remains immutable.
- Existing DuckDB concurrency constraints were respected without data loss.
- No Docker was introduced; no commits or pushes were created.
