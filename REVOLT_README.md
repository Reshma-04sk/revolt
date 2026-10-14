# ReVolt — AI-Powered Lithium-Ion Battery Reuse & Recycling Management Platform

> **"Give Every Battery a Second Life."**  
> *RMK ReVolt Hackathon Finalist Prototype*

---

## 1. Executive Summary

**ReVolt** is an end-to-end digital lifecycle and circular routing platform for spent and decommissioned lithium-ion batteries. It transitions used battery management from informal, hazardous scrap dumping to a structured, traceable, and safety-verified circular pipeline.

The platform triages every registered battery across **four verifiable pathways**:

| Pathway | Target Application | Health & Safety Criteria | Action Protocol |
| :--- | :--- | :--- | :--- |
| 🟢 **REUSE** | Stationary solar energy storage (BESS), UPS, light-duty backup | SoH ≥ 75%, cycles ≤ 1200, intact physical casing, normal voltage window | Capacity verification, second-life passport tagging, integration partner dispatch |
| 🔵 **REFURBISH** | Professional cell balancing, repacking, BMS restoration | SoH 60%–75%, or repairable terminal corrosion / low single-cell deviation | Certified lab diagnostic scan, active balancing, pack re-certification (UL 1974) |
| 🟡 **RECYCLE** | Closed-loop hydrometallurgical mineral extraction (Li, Co, Ni) | SoH < 60%, cycles > 1800, or casing gas swelling without active breach | Controlled 0V discharge, shredding, black mass hydrometallurgical refining |
| 🔴 **HAZARDOUS** | High-containment isolation & emergency neutralization | Severe pouch bulging, punctures, electrolyte leaks, thermal charring, or dangerous voltage | **Immediate physical quarantine**, non-flammable sand container, UN 3480 Hazmat transport |

> **Safety Notice:** *ReVolt serves as the intelligence, assessment, and logistics coordination platform. Physical cell disassembly, testing, refurbishing, and hydrometallurgical recycling are performed exclusively by authorized, certified facilities.*

---

## 2. Technology Stack & Architecture

- **Backend Framework:** FastAPI 0.115+ (Python 3.12/3.13) with asynchronous request handling.
- **Data Validation & Schemas:** Pydantic v2 with strict typing, `StrEnum` domains, and range validation.
- **Diagnostic Engine:** Explainable deterministic rule evaluation engine modeling chemistry-specific operating windows (NMC, LFP, LCO, LMO, NCA).
- **Persistence Layer:** Thread-safe, file-backed JSON repository (`revolt_data.json`) ensuring state survives server restarts while maintaining high-speed in-memory operations.
- **Frontend Architecture:** Clean Vanilla CSS & Modern JavaScript single-page application served directly by FastAPI. Zero heavy bundler dependencies.
- **Visual Design System:** Dark graphite shell (`#0A0F12`), deep forest-green accents, glassmorphic cards, accessible focus rings, and responsive grid layouts.
- **Geographic Mapping:** Leaflet.js with OpenStreetMap tiles for interactive facility discovery and route planning.
- **Environment & Package Management:** `uv` (Astral).

---

## 3. Core Functional Capabilities

### A. Executive Overview Dashboard
- Live KPI telemetry: Registered batteries, assessments completed, units awaiting collection, and landfill diversion tonnage.
- Circular pathway distribution breakdowns.
- Real-time Critical Safety Alert banner highlighting any quarantined hazardous batteries.
- Chronological audit activity stream.

### B. Validated Battery Registration
- Multi-chemistry support: NMC (3.7V), LFP (3.2V), LCO (3.7V), LMO (3.7V), NCA (3.6V), Other.
- Dynamic per-cell voltage guide and automatic State of Health (SoH) calculation.
- Rigorous validation against negative capacities, impossible voltages, and missing physical condition indicators.
- Instant reactive registration without page reload.

### C. Transparent AI Assessment Engine
- Chemistry-specific safety evaluation:
  - Critical under-voltage (< 2.0V NMC / < 1.8V LFP) flagged as dendrite short hazard.
  - Critical over-voltage (> 4.35V NMC / > 3.85V LFP) flagged as thermal runaway hazard.
  - Physical integrity checks (swelling, leaks, punctures, terminal corrosion).
- Defensible confidence scoring based on telemetry completeness (missing data is never assumed safe).
- Explicit next-step action checklists and safety limitation disclosures.

### D. Facility Locator & Simulated Logistics
- Verified facility directory covering hydrometallurgical refiners, second-life labs, and hazardous containment hubs.
- Interactive map pins with capability tags, operating hours, and contact details.
- Filtering by circular pathway and supported chemistries.
- Simulated collection and depot drop-off scheduling with unique booking references (`BK-YYYY-XXXX`).

### E. Digital Battery Passport & Lifecycle Traceability
- Unique digital asset ID (`REV-YYYY-XXXX`) and simulated QR Passport.
- Visual status stepper: `Registered` $\rightarrow$ `Assessed` $\rightarrow$ `Awaiting Collection` $\rightarrow$ `In Transit` $\rightarrow$ `Received at Facility` $\rightarrow$ `Processing` $\rightarrow$ `Completed`.
- State-machine validated status transitions preventing illegal lifecycle skips.
- Complete immutable audit event timeline with timestamps and actors.

### F. Quantified Impact Analytics
- Avoided CO₂ emissions modeled at ~73 kg CO₂e per kWh of second-life reuse.
- High-purity critical mineral recovery estimates (Lithium Carbonate Equivalent, Cobalt, Nickel in kg).
- Municipal landfill diversion weight (kg).
- Transparent documentation of LCA coefficients distinguishing measured telemetry from standardized estimates.

---

## 4. Local Execution & Quick Start

### Prerequisites
- Python 3.12+
- `uv` package manager (`curl -LsSf https://astral.sh/uv/install.ps1 | iex` on Windows)

### Commands

1. **Install Dependencies & Sync Virtual Environment:**
   ```bash
   uv sync
   ```

2. **Run Automated Test Suite (All 125 tests passing):**
   ```bash
   uv run pytest tests/unit/test_revolt_e2e.py
   ```

3. **Start the ReVolt Server:**
   ```bash
   uv run uvicorn src.apps.api.main:app --host 127.0.0.1 --port 8000 --reload
   ```

4. **Access the Applications:**
   - **Interactive Web Platform:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
   - **Interactive API Documentation (Swagger / OpenAPI):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 5. Automated Verification Results

| Test Category | Target Component | Results |
| :--- | :--- | :--- |
| **Safety Engine** | Undervoltage, severe swelling, thermal runaway detection | ✅ PASS (100% quarantine trigger) |
| **Pathway Rules** | SoH ≥ 75% $\rightarrow$ Reuse; SoH 60–75% $\rightarrow$ Refurbish; SoH < 60% $\rightarrow$ Recycle | ✅ PASS |
| **API Endpoints** | Battery CRUD, Assessment, Facilities, Scheduling, Lifecycle status | ✅ PASS |
| **State Machine** | Validated lifecycle transitions & illegal rollback rejection | ✅ PASS |
| **Static Assets** | HTML, CSS Design System, JavaScript Controller | ✅ PASS |
| **Type Safety** | Mypy strict type checking across all ReVolt modules | ✅ PASS (0 issues in 6 files) |
| **Linting** | Ruff linter & formatter (line length 100) | ✅ PASS (0 errors) |
| **Full Unit Suite** | Akesis baseline + ReVolt end-to-end acceptance tests | ✅ PASS (125/125 passing) |

---
*Created for the RMK ReVolt Hackathon 2026.*
