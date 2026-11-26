#!/usr/bin/env python3
"""
IoT Sensor Simulator
Project: Containerizing an Edge Application with Docker

Simulates an IoT Temperature & Humidity Sensor transmitting environmental
readings over HTTP/REST to the containerized Edge Application.

Usage Examples:
  python sensor_simulator.py                    # Runs continuous automated simulation
  python sensor_simulator.py --spike            # Transmits high temperature anomaly (> 35°C)
  python sensor_simulator.py --interval 1.5     # Transmit every 1.5 seconds
  python sensor_simulator.py --count 10         # Transmit 10 readings then stop
  python sensor_simulator.py --interactive      # Interactive manual mode (Enter=normal, s=spike)
"""

import sys
import time
import random
import argparse
import requests
from datetime import datetime

# ANSI Color formatting for terminal presentation
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def generate_reading(device_id="sensor_01", force_spike=False):
    """
    Generate synthetic IoT telemetry payload.
    - Normal temperature: 25.0°C to 34.0°C
    - Spike temperature: 35.5°C to 42.0°C
    """
    # 15% probability of natural anomaly if not explicitly forced
    is_spike = force_spike or (random.random() < 0.15)

    if is_spike:
        temperature = round(random.uniform(35.5, 42.0), 2)
        humidity = round(random.uniform(70.0, 92.0), 1)
    else:
        temperature = round(random.uniform(25.0, 33.8), 2)
        humidity = round(random.uniform(48.0, 68.0), 1)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "device_id": device_id,
        "temperature": temperature,
        "humidity": humidity,
        "timestamp": timestamp
    }, is_spike


def transmit_reading(target_url, payload):
    """Send telemetry reading to the Edge Gateway API endpoint with automatic port fallback."""
    # First attempt with specified target_url
    try:
        response = requests.post(target_url, json=payload, timeout=3.0)
        if response.status_code in (200, 201):
            return response.status_code, response.json()
    except requests.exceptions.RequestException:
        pass

    # If port 5000 failed or responded with non-Edge error (e.g. 404/405 from another app like SmartMirror),
    # check fallback port 5050:
    if ":5000" in target_url:
        fallback_url = target_url.replace(":5000", ":5050")
        try:
            res_alt = requests.post(fallback_url, json=payload, timeout=3.0)
            if res_alt.status_code in (200, 201):
                return res_alt.status_code, res_alt.json()
        except requests.exceptions.RequestException:
            pass

    return None, f"Edge Application not reachable at {target_url} (or fallback :5050)"



def print_banner(target_url, device_id):
    print(f"{CYAN}{'=' * 75}{RESET}")
    print(f"{BOLD}{CYAN}  IoT SENSOR SIMULATOR -> Containerized Edge Gateway{RESET}")
    print(f"  Target Edge API : {BOLD}{target_url}{RESET}")
    print(f"  Simulated Device: {BOLD}{device_id}{RESET}")
    print(f"  Threshold Rule  : Temp >= 35.0°C -> HIGH TEMPERATURE ALERT")
    print(f"{CYAN}{'=' * 75}{RESET}\n")


def run_continuous(target_url, device_id, interval, max_count=None):
    """Continuous transmission loop."""
    print_banner(target_url, device_id)
    print(f"{YELLOW}[IoT Simulator] Starting continuous telemetry transmission... (Ctrl+C to stop){RESET}\n")

    count = 0
    try:
        while True:
            count += 1
            payload, is_spike = generate_reading(device_id)

            status_code, result = transmit_reading(target_url, payload)

            now_str = datetime.now().strftime("%H:%M:%S")
            if status_code in (200, 201):
                res_data = result.get("result", {})
                status = res_data.get("status", "UNKNOWN")

                if "ALERT" in status:
                    status_badge = f"{BOLD}{RED}[EDGE ALERT!]{RESET}"
                    val_str = f"{RED}{payload['temperature']}°C{RESET}"
                else:
                    status_badge = f"{GREEN}[NORMAL]{RESET}"
                    val_str = f"{GREEN}{payload['temperature']}°C{RESET}"

                print(f"[{now_str}] #{count:03d} | Device: {device_id} | "
                      f"Temp: {val_str} | Humidity: {payload['humidity']}% "
                      f"--> {status_badge} (HTTP {status_code})")
            else:
                print(f"[{now_str}] #{count:03d} | {RED}[ERROR]{RESET} {result}")
                print(f"{YELLOW}  Tip: Ensure the Docker container or Flask app is running at {target_url}{RESET}")

            if max_count and count >= max_count:
                print(f"\n{GREEN}Completed transmission of {max_count} readings.{RESET}")
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n{YELLOW}[IoT Simulator] Transmission stopped by user. Total sent: {count}{RESET}")


