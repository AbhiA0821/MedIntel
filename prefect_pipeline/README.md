# MedIntel Prefect Orchestration System

This directory contains the **Prefect 3.0** workflow orchestration layer for the MedIntel AI Healthcare Patient Monitoring platform, fully replacing Apache Airflow.

## Conceptual Architecture

```
                    PREFECT (Workflow Orchestrator)
                                   │
          ┌────────────────────────┼────────────────────────┐
          ↓                        ↓                        ↓
   Data Health Flow             ML Flow               AI Flow (Agents 1 & 2)
          │                        │                        │
          └────────────────────────┼────────────────────────┘
                                   ↓
                                DuckDB

-------------------------------------------------------------------------
Streaming Architecture (Independent & Event-Driven):
  Vital Generator -> Kafka Topic (medintel-vitals) -> PySpark Structured Streaming -> DuckDB
```

Prefect orchestrates **finite, deterministic batch operations** (health checks, ML model inference, AI agent analyses) without blocking or running infinite `while True` monitoring loops.

## Directory Structure

```
prefect/
├── README.md
├── tasks/
│   ├── data_health_tasks.py    # Database connectivity & vital count validation
│   ├── ml_tasks.py             # ML model load & risk score inference tasks
│   └── ai_agent_tasks.py       # Agent 1 (Analysis) & Agent 2 (Recommendation & Alert) tasks
└── flows/
    ├── health_check_flow.py    # Data health check flow
    ├── ml_flow.py              # ML risk inference flow
    ├── ai_analysis_flow.py     # AI agent analysis & recommendation flow
    └── medintel_pipeline.py    # Main composite orchestration pipeline
```

## Running Flows Locally

No Docker or PostgreSQL stack is required to run Prefect flows during development.

### 1. Data Health Check Flow
```bash
python -m prefect.flows.health_check_flow
```

### 2. ML Risk Inference Flow
```bash
python -m prefect.flows.ml_flow
```

### 3. AI Analysis Flow (Agent 1 & Agent 2)
```bash
python -m prefect.flows.ai_analysis_flow
```

### 4. Main MedIntel Pipeline
```bash
python -m prefect.flows.medintel_pipeline
```
