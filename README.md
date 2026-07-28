# 🏥 MedIntel - AI Healthcare Data Pipeline & Intelligent Patient Monitoring System

## 📌 Overview

MedIntel is an end-to-end AI-powered Healthcare Data Engineering project designed to monitor patient health using vital signs. The project combines Data Engineering, Machine Learning, and Web Technologies to process patient data, generate insights, and provide an intelligent healthcare dashboard.

The project is being developed collaboratively using GitHub with separate modules for Data Engineering, Machine Learning, and Flask Dashboard.

---

# 🚀 Current Project Status

## ✅ Completed

- Project Structure Setup
- DuckDB Database Design
- Patients Table
- Vital Signs Table
- Sample Data Generation
- Patient Vital Simulator
- PySpark ETL Pipeline
- Data Validation
- Patient Health Classification
- Healthcare Analytics
- ProcessedPatientVitals Table
- GitHub Repository Setup
- Team Collaboration using Git Branches

---

# 📂 Project Structure

```
MedIntel/
│
├── airflow/
│
├── backend/
│
├── database/
│   ├── medintel.duckdb
│   ├── schema.sql
│   └── sample_data.sql
│
├── docs/
│
├── ml_model/
│
├── pyspark_pipeline/
│
├── static/
│
├── templates/
│
├── app.py
│
├── requirements.txt
│
└── README.md
```

---

# 🛠 Tech Stack

### Data Engineering

- Python
- PySpark
- DuckDB
- Pandas

### Machine Learning

- Scikit-Learn
- Random Forest
- Logistic Regression
- Decision Tree
- XGBoost (Optional)

### Backend

- Flask

### Frontend

- HTML
- CSS
- Bootstrap
- Chart.js

### Workflow Automation

- Apache Airflow *(In Progress)*

### Deployment

- Docker *(Planned)*

---

# 🔄 ETL Pipeline

```
Patients Data
      │
      ▼
DuckDB Database
      │
      ▼
PySpark ETL Pipeline
      │
      ├── Data Validation
      ├── Vital Sign Processing
      ├── Patient Classification
      └── Healthcare Analytics
      │
      ▼
ProcessedPatientVitals
```

---

# 📊 Current Features

✅ Patient Database

✅ Vital Sign Generation

✅ Data Validation

✅ Patient Classification

- Normal
- Warning
- Critical

✅ Healthcare Analytics

✅ Processed Data Storage

---

# 🧠 Machine Learning Module (In Progress)

The ML module will predict patient health status using processed healthcare data.

### Planned Models

- Random Forest (Recommended)
- Logistic Regression
- Decision Tree
- XGBoost (Optional)

### Output

- Patient Risk Prediction
- Health Status Prediction

---

# 🌐 Flask Dashboard (In Progress)

The dashboard will provide real-time visualization of patient data.

### Planned Features

- Dashboard Overview
- Total Patients
- Normal Patients
- Warning Patients
- Critical Patients
- Patient Table
- Search & Filters
- Charts
- AI Insights

---

# ⚙️ Airflow (Upcoming)

Apache Airflow will automate:

- ETL Pipeline Execution
- Daily Data Processing
- Data Validation
- Database Updates

---

# 🐳 Docker (Upcoming)

The complete project will be containerized using Docker for easy deployment.

---

# 👥 Team Structure

## Data Engineering

Responsibilities:

- DuckDB
- PySpark ETL
- Data Validation
- Airflow
- Docker
- Final Integration

---

## Machine Learning

Responsibilities:

- Data Preprocessing
- Model Training
- Model Evaluation
- Prediction Module

---

## Flask Development

Responsibilities:

- Flask Backend
- HTML/CSS
- Bootstrap UI
- Dashboard Development
- Charts
- Database Integration

---

# 🌿 Git Workflow

```
main
│
├── ml-model
│
└── flask-dashboard
```

- `main` → Stable project
- `ml-model` → Machine Learning development
- `flask-dashboard` → Dashboard development

---

# 🎯 Project Roadmap

## Phase 1 ✅

- Database Design
- ETL Pipeline
- Data Validation
- Patient Classification
- Analytics

## Phase 2 🚧

- Apache Airflow

## Phase 3 🚧

- Machine Learning Integration

## Phase 4 🚧

- Flask Dashboard

## Phase 5 🚧

- Docker Deployment

---

# 📈 Future Enhancements

- AI Health Recommendations
- LLM Integration
- Live Patient Monitoring
- Automated ETL Scheduling
- Docker Deployment
- Cloud Deployment

---

# 👨‍💻 Developed By

**Abhishek Rajendrakumar Ainapure**

B.Tech Artificial Intelligence & Data Science

Data Engineering | Machine Learning | AI

---

## ⭐ If you found this project interesting, don't forget to star the repository!