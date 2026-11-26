"""
Edge Application Server - Flask Edge Gateway
Project: Containerizing an Edge Application with Docker

This application acts as a localized Edge Gateway node. It:
1. Ingests raw telemetry streams from IoT sensor nodes via REST API.
2. Performs local, low-latency data filtering, statistical aggregation, and anomaly detection.
3. Detects abnormal conditions (e.g., Temperature >= 35.0°C) locally without cloud latency.
4. Serves an operational Web Dashboard for real-time Edge monitoring.
"""

import os
import sys
import time
import random
import threading
from datetime import datetime
from collections import deque
from flask import Flask, request, jsonify, render_template

# ==============================================================================
# Configuration & State Initialization
# ==============================================================================

app = Flask(__name__)

# Configuration parameters
CONTAINER_NAME = os.environ.get("EDGE_DEVICE_NAME", "edge-app")
PORT = int(os.environ.get("PORT", 5000))
DEFAULT_THRESHOLD = float(os.environ.get("TEMPERATURE_THRESHOLD", 35.0))

# Operational Data Storage (In-memory bounded queues for Edge performance)
MAX_HISTORY_LENGTH = 50
MAX_ALERT_LENGTH = 30

telemetry_history = deque(maxlen=MAX_HISTORY_LENGTH)
alert_history = deque(maxlen=MAX_ALERT_LENGTH)
data_lock = threading.Lock()

# Aggregate statistics
system_stats = {
    "total_readings": 0,
    "alert_count": 0,
    "current_temperature": None,
    "current_humidity": None,
    "min_temperature": None,
    "max_temperature": None,
    "avg_temperature": 0.0,
    "temperature_threshold": DEFAULT_THRESHOLD,
    "temp_sum": 0.0,
    "last_updated": None
}

# Edge node operational metadata
start_timestamp = time.time()
simulation_active = False
simulation_thread = None
simulation_interval = 2.0  # seconds between simulated ticks


def is_running_in_docker():
    """Detect whether this application is executing inside a Docker container."""
    if os.environ.get("DOCKER_CONTAINER") == "true":
        return True
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "rt") as f:
            return "docker" in f.read() or "kubepods" in f.read()
    except Exception:
        return False


# ==============================================================================
# Edge Processing Logic (Local Anomaly Detection & Statistics)
# ==============================================================================

def process_sensor_reading(data):
    """
    Process raw IoT telemetry locally at the Edge layer.
    - Validates payload
    - Computes running statistics
    - Identifies threshold breaches (< 35°C NORMAL, >= 35°C HIGH TEMP ALERT)
    - Records alert events locally
    """
    global system_stats

    # Extract & sanitize fields
    device_id = str(data.get("device_id", "unknown_sensor"))
    try:
        temperature = round(float(data.get("temperature", 0.0)), 2)
    except (ValueError, TypeError):
        temperature = 0.0

    try:
        humidity = round(float(data.get("humidity", 0.0)), 1)
    except (ValueError, TypeError):
        humidity = 0.0

    timestamp = data.get("timestamp")
    if not timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    threshold = system_stats["temperature_threshold"]

    # --- Edge Decision Rule: Threshold Comparison ---
    if temperature >= threshold:
        status = "HIGH TEMPERATURE ALERT"
        is_alert = True
        status_level = "danger"
        message = f"Warning: Sensor {device_id} reported {temperature}°C, exceeding threshold of {threshold}°C!"
    else:
        status = "NORMAL"
        is_alert = False
        status_level = "success"
        message = f"Nominal conditions: {temperature}°C is within acceptable operating limits."

    record = {
        "device_id": device_id,
        "temperature": temperature,
        "humidity": humidity,
        "timestamp": timestamp,
        "status": status,
        "is_alert": is_alert,
        "status_level": status_level,
        "message": message,
        "edge_processed_at": datetime.now().strftime("%H:%M:%S.%f")[:-3]
    }

    # Thread-safe update of statistics and storage
    with data_lock:
        telemetry_history.append(record)
        system_stats["total_readings"] += 1
        system_stats["current_temperature"] = temperature
        system_stats["current_humidity"] = humidity
        system_stats["last_updated"] = timestamp

        # Statistics computation
        if system_stats["min_temperature"] is None or temperature < system_stats["min_temperature"]:
            system_stats["min_temperature"] = temperature
        if system_stats["max_temperature"] is None or temperature > system_stats["max_temperature"]:
            system_stats["max_temperature"] = temperature

        system_stats["temp_sum"] += temperature
        system_stats["avg_temperature"] = round(
            system_stats["temp_sum"] / system_stats["total_readings"], 2
        )

        # Alert logging
        if is_alert:
            system_stats["alert_count"] += 1
            alert_history.appendleft({
                "timestamp": timestamp,
                "device_id": device_id,
                "temperature": temperature,
                "threshold": threshold,
                "message": message
            })

    return record


