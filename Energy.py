import os
import json
import threading
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response
from flask_cors import CORS
import tinytuya
import mysql.connector
from io import StringIO
import csv

app = Flask(__name__)
CORS(app)

# ─── Tuya Cloud Configuration ─────────────────────────────────────────────
API_REGION = "eu"
API_KEY = "jpemtvyqmyvtytvcpywj"
API_SECRET = "bbe0b8e88059472bb0c50e1735537e03"

# ─── Device and Room Mapping ──────────────────────────────────────────────
ROOM_DEVICE_MAP = {
    1: "bf2ea6423fde0e3a5bu0lt",
}

# ─── Cloud Device Initialization ───────────────────────────────────────────
cloud = tinytuya.Cloud(
    apiRegion=API_REGION,
    apiKey=API_KEY,
    apiSecret=API_SECRET,
    apiDeviceID=next(iter(ROOM_DEVICE_MAP.values())),
)


# ─── MySQL Database Connection Setup ──────────────────────────────────────
def get_db_connection():
    return mysql.connector.connect(
        host="Asifuzzaman.mysql.pythonanywhere-services.com",
        user="Asifuzzaman",
        password="l1v1ng1nh3ll25",
        database="Asifuzzaman$default",
    )


def create_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS room_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME,
                room_id INT,
                connected BOOLEAN,
                power_on BOOLEAN,
                current FLOAT,
                voltage FLOAT FLOAT,
                watt FLOAT
            )
        """
        )
        conn.commit()
    except mysql.connector.Error as err:
        print(f"Error creating table: {err}")
    finally:
        if "conn" in locals() and conn.is_connected():
            cursor.close()
            conn.close()


# ─── Data Handling ───────────────────────────────────────────────────────
DATA_DIR = "flask_app/static/data"
DATA_FILE_TEMPLATE = "room{}_data.json"


def load_data(room_id):
    """Load data for a specific room from the file system."""
    file_path = os.path.join(DATA_DIR, DATA_FILE_TEMPLATE.format(room_id))
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    else:
        print(f"No data found for Room {room_id} at {file_path}")
        return []


def save_data(room_id, data):
    """Saves JSON data to the file for a specific room."""
    file_path = os.path.join(DATA_DIR, DATA_FILE_TEMPLATE.format(room_id))
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


def insert_data_to_db(room_id, data):
    """Insert data into MySQL database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    for data_point in data:
        cursor.execute(
            """
            INSERT INTO room_data (timestamp, room_id, connected, power_on, current, voltage, watt)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
            (
                data_point["timestamp"],
                room_id,
                data_point["connected"],
                data_point["power_on"],
                data_point["current"],
                data_point["voltage"],
                data_point["watt"],
            ),
        )

    conn.commit()
    cursor.close()
    conn.close()


# ─── Data Collection ──────────────────────────────────────────────────────
is_collecting = {}


def collect_data(room_id, device_id):
    """
    Thread function to periodically collect data for a single device and save it.
    """
    global cloud
    print(f"Starting data collection for Room {room_id} with device ID {device_id}")
    data_history = load_data(room_id)

    while is_collecting.get(room_id, False):
        try:
            result = cloud.getstatus(device_id) if cloud else None
            current_time = datetime.now().isoformat()

            if result and result.get("success", False):
                status_data = result.get("result", [])
                power_on, current, voltage, watt = False, 0, 0, 0
                for item in status_data:
                    if item.get("code") == "switch_1":
                        power_on = item.get("value", False)
                    elif item.get("code") == "cur_current":
                        current = item.get("value", 0) / 1000
                    elif item.get("code") == "cur_voltage":
                        voltage = item.get("value", 0) / 10
                    elif item.get("code") == "cur_power":
                        watt = item.get("value", 0) / 10

                data_point = {
                    "timestamp": current_time,
                    "room_id": room_id,
                    "connected": True,
                    "power_on": power_on,
                    "current": current,
                    "voltage": voltage,
                    "watt": watt,
                }
            else:
                data_point = {
                    "timestamp": current_time,
                    "room_id": room_id,
                    "connected": False,
                    "power_on": False,
                    "current": 0,
                    "voltage": 0,
                    "watt": 0,
                }

            data_history.append(data_point)
            save_data(room_id, data_history)
            insert_data_to_db(room_id, [data_point])
        except Exception as e:
            print(f"Data collection error for Room {room_id}: {e}")
        time.sleep(7)


# ─── Device Control ───────────────────────────────────────────────────────
def get_device_status(device_id):
    """
    Returns a dict with: switch (bool), power (float W), current (float A), voltage (float V)
    """
    result = cloud.getstatus(device_id)
    if result and result.get("success", False):
        status_data = result.get("result", [])
        power_on, current, voltage, watt = False, 0, 0, 0
        for item in status_data:
            if item.get("code") == "switch_1":
                power_on = item.get("value", False)
            elif item.get("code") == "cur_current":
                current = item.get("value", 0) / 1000
            elif item.get("code") == "cur_voltage":
                voltage = item.get("value", 0) / 10
            elif item.get("code") == "cur_power":
                watt = item.get("value", 0) / 10
        return {
            "switch": power_on,
            "power": watt,
            "current": current,
            "voltage": voltage,
        }
    return {"switch": False, "power": 0, "current": 0, "voltage": 0}


def set_device_power(device_id, state):
    """
    Sets the power state of a Tuya device using the a reliable command format.
    """
    try:
        cloud.sendcommand(
            device_id, {"commands": [{"code": "switch_1", "value": state}]}
        )
        return True
    except Exception as e:
        print(f"Error setting device power for {device_id}: {e}")
        return False


# ─── Routes ────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/status/<int:room_id>")
def status(room_id):
    device_id = ROOM_DEVICE_MAP.get(room_id)
    if device_id:
        status_data = get_device_status(device_id)
        return jsonify(status_data)
    return jsonify({"error": "Room not found"}), 404


# Modified route to turn device ON
@app.route("/on/<int:room_id>")
def power_on(room_id):
    device_id = ROOM_DEVICE_MAP.get(room_id)
    if device_id:
        success = set_device_power(device_id, True)
        if success:
            return jsonify({"success": True, "power_on": True})
        return jsonify({"success": False, "error": "Failed to set power"}), 500
    return jsonify({"error": "Room not found"}), 404


# Modified route to turn device OFF
@app.route("/off/<int:room_id>")
def power_off(room_id):
    device_id = ROOM_DEVICE_MAP.get(room_id)
    if device_id:
        success = set_device_power(device_id, False)
        if success:
            return jsonify({"success": True, "power_on": False})
        return jsonify({"success": False, "error": "Failed to set power"}), 500
    return jsonify({"error": "Room not found"}), 404


@app.route("/api/status/<int:room_id>")
def get_status_api(room_id):
    device_id = ROOM_DEVICE_MAP.get(room_id)
    if device_id:
        status_data = get_device_status(device_id)
        return jsonify(status_data)
    return jsonify({"error": "Invalid room ID"}), 400


@app.route("/api/toggle/<int:room_id>", methods=["POST"])
def toggle_power_api(room_id):
    device_id = ROOM_DEVICE_MAP.get(room_id)
    if device_id:
        current_status = get_device_status(device_id)
        new_power_state = not current_status.get("switch", False)
        success = set_device_power(device_id, new_power_state)
        if success:
            return jsonify({"success": True, "power_on": new_power_state})
        return jsonify({"success": False, "error": "Failed to toggle power"}), 500
    return jsonify({"error": "Invalid room ID"}), 400


@app.route("/api/data/<int:room_id>")
def get_data(room_id):
    try:
        from_time = request.args.get("from")
        to_time = request.args.get("to")

        data = get_data_by_room_and_time_range(room_id, from_time, to_time)

        if data:
            data_list = [
                {
                    "timestamp": entry["timestamp"],
                    "room_id": entry["room_id"],
                    "connected": entry["connected"],
                    "power_on": entry["power_on"],
                    "current": entry["current"],
                    "voltage": entry["voltage"],
                    "watt": entry["watt"],
                }
                for entry in data
            ]
            return jsonify(data_list)
        else:
            return jsonify({"error": f"No data found for Room {room_id}"}), 404

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return jsonify({"error": f"Database error: {err}"}), 500


@app.route("/api/energy/<int:room_id>")
def calculate_energy(room_id):
    data_history = load_data(room_id)
    total_energy = 0
    if len(data_history) > 1:
        for i in range(1, len(data_history)):
            t1 = datetime.fromisoformat(data_history[i - 1]["timestamp"])
            t2 = datetime.fromisoformat(data_history[i]["timestamp"])
            delta_h = (t2 - t1).total_seconds() / 3600
            avg_watt = (data_history[i]["watt"] + data_history[i - 1]["watt"]) / 2
            total_energy += (avg_watt * delta_h) / 1000
    return jsonify({"energy_kwh": round(total_energy, 4)})


@app.route("/api/download-csv/<int:room_id>")
def download_csv(room_id):
    """
    Endpoint to download data as a CSV file, with optional date range.
    """
    from_date_str = request.args.get("from")
    to_date_str = request.args.get("to")

    from_time = from_date_str if from_date_str else None
    to_time = to_date_str if to_date_str else None

    data = get_data_by_room_and_time_range(room_id, from_time, to_time)

    if not data:
        return (
            jsonify({"error": "No data found for the specified room and time range."}),
            404,
        )

    csv_content = generate_csv(data)

    file_size_mb = len(csv_content.encode("utf-8")) / (1024 * 1024)

    if file_size_mb <= 2:
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={
                "Content-disposition": f"attachment; filename=room_{room_id}_data.csv"
            },
        )
    else:
        mid_point = len(data) // 2
        data_part1 = data[:mid_point]
        data_part2 = data[mid_point:]

        csv_content1 = generate_csv(data_part1)
        csv_content2 = generate_csv(data_part2)

        return jsonify(
            {
                "success": True,
                "room_id": room_id,
                "part1_data": csv_content1,
                "part2_data": csv_content2,
                "message": "Data split into two files due to size limit.",
            }
        )


def get_data_by_room_and_time_range(room_id, from_time=None, to_time=None):
    """
    Fetches data from the database for a specific room within an optional
    time range.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = "SELECT timestamp, room_id, connected, power_on, current, voltage, watt FROM room_data WHERE room_id = %s"
    params = [room_id]

    if from_time and to_time:
        query += " AND timestamp BETWEEN %s AND %s"
        params.append(from_time)
        params.append(to_time)

    query += " ORDER BY timestamp"

    cursor.execute(query, tuple(params))
    data = cursor.fetchall()

    cursor.close()
    conn.close()
    return data


def generate_csv(data):
    """Generates CSV content from a list of dictionaries."""
    if not data:
        return ""

    fieldnames = [
        "timestamp",
        "room_id",
        "connected",
        "power_on",
        "current",
        "voltage",
        "watt",
    ]
    csv_buffer = StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)

    writer.writeheader()
    writer.writerows(data)

    return csv_buffer.getvalue()


if __name__ == "__main__":
    create_db()
    if ROOM_DEVICE_MAP:
        first_device_id = list(ROOM_DEVICE_MAP.values())[0]
        cloud = tinytuya.Cloud(
            apiRegion=API_REGION,
            apiKey=API_KEY,
            apiSecret=API_SECRET,
            apiDeviceID=first_device_id,
        )

    for room_id in range(1, 101):
        file_path = os.path.join(DATA_DIR, DATA_FILE_TEMPLATE.format(room_id))
        if os.path.exists(file_path):
            data = load_data(room_id)
            if data:
                insert_data_to_db(room_id, data)
                print(f"Data for Room {room_id} inserted into the database.")
            else:
                print(f"No data found in {file_path}")

    for room_id, device_id in ROOM_DEVICE_MAP.items():
        is_collecting[room_id] = True
        thread = threading.Thread(target=collect_data, args=(room_id, device_id))
        thread.daemon = True
        thread.start()
        print(f"Data collection thread started for Room {room_id}")

    app.run(debug=True, host="0.0.0.0", port=5005)
