from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import tinytuya
import json
import threading
import time
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# Tuya cloud configuration (Updated with your new credentials)
DEVICE_ID = "bf2ea6423fde0e3a5bu0lt"  # New Device ID
API_REGION = "eu"  # Region is "eu" (for Europe)
API_KEY = "jpemtvyqmyvtytvcpywj"  # New Access ID/Client ID
API_SECRET = "bbe0b8e88059472bb0c50e1735537e03"  # New Access Secret/Client Secret
UId = "eu1753528411983D22FV"  # Your UId for the device

DATA_FILE = "2nddevice_data.json"
cloud = None
data_collection_thread = None
is_collecting = False

def init_device():
    global cloud
    try:
        cloud = tinytuya.Cloud(
            apiRegion=API_REGION,
            apiKey=API_KEY,
            apiSecret=API_SECRET,
            apiDeviceID=DEVICE_ID
        )
        result = cloud.getstatus(DEVICE_ID)
        print(f"Device status response: {result}")
        return result.get('success', False)
    except Exception as e:
        print(f"Device initialization error: {e}")
        return False

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def collect_data():
    global is_collecting
    data_history = load_data()
    while is_collecting:
        try:
            result = cloud.getstatus(DEVICE_ID) if cloud else None
            current_time = datetime.now().isoformat()

            if result and result.get('success', False):
                status_data = result.get('result', [])
                power_on, current, voltage, watt = False, 0, 0, 0
                for item in status_data:
                    if item.get('code') == 'switch_1':
                        power_on = item.get('value', False)
                    elif item.get('code') == 'cur_current':
                        current = item.get('value', 0) / 1000
                    elif item.get('code') == 'cur_voltage':
                        voltage = item.get('value', 0) / 10
                    elif item.get('code') == 'cur_power':
                        watt = item.get('value', 0) / 10
                data_point = {
                    "timestamp": current_time,
                    "connected": True,
                    "power_on": power_on,
                    "current": current,
                    "voltage": voltage,
                    "watt": watt
                }
            else:
                data_point = {
                    "timestamp": current_time,
                    "connected": False,
                    "power_on": False,
                    "current": 0,
                    "voltage": 0,
                    "watt": 0
                }
            data_history.append(data_point)
            save_data(data_history)
        except Exception as e:
            print(f"Data collection error: {e}")
        time.sleep(7)

@app.route('/')
def index():
    return render_template('tuya.html')

@app.route('/api/status')
def get_status():
    try:
        result = cloud.getstatus(DEVICE_ID) if cloud else None
        if result and result.get('success', False):
            status_data = result.get('result', [])
            power_on, current, voltage, watt = False, 0, 0, 0
            for item in status_data:
                if item.get('code') == 'switch_1':
                    power_on = item.get('value', False)
                elif item.get('code') == 'cur_current':
                    current = item.get('value', 0) / 1000
                elif item.get('code') == 'cur_voltage':
                    voltage = item.get('value', 0) / 10
                elif item.get('code') == 'cur_power':
                    watt = item.get('value', 0) / 10
            return jsonify({
                "connected": True,
                "power_on": power_on,
                "current": current,
                "voltage": voltage,
                "watt": watt
            })
        return jsonify({"connected": False, "power_on": False, "current": 0, "voltage": 0, "watt": 0})
    except Exception as e:
        print(f"Status error: {e}")
        return jsonify({"connected": False, "power_on": False, "current": 0, "voltage": 0, "watt": 0})

@app.route('/api/toggle', methods=['POST'])
def toggle_power():
    try:
        result = cloud.getstatus(DEVICE_ID)  # Get the current device status
        if result and result.get('success', False):
            status_data = result.get('result', [])
            current_power = any(item.get('code') == 'switch_1' and item.get('value', False) for item in status_data)
            new_power = not current_power  # Toggle the current power state
            command_result = cloud.sendcommand(DEVICE_ID, [{
                "code": "switch_1",
                "value": new_power
            }])
            return jsonify({"success": command_result.get('success', False), "power_on": new_power})
        return jsonify({"success": False, "error": "Device not connected"})
    except Exception as e:
        print(f"Toggle error: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/data')
def get_data():
    data_history = load_data()
    return jsonify(data_history)

@app.route('/api/energy')
def calculate_energy():
    data_history = load_data()
    total_energy = 0
    for i in range(1, len(data_history)):
        t1 = datetime.fromisoformat(data_history[i-1]['timestamp'])
        t2 = datetime.fromisoformat(data_history[i]['timestamp'])
        delta_h = (t2 - t1).total_seconds() / 3600
        avg_watt = (data_history[i]['watt'] + data_history[i-1]['watt']) / 2
        total_energy += (avg_watt * delta_h) / 1000
    return jsonify({"energy_kwh": round(total_energy, 4)})

if __name__ == '__main__':
    if init_device():
        is_collecting = True
        thread = threading.Thread(target=collect_data)
        thread.daemon = True
        thread.start()
        print("Cloud device connected and data collection started")
    else:
        print("Failed to connect to cloud device")
    app.run(debug=True, host='0.0.0.0', port=5005)