def run_single_spike(target_url, device_id):
    """Send one explicit high-temperature anomaly."""
    print_banner(target_url, device_id)
    print(f"{YELLOW}[IoT Simulator] Generating HIGH TEMPERATURE anomaly reading...{RESET}")

    payload, _ = generate_reading(device_id, force_spike=True)
    status_code, result = transmit_reading(target_url, payload)

    if status_code in (200, 201):
        res_data = result.get("result", {})
        print(f"{BOLD}{RED}\n[ANOMALY TRANSMITTED SUCCESSFULLY]{RESET}")
        print(f"  Device     : {payload['device_id']}")
        print(f"  Temperature: {BOLD}{RED}{payload['temperature']} °C{RESET} (Breaches 35°C threshold)")
        print(f"  Humidity   : {payload['humidity']} %")
        print(f"  Edge Status: {BOLD}{RED}{res_data.get('status')}{RESET}")
        print(f"  Message    : {res_data.get('message')}\n")
    else:
        print(f"{RED}[ERROR] Could not transmit reading: {result}{RESET}")


def run_interactive(target_url, device_id):
    """Interactive mode allowing presenter to choose normal or alert readings."""
    print_banner(target_url, device_id)
    print(f"{YELLOW}Interactive Mode Enabled for Demonstration:{RESET}")
    print(f"  Press {BOLD}[ENTER]{RESET}       -> Transmit NORMAL reading (< 35°C)")
    print(f"  Type {BOLD}'s' + [ENTER]{RESET} -> Transmit HIGH TEMP SPIKE (>= 35°C)")
    print(f"  Type {BOLD}'q' + [ENTER]{RESET} -> Quit\n")

    count = 0
    while True:
        try:
            choice = input(f"{CYAN}Sensor Prompt [{count + 1}] > {RESET}").strip().lower()
            if choice == "q":
                break

            force_spike = (choice == "s")
            payload, is_spike = generate_reading(device_id, force_spike=force_spike)
            count += 1

            status_code, result = transmit_reading(target_url, payload)
            if status_code in (200, 201):
                res_data = result.get("result", {})
                status = res_data.get("status")
                badge = f"{BOLD}{RED}[ALERT DETECTED]{RESET}" if "ALERT" in status else f"{GREEN}[NORMAL]{RESET}"
                print(f"  -> Sent: {payload['temperature']}°C | Hum: {payload['humidity']}% | Edge Evaluation: {badge}\n")
            else:
                print(f"  -> {RED}Error: {result}{RESET}\n")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting interactive mode.")
            break


def main():
    parser = argparse.ArgumentParser(
        description="IoT Sensor Simulator for Edge Computing Laboratory Project"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:5000/api/sensor",
        help="Target Edge Gateway API URL (default: http://localhost:5000/api/sensor)"
    )
    parser.add_argument(
        "--device",
        default="sensor_01",
        help="Simulated Device ID (default: sensor_01)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Transmission interval in seconds (default: 2.0)"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Number of readings to transmit before terminating (default: infinite)"
    )
    parser.add_argument(
        "--spike",
        action="store_true",
        help="Transmit an abnormal high-temperature reading immediately"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run interactive mode for live presentation"
    )

    args = parser.parse_args()

    if args.spike:
        run_single_spike(args.url, args.device)
    elif args.interactive:
        run_interactive(args.url, args.device)
    else:
        run_continuous(args.url, args.device, args.interval, args.count)


if __name__ == "__main__":
    main()