# ==============================================================================
# In-App Simulation Worker (Runs on-demand for UI-driven demos)
# ==============================================================================

def simulation_worker():
    """Background worker generating real-time sensor telemetries."""
    global simulation_active
    sensor_ids = ["sensor_01", "sensor_02", "sensor_03"]

    print("[Edge Simulator Worker] Background telemetry generation thread started.")
    while simulation_active:
        device_id = random.choice(sensor_ids)

        # 85% normal temperature (26.0 - 33.5°C), 15% spontaneous spike (35.5 - 41.0°C)
        if random.random() < 0.15:
            temp = round(random.uniform(35.5, 41.5), 2)
            hum = round(random.uniform(68.0, 88.0), 1)
        else:
            temp = round(random.uniform(26.0, 33.8), 2)
            hum = round(random.uniform(48.0, 68.0), 1)

        payload = {
            "device_id": device_id,
            "temperature": temp,
            "humidity": hum,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        process_sensor_reading(payload)
        time.sleep(simulation_interval)

    print("[Edge Simulator Worker] Background telemetry generation thread stopped.")


# ==============================================================================
# Web Dashboard & REST API Routes
# ==============================================================================

@app.route("/")
def index():
    """Serve the Edge Computing Web Dashboard."""
    return render_template("index.html")


@app.route("/api/sensor", methods=["POST"])
def receive_sensor_data():
    """
    POST /api/sensor
    Receives sensor data payload:
    {
        "device_id": "sensor_01",
        "temperature": 32.5,
        "humidity": 65,
        "timestamp": "2026-09-24 13:00:00"
    }
    """
    if not request.is_json:
        return jsonify({
            "status": "error",
            "message": "Invalid payload: Request body must be valid application/json"
        }), 400

    payload = request.get_json()
    if not payload:
        return jsonify({
            "status": "error",
            "message": "Empty JSON payload"
        }), 400

    processed_record = process_sensor_reading(payload)
    return jsonify({
        "status": "success",
        "layer": "Edge Layer (Local Processing)",
        "result": processed_record
    }), 201


@app.route("/api/data", methods=["GET"])
def get_recent_data():
    """
    GET /api/data
    Returns recent sensor readings in chronological order for charting and display.
    """
    with data_lock:
        data_list = list(telemetry_history)

    return jsonify({
        "status": "success",
        "count": len(data_list),
        "data": data_list
    })


@app.route("/api/statistics", methods=["GET"])
def get_statistics():
    """
    GET /api/statistics
    Returns aggregated metrics: current, average, minimum, maximum temperature, count & alerts.
    """
    with data_lock:
        stats_copy = dict(system_stats)

    return jsonify({
        "status": "success",
        "layer": "Edge Layer (Aggregations)",
        "statistics": stats_copy
    })


@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    """
    GET /api/alerts
    Returns recent alert events detected locally at the Edge.
    """
    with data_lock:
        alerts_copy = list(alert_history)

    return jsonify({
        "status": "success",
        "count": len(alerts_copy),
        "alerts": alerts_copy
    })


@app.route("/api/status", methods=["GET"])
def get_edge_status():
    """
    GET /api/status
    Returns the operational health, Docker status, and runtime environment of the Edge node.
    """
    uptime_seconds = int(time.time() - start_timestamp)
    running_in_docker = is_running_in_docker()

    return jsonify({
        "status": "ONLINE",
        "container_name": CONTAINER_NAME,
        "environment": "Docker Container" if running_in_docker else "Host System (Simulated Edge Node)",
        "is_docker": running_in_docker,
        "port": PORT,
        "processing_location": "Edge (Local Gateway)",
        "uptime_seconds": uptime_seconds,
        "simulation_running": simulation_active,
        "threshold": system_stats["temperature_threshold"],
        "total_readings": system_stats["total_readings"],
        "total_alerts": system_stats["alert_count"]
    })


# --- Simulation Control Endpoints for Interactive Demonstration ---

@app.route("/api/simulation/start", methods=["POST"])
def start_simulation():
    """Start automated simulated sensor telemetry generator."""
    global simulation_active, simulation_thread
    if not simulation_active:
        simulation_active = True
        simulation_thread = threading.Thread(target=simulation_worker, daemon=True)
        simulation_thread.start()
        return jsonify({"status": "success", "message": "Simulation started", "running": True})
    return jsonify({"status": "info", "message": "Simulation is already active", "running": True})


@app.route("/api/simulation/stop", methods=["POST"])
def stop_simulation():
    """Stop automated simulated sensor telemetry generator."""
    global simulation_active
    simulation_active = False
    return jsonify({"status": "success", "message": "Simulation stopped", "running": False})


@app.route("/api/simulation/spike", methods=["POST"])
def inject_temperature_spike():
    """
    Generate an immediate high-temperature reading (e.g., 38.0°C - 42.0°C)
    to demonstrate local anomaly detection during presentations.
    """
    spike_temp = round(random.uniform(37.5, 42.5), 2)
    spike_hum = round(random.uniform(70.0, 92.0), 1)
    payload = {
        "device_id": "sensor_01",
        "temperature": spike_temp,
        "humidity": spike_hum,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    processed = process_sensor_reading(payload)
    return jsonify({
        "status": "success",
        "message": f"High temperature anomaly injected ({spike_temp}°C)",
        "result": processed
    })


@app.route("/api/clear", methods=["POST"])
def clear_data():
    """Reset data queues and statistics for a fresh demonstration run."""
    global system_stats
    with data_lock:
        telemetry_history.clear()
        alert_history.clear()
        threshold = system_stats["temperature_threshold"]
        system_stats = {
            "total_readings": 0,
            "alert_count": 0,
            "current_temperature": None,
            "current_humidity": None,
            "min_temperature": None,
            "max_temperature": None,
            "avg_temperature": 0.0,
            "temperature_threshold": threshold,
            "temp_sum": 0.0,
            "last_updated": None
        }
    return jsonify({"status": "success", "message": "Edge storage and statistics reset"})


@app.route("/api/threshold", methods=["POST"])
def set_threshold():
    """Configure the alert threshold value dynamically."""
    global system_stats
    data = request.get_json(silent=True) or {}
    new_threshold = data.get("threshold")
    try:
        new_threshold = float(new_threshold)
        with data_lock:
            system_stats["temperature_threshold"] = new_threshold
        return jsonify({"status": "success", "threshold": new_threshold})
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid threshold value"}), 400


# ==============================================================================
# Entry Point
# ==============================================================================

def is_port_in_use(port):
    """Check if a port is currently listening on localhost."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0

if __name__ == "__main__":
    # Check if target port is already occupied by another running application
    if is_port_in_use(PORT):
        fallback_port = 5050
        print("\n" + "!" * 72)
        print(f" [PORT CONFLICT DETECTED]")
        print(f" Port {PORT} is already occupied by another running app (e.g. SmartMirror).")
        print(f" To free port {PORT}, you can run in PowerShell:")
        print(f"   Stop-Process -Id (Get-NetTCPConnection -LocalPort {PORT}).OwningProcess -Force")
        print(f" [AUTO-SWITCHING] Starting Edge Gateway on free port {fallback_port} instead!")
        print(f" Open Dashboard at: http://localhost:{fallback_port}")
        print("!" * 72 + "\n")
        PORT = fallback_port

    print("=" * 70)
    print("  Containerizing an Edge Application with Docker")
    print("  Edge Gateway Node: Initializing...")
    print(f"  Containerized Environment: {is_running_in_docker()}")
    print(f"  Active URL: http://localhost:{PORT}")
    print(f"  Default Alert Threshold: >= {DEFAULT_THRESHOLD}°C")
    print("=" * 70)

    app.run(host="0.0.0.0", port=PORT, debug=False)


