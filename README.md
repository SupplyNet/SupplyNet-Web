# SupplyNet — Autonomous Fleet Route & Disruption Intelligence

SupplyNet is an enterprise logistics and autonomous fleet management platform featuring multi-objective route optimization, live GPS telematics simulation, disruption detection, and dynamic rerouting.

---

## 📖 Architecture & Telematics Guide
For in-depth documentation on how the FastAPI simulation engine works, how the Flask routes synchronize with MySQL, and how the Google Maps tracking UI operates, please see:
- 📄 **[GPS_SIMULATION_ENGINE.md](GPS_SIMULATION_ENGINE.md)** — In-depth physics, geodesic formulas, FastAPI simulator internals, and endpoint documentation.
- 📄 **[SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)** — Complete full-stack system architecture, data models, and sequence workflows.

---

## 🚀 Running the Project Locally

### 1. Start the FastAPI Simulation Server
```bash
uvicorn main3:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Start the Flask Web Application
```bash
python run.py
```
Visit `http://localhost:5000` in your browser.



Set-Location "C:\Users\priya\Downloads\SupplyNet-Web" 