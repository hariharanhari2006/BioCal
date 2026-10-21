from flask import Flask, render_template, jsonify, request
import serial, threading, time, math
from serial.tools import list_ports

app = Flask(__name__)
BAUD = 9600
lock = threading.Lock()
state = {'connected': False, 'port': None, 'raw': None, 'led': 1, 'reference': None, 'error': None}
ser = None
reader_thread = None
stop_reader = threading.Event()
calibration = []

def serial_reader():
    global ser
    while not stop_reader.is_set():
        try:
            if ser is None or not ser.is_open:
                time.sleep(.2); continue
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith('LDR:'):
                try:
                    value = int(line.split(':', 1)[1])
                    if 0 <= value <= 1023:
                        with lock: state.update(raw=value, error=None)
                except ValueError: pass
        except Exception as exc:
            with lock: state['error'] = str(exc)
            time.sleep(.3)

@app.route('/')
def home(): return render_template('index.html')

@app.get('/api/ports')
def ports():
    return jsonify(ports=[{'device': p.device, 'description': p.description} for p in list_ports.comports()])

@app.get('/api/status')
def status():
    with lock: return jsonify(dict(state))

@app.post('/api/connect')
def connect():
    global ser, reader_thread
    port = str((request.get_json(silent=True) or {}).get('port', '')).strip()
    if not port: return jsonify(ok=False, error='Select an Arduino serial port.'), 400
    try:
        stop_reader.set()
        if reader_thread and reader_thread.is_alive(): reader_thread.join(timeout=1)
        if ser:
            try: ser.close()
            except Exception: pass
        stop_reader.clear()
        ser = serial.Serial(port, BAUD, timeout=1)
        time.sleep(2)
        ser.reset_input_buffer()
        with lock: state.update(connected=True, port=port, raw=None, error=None)
        reader_thread = threading.Thread(target=serial_reader, daemon=True)
        reader_thread.start()
        return jsonify(ok=True, message=f'Connected to {port} at {BAUD} baud.')
    except Exception as exc:
        with lock: state.update(connected=False, port=None, error=str(exc))
        return jsonify(ok=False, error=str(exc)), 500

@app.post('/api/disconnect')
def disconnect():
    global ser
    stop_reader.set()
    if ser:
        try: ser.close()
        except Exception: pass
    with lock: state.update(connected=False, port=None, raw=None)
    return jsonify(ok=True)

@app.post('/api/led')
def select_led():
    global ser
    try: n = int((request.get_json(silent=True) or {}).get('led', 1))
    except (TypeError, ValueError): n = 0
    if n not in (1, 2, 3): return jsonify(ok=False, error='LED must be 1, 2, or 3.'), 400
    if ser is None or not ser.is_open: return jsonify(ok=False, error='Connect to Arduino first.'), 400
    try:
        ser.write(f'LED1:0\nLED2:0\nLED3:0\nLED{n}:1\n'.encode())
        with lock: state['led'] = n
        return jsonify(ok=True, led=n)
    except Exception as exc: return jsonify(ok=False, error=str(exc)), 500

@app.post('/api/led/off')
def all_off():
    if ser and ser.is_open:
        try: ser.write(b'LED1:0\nLED2:0\nLED3:0\n')
        except Exception: pass
    return jsonify(ok=True)

@app.post('/api/reference')
def set_reference():
    with lock: raw, connected = state['raw'], state['connected']
    if not connected or raw is None: return jsonify(ok=False, error='Connect and wait for a live reading first.'), 400
    if raw <= 0: return jsonify(ok=False, error='Reference reading is zero. Check the LED and LDR alignment.'), 400
    with lock: state['reference'] = raw
    return jsonify(ok=True, reference=raw)

@app.post('/api/reference/clear')
def clear_reference():
    with lock: state['reference'] = None
    return jsonify(ok=True)

@app.get('/api/measurement')
def measurement():
    with lock: raw, ref, connected, led = state['raw'], state['reference'], state['connected'], state['led']
    trans = od = None
    if connected and raw is not None and ref is not None and ref > 0:
        trans = max(0.0, min(1.0, raw / ref))
        if trans > 0: od = -math.log10(trans)
    return jsonify(connected=connected, raw=raw, reference=ref, transmittance=trans, od=od, led=led)

@app.get('/api/calibration')
def get_calibration(): return jsonify(samples=calibration)

@app.post('/api/calibration')
def add_calibration():
    payload = request.get_json(silent=True) or {}
    try: concentration = float(payload['concentration'])
    except (KeyError, TypeError, ValueError): return jsonify(ok=False, error='Enter a valid numeric concentration.'), 400
    with lock: raw, ref, connected = state['raw'], state['reference'], state['connected']
    if not connected or raw is None or ref is None or ref <= 0 or raw <= 0:
        return jsonify(ok=False, error='Connect Arduino, set a valid blank reference, and ensure the reading is above zero.'), 400
    od = -math.log10(max(1e-9, min(1.0, raw / ref)))
    calibration.append({'raw': raw, 'od': od, 'concentration': concentration})
    return jsonify(ok=True, samples=calibration)

@app.post('/api/calibration/clear')
def clear_calibration():
    calibration.clear()
    return jsonify(ok=True)

@app.post('/api/predict')
def predict():
    if len(calibration) < 2: return jsonify(ok=False, error='Add at least two calibration standards first.'), 400
    with lock: raw, ref, connected = state['raw'], state['reference'], state['connected']
    if not connected or raw is None or ref is None or ref <= 0 or raw <= 0:
        return jsonify(ok=False, error='No valid live reading/reference. Set a blank and check the sensor.'), 400
    xs = [s['od'] for s in calibration]; ys = [s['concentration'] for s in calibration]
    mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
    denom = sum((x-mx)**2 for x in xs)
    if denom == 0: return jsonify(ok=False, error='Calibration readings are identical. Measure standards with different optical readings.'), 400
    slope = sum((xs[i]-mx)*(ys[i]-my) for i in range(len(xs))) / denom
    intercept = my - slope*mx
    od = -math.log10(max(1e-9, min(1.0, raw/ref)))
    return jsonify(ok=True, prediction=slope*od+intercept, od=od, note='Basic linear-regression estimate. Validate with independent known samples.')

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
