# 🏥 MedIntel – AI Healthcare Data Pipeline

MedIntel is an end-to-end AI-powered healthcare monitoring system that simulates real-time patient vital signs, processes healthcare data using PySpark, stores validated records in DuckDB, and provides intelligent health monitoring and recommendations.

> 🚧 **Project Status:** In Development

---

# 📌 Project Overview

MedIntel simulates continuous patient monitoring in a hospital environment. Patient vital signs are generated periodically, validated through a PySpark data pipeline, stored in DuckDB, analyzed using machine learning, and visualized through an interactive dashboard.

---

# 🏗️ System Architecture

```
Patient Simulator
        │
        ▼
PySpark Data Processing
        │
        ▼
DuckDB Database
        │
        ▼
Machine Learning Model
        │
        ▼
Reason Detection Engine
        │
        ▼
Recommendation Engine
        │
        ▼
Flask Dashboard
```

---

# 🚀 Features

## ✅ Completed

- DuckDB Database Design
- Patients Table
- VitalSigns Table
- Generated 100 Realistic Patients
- SQL Monitoring Queries
- Patient Dashboard (Initial Version)
- Reason Detection Engine
- Severity Classification Engine
- Recommendation Engine
- Patient Vital Signs Simulator
- Realistic Vital Sign Generation
  - Heart Rate
  - Blood Pressure
  - SpO₂
  - Temperature
  - Respiratory Rate

---

## 🚧 In Progress

- PySpark Data Validation Pipeline
- Live Patient Simulation
- Data Cleaning & Transformation

---

## 📅 Planned

- Random Forest Health Prediction
- Airflow Pipeline Automation
- Flask Web Dashboard
- Live Alerts
- Interactive Analytics
- Docker Deployment

---

# 🛠️ Technology Stack

| Category | Technologies |
|----------|--------------|
| Programming | Python |
| Data Processing | PySpark |
| Database | DuckDB |
| Machine Learning | Scikit-learn |
| Workflow | Apache Airflow |
| Dashboard | Flask, Plotly |
| Version Control | Git, GitHub |

---

# 📂 Project Structure

```
MedIntel/
│
├── database/
│   ├── medintel.duckdb
│   ├── schema.sql
│   ├── sample_data.sql
│   └── setup_database.py
│
├── patient_management/
│   └── generate_patients.py
│
├── simulator/
│   └── patient_simulator.py
│
├── monitoring/
│
├── dashboard/
│
├── airflow/
│
├── pyspark/
│
└── README.md
```

---

# 📊 Current Workflow

```
Generate 100 Patients
        │
        ▼
Generate Vital Signs
        │
        ▼
(PySpark Validation - In Progress)
        │
        ▼
Store Clean Data
        │
        ▼
ML Prediction
        │
        ▼
Recommendation Engine
        │
        ▼
Dashboard
```

---

# 🎯 Current Progress

- [x] Database Design
- [x] Patient Generation
- [x] Vital Sign Simulation
- [x] Recommendation Engine
- [x] Severity Detection
- [ ] PySpark Processing
- [ ] Live Simulator
- [ ] Machine Learning
- [ ] Airflow
- [ ] Flask Dashboard

---

# 👨‍💻 Author

**Abhishek Rajendrakumar Ainapure**

- GitHub: https://github.com/AbhiA0821

---

⭐ This project is being developed as a real-world AI + Data Engineering portfolio project to demonstrate healthcare data processing, scalable data pipelines, and intelligent patient monitoring.