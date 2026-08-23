# MEDINTEL — FINAL PRESENTATION DEMO RUNBOOK & OPERATIONAL MANUAL

This runbook provides exact operational startup procedures, test credential references, architecture mappings, and step-by-step demonstration workflows for the MedIntel AI Healthcare Monitoring Platform.

---

## 1. System Startup Procedures

Execute startup commands from the project root directory (`f:\Projects\MedIntel`).

### A. FastAPI Backend Service (Port 8000)
Starts the primary REST API service for patient vitals, live monitoring, pipeline metrics, and authentication.
```bash
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
- **Base URL**: `http://127.0.0.1:8000`
- **Interactive OpenAPI Docs**: `http://127.0.0.1:8000/docs`
- **Health Endpoint**: `http://127.0.0.1:8000/health`

### B. Flask Presentation Frontend (Port 5000)
Starts the Flask presentation server rendering dark-mode clinical dashboards and proxying `/api/v1/*` requests to FastAPI.
```bash
.venv\Scripts\python.exe frontend/app.py
```
- **Application URL**: `http://127.0.0.1:5000`
- **Login Route**: `http://127.0.0.1:5000/login`

### C. Independent Background Simulator
Generates realistic patient vital signs every 3 seconds, evaluates clinical safety thresholds, and updates DuckDB + Kafka.
```bash
.venv\Scripts\python.exe simulator/simulator_runner.py
```
*(Alternatively, click **▶ START SIMULATOR** on the left panel of the web dashboard).*

---

## 2. Configured Test Credentials

| Role | Username / Email | Specialty | Access Scope |
|---|---|---|---|
| **Doctor** | `dr.rahul@medintel.org` | Cardiology | Full Dashboard, Live Vitals, Critical Alerts, Web Push Notifications, Patient Management, Simulator Controls |
| **Doctor** | `dr.priya@medintel.org` | Neurology | Full Dashboard, Specialty Routing, Critical Alerts, Web Push Notifications |
| **Doctor** | `dr.amit@medintel.org` | General Medicine | Full Dashboard, Specialty Routing, Critical Alerts, Web Push Notifications |
| **Receptionist** | `reception@medintel.org` | Admissions | Live Patient Monitoring, Patient Directory, Add/Delete Patient CRUD (Doctor Push controls hidden) |

---

## 3. End-to-End Live Presentation Sequence

Follow this exact 14-step demonstration flow for live presentations:

1. **System Initialization**: Confirm FastAPI (`http://127.0.0.1:8000/health`) and Flask (`http://127.0.0.1:5000`) are active.
2. **Doctor Login**: Open `http://127.0.0.1:5000/login`, select **Doctor**, enter `dr.rahul@medintel.org`, click **Login to Command Center**.
3. **Dashboard Overview**: Demonstrate the 6 top KPI summary cards (Total Patients: 100, Critical: 8, Moderate, Low Risk, Total Records, Last Update).
4. **Simulator Controls**: Click **▶ START SIMULATOR** in the left sidebar. Observe the status pill turn green (**RUNNING**).
5. **Live Vital Streaming**: Highlight the patient table updating every 3 seconds. Show gradual vital variations for normal patients (e.g. HR: `70 → 72 → 73 → 74 bpm`).
6. **Controlled Critical Patients**: Demonstrate that exactly 8 controlled patients (`101, 102, 103, 104, 105, 106, 107, 108`) remain Critical every cycle.
7. **Critical Alerts Panel**: Explain right-hand Critical Patients panel showing bulleted clinical reasons (e.g. *Hypoxia*, *Pyrexia*) and Agent 2 grounded recommendations.
8. **Specialty Routing**: Highlight automatic routing of cardiac patients to *Dr. Rahul Sharma*, neurological to *Dr. Priya Patel*, and general medicine to *Dr. Amit Verma*.
9. **Doctor Push Notification**: Click the **Push Notifications ENABLED** badge to trigger browser Web Push notification simulation.
10. **View All Critical Alerts**: Click **View All** to navigate to `/critical_alerts`. Confirm all 8 active critical alerts render without truncation.
11. **Patient Slide-Over Drawer**: Click any patient row in the table to open the detailed vital inspection drawer.
12. **Patient Management (Add)**: Click **+ Add Patient**, enter test details (`First Name: Test`, `Last Name: Patient`, `Age: 30`, `Ward: ICU`), click **Save Patient**. Confirm patient is created in DuckDB and appears immediately in the table.
13. **Patient Management (Delete)**: Click **🗑️ Delete Patient**, select `Test Patient`, review the confirmation dialog, click **Confirm Delete**. Confirm instant removal from DB and UI.
14. **Receptionist Role Security**: Click **Logout**, log in as **Receptionist** (`reception@medintel.org`). Demonstrate that Doctor Web Push controls are hidden while monitoring remain accessible.

---

## 4. System Architecture Summary

```text
Patient Simulator (3s Cycle)
        │
        ├──► Kafka Broker ('medintel-vitals' topic)
        │
        ├──► DuckDB Database ('medintel.duckdb')
        │       │
        │       ▼
        ├──► FastAPI Backend (Port 8000)
        │       │
        │       ▼
        └──► Flask Frontend (Port 5000)
                │
                ▼
        Live Clinical Command Dashboard
```

---

## 5. Troubleshooting & Operations

- **DuckDB File Lock**: Ensure only one process opens `medintel.duckdb` in read/write mode. ProcessSharedDuckDBConnection handle prevents lock contention within process threads.
- **Port Conflict (8000/5000)**: If ports 8000 or 5000 are in use, terminate orphan Python processes or run `netstat -ano | findstr :8000`.
- **FastAPI Disconnection**: If FastAPI stops, Flask proxy returns a graceful 502 Bad Gateway error banner rather than crashing the client. Restarting FastAPI restores dashboard live polling automatically.
