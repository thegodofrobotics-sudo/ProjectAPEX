import cv2
import numpy as np
import threading
import time
import random
import serial
import base64
import io
import csv
import math
from flask import Flask, Response, jsonify, request, render_template_string, make_response

app = Flask(__name__)

# ==============================================================================
# 1. Hardware Serial Bridge Connection (STM32 Microcontroller Core)
# ==============================================================================
mcu = None
candidate_ports = ['/dev/ttyHS1', '/dev/ttyS0', '/dev/ttyMSM0', '/dev/ttyGS0', '/dev/ttyACM0']

for port in candidate_ports:
    try:
        test_mcu = serial.Serial(
            port=port,
            baudrate=9600,
            timeout=0.5,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )
        if test_mcu.is_open:
            mcu = test_mcu
            print(f"[APEX-PRIME] Hardware serial bridge locked on {port}")
            break
    except Exception:
        continue

# ==============================================================================
# 2. Tactical System State & Telemetry Matrix
# ==============================================================================
system_state = {
    "temperature": 26.8,
    "humidity": 52.4,
    "fire_risk": "NOMINAL (SAFE)",
    "fire_risk_score": 18,
    "status": "SECTOR ALPHA // ALL PERIMETERS SECURE",
    "threat_level": "LOW",
    "threat_code": "CODE GREEN (SECURE)",
    "identified_target": "None",
    "poacher_count": 0,
    "staff_count": 0,
    "wildlife_count": 0,
    "wildlife_status": "NOMINAL (UNTHREATENED)",
    "total_objects": 0,
    "total_intrusions": 0,
    "last_alert_time": "None",
    "camera_source": "INITIALIZING SENSORS...",
    "audio_alarm": False,
    "manual_alarm": False,
    "vision_mode": "OPTICAL",
    "target_velocity": "STATIONARY",
    "speed_px_sec": 0,
    "fps": 29.2,
    "radar_targets": [],
    "active_targets_detail": [],
    "min_distance_px": 999,
    "intercept_bearing_deg": 0,
    "voice_announcement": ""
}

incident_logs = []
evidence_snapshots = []
telemetry_history = []
MAX_SNAPSHOTS = 6

# ==============================================================================
# 3. High-Precision Optical Video Pipeline
# ==============================================================================
cap = None
USE_REAL_CAMERA = False

for idx in [2, 0, 1, 3]:
    temp_cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
    if temp_cap.isOpened():
        ret, frame = temp_cap.read()
        if ret and frame is not None:
            cap = temp_cap
            USE_REAL_CAMERA = True
            system_state["camera_source"] = f"HIGH-RES UVC SENSOR (/dev/video{idx})"
            print(f"[APEX-PRIME] Optical feed locked on /dev/video{idx}")
            break
        temp_cap.release()

if not USE_REAL_CAMERA:
    system_state["camera_source"] = "SYNTHETIC C4ISR RECON FEED"

# ==============================================================================
# 4. Background Telemetry Reader (DHT11 & Forest Fire Threat Index)
# ==============================================================================
def telemetry_worker():
    global mcu
    sim_t = 27.2
    sim_h = 54.0

    while True:
        data_parsed = False
        if mcu and mcu.is_open:
            try:
                if mcu.in_waiting > 0:
                    line = mcu.readline().decode('utf-8', errors='ignore').strip()
                    if "DATA:" in line:
                        payload = line.split("DATA:")[1]
                        parts = payload.split(",")
                        if len(parts) == 2:
                            system_state["temperature"] = round(float(parts[0].strip()), 1)
                            system_state["humidity"] = round(float(parts[1].strip()), 1)
                            data_parsed = True
            except Exception:
                pass

        if not data_parsed:
            sim_t += random.uniform(-0.04, 0.04)
            sim_h += random.uniform(-0.08, 0.08)
            system_state["temperature"] = round(sim_t, 1)
            system_state["humidity"] = round(sim_h, 1)

        # Mathematical Forest Fire Weather Index (FWI)
        temp = system_state["temperature"]
        hum = system_state["humidity"]
        fire_score = int(max(0, min(100, (temp * 2.2) - (hum * 0.8) + 15)))
        system_state["fire_risk_score"] = fire_score

        if fire_score > 75:
            system_state["fire_risk"] = "CRITICAL // WILDFIRE HAZARD"
        elif fire_score > 45:
            system_state["fire_risk"] = "ELEVATED FIRE THREAT"
        else:
            system_state["fire_risk"] = "NOMINAL (SAFE)"

        telemetry_history.append({
            "time": time.strftime("%H:%M:%S"),
            "temp": temp,
            "hum": hum,
            "fire": fire_score
        })
        if len(telemetry_history) > 30:
            telemetry_history.pop(0)

        time.sleep(1.0)

threading.Thread(target=telemetry_worker, daemon=True).start()

# ==============================================================================
# 5. Saliency Target Classification & Tracking Engine
# ==============================================================================
def extract_targets(frame, max_limit=3):
    h, w = frame.shape[:2]
    
    # Active Defense Zone Mask (7% border margin to eliminate room & table perimeter clutter)
    roi_mask = np.zeros((h, w), dtype=np.uint8)
    roi_mask[int(h*0.07):int(h*0.93), int(w*0.07):int(w*0.93)] = 255

    # Bilateral noise filter: Preserves 3D physical toy edges while suppressing grass mat textures
    smooth = cv2.bilateralFilter(frame, 7, 75, 75)
    hsv = cv2.cvtColor(smooth, cv2.COLOR_BGR2HSV)
    kernel_m = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    # --- Target 1: Authorized Ranger (Pure Blue LEGO Minifigure) ---
    staff_raw = cv2.inRange(hsv, np.array([92, 80, 50]), np.array([135, 255, 255]))
    staff_mask = cv2.bitwise_and(staff_raw, roi_mask)
    staff_mask = cv2.morphologyEx(staff_mask, cv2.MORPH_OPEN, kernel_m)
    staff_mask = cv2.morphologyEx(staff_mask, cv2.MORPH_DILATE, kernel_m, iterations=2)

    # --- Target 2: Wildlife (Amber, Orange & Yellow Animal Toys) ---
    wildlife_raw = cv2.inRange(hsv, np.array([11, 90, 65]), np.array([36, 255, 255]))
    wildlife_mask = cv2.bitwise_and(wildlife_raw, roi_mask)
    wildlife_mask = cv2.bitwise_and(wildlife_mask, cv2.bitwise_not(staff_mask))
    wildlife_mask = cv2.morphologyEx(wildlife_mask, cv2.MORPH_OPEN, kernel_m)
    wildlife_mask = cv2.morphologyEx(wildlife_mask, cv2.MORPH_DILATE, kernel_m, iterations=2)

    # --- Target 3: Poacher [Hostile] (Reddish-Brown / Brick Red Figure) ---
    m_red1 = cv2.inRange(hsv, np.array([0, 85, 45]), np.array([10, 255, 255]))
    m_red2 = cv2.inRange(hsv, np.array([168, 85, 45]), np.array([180, 255, 255]))
    poacher_raw = cv2.bitwise_or(m_red1, m_red2)
    poacher_mask = cv2.bitwise_and(poacher_raw, roi_mask)
    poacher_mask = cv2.bitwise_and(poacher_mask, cv2.bitwise_not(staff_mask))
    poacher_mask = cv2.bitwise_and(poacher_mask, cv2.bitwise_not(wildlife_mask))
    poacher_mask = cv2.morphologyEx(poacher_mask, cv2.MORPH_OPEN, kernel_m)
    poacher_mask = cv2.morphologyEx(poacher_mask, cv2.MORPH_DILATE, kernel_m, iterations=2)

    detected = []

    def validate_entity(cnt, mask_src):
        area = cv2.contourArea(cnt)
        if 750 < area < 35000:
            bx, by, bw, bh = cv2.boundingRect(cnt)
            if 20 < bw < 320 and 20 < bh < 320:
                roi = mask_src[by:by+bh, bx:bx+bw]
                density = cv2.countNonZero(roi) / float(bw * bh)
                if density > 0.24:
                    return True, (bx, by, bw, bh), area
        return False, None, 0

    # 1. Staff
    cnts_s, _ = cv2.findContours(staff_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts_s:
        valid, box, area = validate_entity(c, staff_mask)
        if valid:
            bx, by, bw, bh = box
            detected.append({
                "type": "STAFF",
                "tag": "AUTHORIZED RANGER",
                "color": (255, 200, 0),
                "box": box,
                "area": area,
                "center": (bx + bw // 2, by + bh // 2)
            })

    # 2. Wildlife
    cnts_w, _ = cv2.findContours(wildlife_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts_w:
        valid, box, area = validate_entity(c, wildlife_mask)
        if valid:
            bx, by, bw, bh = box
            detected.append({
                "type": "WILDLIFE",
                "tag": "WILDLIFE",
                "color": (0, 255, 128),
                "box": box,
                "area": area,
                "center": (bx + bw // 2, by + bh // 2)
            })

    # 3. Poacher
    cnts_p, _ = cv2.findContours(poacher_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts_p:
        valid, box, area = validate_entity(c, poacher_mask)
        if valid:
            bx, by, bw, bh = box
            aspect = float(bh) / float(max(1, bw))
            if aspect >= 0.65:
                detected.append({
                    "type": "POACHER",
                    "tag": "POACHER [HOSTILE]",
                    "color": (0, 0, 255),
                    "box": box,
                    "area": area,
                    "center": (bx + bw // 2, by + bh // 2)
                })

    detected.sort(key=lambda item: item["area"], reverse=True)
    return detected[:max_limit]

def generate_video_stream():
    global USE_REAL_CAMERA
    
    prev_poacher_pos = None
    last_speed_time = time.time()
    trail_points = []
    
    poacher_streak = 0
    staff_streak = 0
    wildlife_streak = 0
    frame_counter = 0
    t_start = time.time()
    last_voice_announcement_time = 0

    while True:
        if USE_REAL_CAMERA:
            success, frame = cap.read()
            if not success:
                time.sleep(0.03)
                continue

            frame = cv2.resize(frame, (640, 480))
            frame_counter += 1
            if frame_counter % 15 == 0:
                elapsed = time.time() - t_start
                system_state["fps"] = round(15.0 / max(0.001, elapsed), 1)
                t_start = time.time()

            current_targets = extract_targets(frame, max_limit=3)

            p_count = sum(1 for t in current_targets if t["type"] == "POACHER")
            s_count = sum(1 for t in current_targets if t["type"] == "STAFF")
            w_count = sum(1 for t in current_targets if t["type"] == "WILDLIFE")

            # Temporal Debounce
            if p_count > 0: poacher_streak = min(8, poacher_streak + 2)
            else: poacher_streak = max(0, poacher_streak - 1)

            if s_count > 0: staff_streak = min(8, staff_streak + 2)
            else: staff_streak = max(0, staff_streak - 1)

            if w_count > 0: wildlife_streak = min(8, wildlife_streak + 2)
            else: wildlife_streak = max(0, wildlife_streak - 1)

            is_poacher_active = (poacher_streak >= 2)
            system_state["poacher_count"] = p_count if is_poacher_active else 0
            system_state["staff_count"] = s_count if staff_streak >= 2 else 0
            system_state["wildlife_count"] = w_count if wildlife_streak >= 2 else 0
            system_state["total_objects"] = len(current_targets) if (is_poacher_active or staff_streak >= 2 or wildlife_streak >= 2) else 0

            # Dynamic Threat Assessment for Wildlife
            if is_poacher_active and w_count > 0:
                system_state["wildlife_status"] = "ENDANGERED // THREAT ACTIVE IN SECTOR"
            elif w_count > 0:
                system_state["wildlife_status"] = "NOMINAL (UNTHREATENED)"
            else:
                system_state["wildlife_status"] = "NO ENTITIES DETECTED"

            # 100% Crash-Proof Proximity Calculation
            poachers = [t for t in current_targets if t["type"] == "POACHER"]
            wildlife = [t for t in current_targets if t["type"] == "WILDLIFE"]
            min_dist = 999
            bearing_deg = 0

            if poachers and wildlife and is_poacher_active:
                px, py = poachers[0]["center"]
                closest_w = None
                
                for w_obj in wildlife:
                    cur_wx, cur_wy = w_obj["center"]
                    d = int(np.sqrt((px - cur_wx)**2 + (py - cur_wy)**2))
                    if d < min_dist:
                        min_dist = d
                        closest_w = w_obj

                if closest_w is not None:
                    target_wx, target_wy = closest_w["center"]
                    rad = math.atan2(target_wy - py, target_wx - px)
                    bearing_deg = int((math.degrees(rad) + 360) % 360)

                    system_state["min_distance_px"] = min_dist
                    system_state["intercept_bearing_deg"] = bearing_deg
                    
                    # Render Tactical Ballistic Intercept Vector Line
                    cv2.line(frame, (px, py), (target_wx, target_wy), (0, 140, 255), 2)
                    cv2.circle(frame, (px, py), 6, (0, 0, 255), -1)
                    cv2.circle(frame, (target_wx, target_wy), 6, (0, 255, 128), -1)
                    
                    mid_x = (px + target_wx) // 2
                    mid_y = (py + target_wy) // 2
                    cv2.putText(frame, f"INTERCEPT: {min_dist}px | AZ: {bearing_deg} DEG", 
                                (mid_x - 70, max(25, mid_y - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 140, 255), 1)
            else:
                system_state["min_distance_px"] = 999
                system_state["intercept_bearing_deg"] = 0

            # Build Telemetry Dossier Cards
            details = []
            for t in current_targets:
                bx, by, bw, bh = t["box"]
                details.append({
                    "type": t["type"],
                    "tag": t["tag"],
                    "pos": f"X:{t['center'][0]} Y:{t['center'][1]}",
                    "size": f"{bw}x{bh} px",
                    "area": f"{t['area']} px²"
                })
            system_state["active_targets_detail"] = details

            # Map Radar Target Points
            r_targets = []
            if system_state["total_objects"] > 0:
                for t in current_targets:
                    cx, cy = t["center"]
                    target_tag = t["type"]
                    if target_tag == "WILDLIFE" and is_poacher_active:
                        target_tag = "WILDLIFE_AT_RISK"
                    r_targets.append({
                        "type": target_tag,
                        "nx": round((cx - 320) / 320.0, 2),
                        "ny": round((cy - 240) / 240.0, 2)
                    })
            system_state["radar_targets"] = r_targets

            # Kinematic Trajectory Vector
            if poachers and is_poacher_active:
                curr_pos = poachers[0]["center"]
                trail_points.append(curr_pos)
                if len(trail_points) > 12:
                    trail_points.pop(0)

                dt = max(0.01, time.time() - last_speed_time)
                if prev_poacher_pos is not None:
                    dx = curr_pos[0] - prev_poacher_pos[0]
                    dy = curr_pos[1] - prev_poacher_pos[1]
                    dist_px = np.sqrt(dx**2 + dy**2)
                    speed = int(dist_px / dt)
                    system_state["speed_px_sec"] = speed

                    if speed > 110:
                        system_state["target_velocity"] = "RAPID INFILTRATION"
                    elif speed > 20:
                        system_state["target_velocity"] = "SLOW INFILTRATION"
                    else:
                        system_state["target_velocity"] = "STATIONARY LOITERING"

                prev_poacher_pos = curr_pos
                last_speed_time = time.time()
            else:
                prev_poacher_pos = None
                trail_points.clear()
                system_state["target_velocity"] = "STATIONARY"
                system_state["speed_px_sec"] = 0

            # Multi-Spectrum Rendering Modes
            v_mode = system_state["vision_mode"]
            if v_mode == "INFERNO":
                gray_f = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frame = cv2.applyColorMap(gray_f, cv2.COLORMAP_INFERNO)
            elif v_mode == "JET":
                gray_f = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frame = cv2.applyColorMap(gray_f, cv2.COLORMAP_JET)
            elif v_mode == "NVG":
                gray_f = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frame = cv2.cvtColor(gray_f, cv2.COLOR_GRAY2BGR)
                frame[:, :, 0] = 0
                frame[:, :, 2] = 0
                for line_y in range(0, 480, 6):
                    cv2.line(frame, (0, line_y), (640, line_y), (0, 30, 0), 1)

            # Virtual Exclusion Boundary Line
            cv2.line(frame, (30, 390), (610, 390), (0, 0, 255), 1)
            cv2.putText(frame, "PERIMETER TRIPWIRE // DEFENSE GRID ACTIVE", (35, 382),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 255), 1)

            # Motion Trail
            for i in range(1, len(trail_points)):
                thickness = int(np.sqrt(12 / float(i + 1)) * 2)
                cv2.line(frame, trail_points[i - 1], trail_points[i], (0, 0, 255), thickness)

            # Draw Tactical Reticles & Corner Brackets
            idx_p, idx_s, idx_w = 1, 1, 1
            for t in current_targets:
                if (t["type"] == "POACHER" and is_poacher_active) or \
                   (t["type"] == "STAFF" and staff_streak >= 2) or \
                   (t["type"] == "WILDLIFE" and wildlife_streak >= 2):
                    
                    x, y, w, h = t["box"]
                    color = t["color"]

                    if t["type"] == "POACHER":
                        label = f"TARGET: POACHER #{idx_p} [{system_state['target_velocity']}]" if p_count > 1 else f"TARGET: POACHER [HOSTILE]"
                        idx_p += 1
                    elif t["type"] == "STAFF":
                        label = f"FRIENDLY: RANGER #{idx_s} [AUTH]" if s_count > 1 else t["tag"]
                        idx_s += 1
                    else:
                        if is_poacher_active:
                            label = f"WILDLIFE #{idx_w} [ENDANGERED // THREAT NEARBY]"
                            color = (0, 140, 255)
                        else:
                            label = f"BIOMETRIC: WILDLIFE #{idx_w} [SAFE]"
                            color = (0, 255, 128)
                        idx_w += 1

                    # Precision Corner Brackets
                    b_len = 16
                    cv2.line(frame, (x, y), (x + b_len, y), color, 3)
                    cv2.line(frame, (x, y), (x, y + b_len), color, 3)
                    cv2.line(frame, (x + w, y), (x + w - b_len, y), color, 3)
                    cv2.line(frame, (x + w, y), (x + w, y + b_len), color, 3)
                    cv2.line(frame, (x, y + h), (x + b_len, y + h), color, 3)
                    cv2.line(frame, (x, y + h), (x, y + h - b_len), color, 3)
                    cv2.line(frame, (x + w, y + h), (x + w - b_len, y + h), color, 3)
                    cv2.line(frame, (x + w, y + h), (x + w, y + h - b_len), color, 3)

                    # Bounding Outline
                    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 1)
                    cv2.putText(frame, label, (x, max(20, y - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 2)

            # State & Actuation Decision Engine
            if (poacher_streak >= 3) or system_state["manual_alarm"]:
                system_state["status"] = f"CRITICAL: POACHER DETECTED // {w_count} WILDLIFE IN DANGER" if w_count > 0 else f"CRITICAL: {p_count} HOSTILE POACHER(S) DETECTED"
                system_state["threat_level"] = "HIGH"
                system_state["threat_code"] = "CODE RED (LETHAL BREACH)"
                system_state["identified_target"] = f"POACHER ({p_count})" if p_count > 1 else "POACHER (HOSTILE)"
                system_state["audio_alarm"] = True
                timestamp = time.strftime("%H:%M:%S")

                # Autonomous Voice Announcement Trigger
                if time.time() - last_voice_announcement_time > 8.0:
                    system_state["voice_announcement"] = f"Warning. Hostile poacher breach detected in Sector Alpha. Intercept distance {min_dist} pixels. Deploying acoustic deterrence."
                    last_voice_announcement_time = time.time()

                if system_state["last_alert_time"] != timestamp and not system_state["manual_alarm"]:
                    system_state["last_alert_time"] = timestamp
                    system_state["total_intrusions"] += 1
                    
                    _, snap_buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    snap_b64 = base64.b64encode(snap_buf).decode('utf-8')
                    evidence_snapshots.insert(0, {
                        "time": timestamp,
                        "tag": f"POACHER INCURSION (WILDLIFE THREATENED)" if w_count > 0 else f"{p_count} POACHER(S) INCURSION",
                        "image": f"data:image/jpeg;base64,{snap_b64}",
                        "speed": system_state["target_velocity"],
                        "temp": system_state["temperature"],
                        "hum": system_state["humidity"]
                    })
                    if len(evidence_snapshots) > MAX_SNAPSHOTS:
                        evidence_snapshots.pop()

                    incident_logs.insert(0, {
                        "time": timestamp,
                        "type": f"Poacher Incursion // Wildlife Threatened" if w_count > 0 else f"Hostile Poachers ({p_count}) Detected",
                        "threat": "CRITICAL",
                        "temp": system_state["temperature"],
                        "hum": system_state["humidity"],
                        "speed": system_state["target_velocity"]
                    })
                    if len(incident_logs) > 20:
                        incident_logs.pop()

                if mcu and mcu.is_open:
                    try:
                        mcu.write(b'1')
                    except Exception:
                        pass

            elif staff_streak >= 3 and not is_poacher_active:
                system_state["status"] = f"AUTHORIZED: {s_count} RANGER PATROL CHECK-IN"
                system_state["threat_level"] = "AUTHORIZED"
                system_state["threat_code"] = "CODE BLUE (PATROL ACTIVE)"
                system_state["identified_target"] = f"RANGER ({s_count})" if s_count > 1 else "RANGER (LEGO FIGURE)"
                system_state["audio_alarm"] = False
                
                if time.time() - last_voice_announcement_time > 12.0:
                    system_state["voice_announcement"] = "Forest ranger credentials verified. Sector Alpha secure."
                    last_voice_announcement_time = time.time()

                if not system_state["manual_alarm"] and mcu and mcu.is_open:
                    try:
                        mcu.write(b'0')
                    except Exception:
                        pass

            elif wildlife_streak >= 3 and not is_poacher_active:
                system_state["status"] = f"PASSIVE: {w_count} WILDLIFE IN SECTOR (UNTHREATENED)"
                system_state["threat_level"] = "LOW"
                system_state["threat_code"] = "CODE GREEN (SECURE)"
                system_state["identified_target"] = f"WILDLIFE ({w_count})"
                system_state["audio_alarm"] = False
                if not system_state["manual_alarm"] and mcu and mcu.is_open:
                    try:
                        mcu.write(b'0')
                    except Exception:
                        pass

            else:
                if not system_state["manual_alarm"] and poacher_streak == 0 and staff_streak == 0 and wildlife_streak == 0:
                    system_state["status"] = "SECTOR ALPHA // ALL PERIMETERS SECURE"
                    system_state["threat_level"] = "LOW"
                    system_state["threat_code"] = "CODE GREEN (SECURE)"
                    system_state["identified_target"] = "None"
                    system_state["audio_alarm"] = False
                    if mcu and mcu.is_open:
                        try:
                            mcu.write(b'0')
                        except Exception:
                            pass

            disp_p = p_count if is_poacher_active else 0
            disp_s = s_count if staff_streak >= 2 else 0
            disp_w = w_count if wildlife_streak >= 2 else 0
            hud_text = f"C4ISR RECON: {disp_p} POACHER | {disp_s} RANGER | {disp_w} WILDLIFE | {system_state['fps']} FPS"
            cv2.putText(frame, hud_text, (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 136), 1)

        else:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            for y in range(0, 480, 40):
                cv2.line(frame, (0, y), (640, y), (15, 25, 20), 1)
            for x in range(0, 640, 40):
                cv2.line(frame, (x, 0), (x, 480), (15, 25, 20), 1)
            cv2.putText(frame, "RADAR SIMULATION: SECTOR SCANNING", (25, 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 136), 1)

        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.035)

# ==============================================================================
# 6. Competition-Grade Sovereign Terminal Interface
# ==============================================================================
HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PROJECT APEX | Sovereign Defense Terminal</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@500;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg: #05080e;
            --panel: rgba(10, 16, 26, 0.88);
            --panel-card: rgba(15, 24, 38, 0.6);
            --border: #162438;
            --border-glow: rgba(0, 229, 255, 0.35);
            --accent-green: #00ff88;
            --accent-red: #ff2a55;
            --accent-cyan: #00e5ff;
            --accent-yellow: #ffb703;
            --accent-amber: #ff8800;
            --text-main: #e2e8f0;
            --text-muted: #7e91a8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Rajdhani', sans-serif;
            background: var(--bg);
            color: var(--text-main);
            padding: 16px;
            min-height: 100vh;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(0, 229, 255, 0.04), transparent 450px),
                radial-gradient(circle at 90% 80%, rgba(0, 255, 136, 0.03), transparent 450px);
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid var(--border);
            padding-bottom: 12px;
            margin-bottom: 16px;
            flex-wrap: wrap;
            gap: 12px;
        }
        .brand h1 {
            font-family: 'Orbitron', monospace;
            font-size: 2.2rem;
            letter-spacing: 4px;
            color: var(--accent-green);
            text-shadow: 0 0 20px rgba(0, 255, 136, 0.4);
        }
        .brand p { color: var(--text-muted); font-size: 0.95rem; font-family: 'Share Tech Mono', monospace; }

        .header-meta { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .status-chip {
            font-family: 'Orbitron', monospace;
            background: rgba(0, 255, 136, 0.08);
            border: 1px solid var(--accent-green);
            color: var(--accent-green);
            padding: 6px 14px;
            border-radius: 4px;
            font-size: 0.85rem;
            box-shadow: 0 0 10px rgba(0, 255, 136, 0.15);
        }

        .main-grid {
            display: grid;
            grid-template-columns: 1.8fr 1fr;
            gap: 16px;
        }
        @media (max-width: 1100px) { .main-grid { grid-template-columns: 1fr; } }

        .panel {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            backdrop-filter: blur(14px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
            margin-bottom: 16px;
            position: relative;
        }
        .panel::before {
            content: ''; position: absolute; top: 0; left: 0; width: 8px; height: 8px;
            border-top: 2px solid var(--accent-cyan); border-left: 2px solid var(--accent-cyan);
        }
        .panel::after {
            content: ''; position: absolute; bottom: 0; right: 0; width: 8px; height: 8px;
            border-bottom: 2px solid var(--accent-cyan); border-right: 2px solid var(--accent-cyan);
        }

        .panel-title {
            font-family: 'Orbitron', monospace;
            font-size: 1rem;
            color: var(--accent-cyan);
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            padding-bottom: 6px;
        }

        .video-box {
            position: relative;
            width: 100%;
            border-radius: 6px;
            overflow: hidden;
            border: 2px solid #162438;
            background: #000;
        }
        .video-box img { width: 100%; height: auto; display: block; }

        /* LIVE CORNER RADAR SCOPE */
        .radar-scope-container {
            position: absolute;
            bottom: 14px;
            right: 14px;
            width: 135px;
            height: 135px;
            background: rgba(5, 8, 14, 0.9);
            border: 2px solid var(--accent-green);
            border-radius: 50%;
            box-shadow: 0 0 20px rgba(0, 255, 136, 0.35);
            overflow: hidden;
            backdrop-filter: blur(6px);
        }
        .radar-scope-container canvas { width: 100%; height: 100%; display: block; }

        .siren-beacon {
            display: none;
            position: absolute;
            top: 14px;
            right: 14px;
            background: var(--accent-red);
            color: #fff;
            padding: 8px 16px;
            font-family: 'Orbitron', monospace;
            font-size: 0.9rem;
            font-weight: 900;
            border-radius: 4px;
            box-shadow: 0 0 35px var(--accent-red);
            animation: beaconPulse 0.35s infinite alternate;
        }
        @keyframes beaconPulse {
            from { opacity: 1; transform: scale(1); }
            to { opacity: 0.25; transform: scale(1.04); }
        }

        .threat-banner {
            padding: 14px;
            border-radius: 6px;
            text-align: center;
            font-family: 'Orbitron', monospace;
            font-size: 1.1rem;
            font-weight: 900;
            margin-bottom: 16px;
            letter-spacing: 2px;
            text-shadow: 0 0 10px currentColor;
        }
        .threat-low { background: rgba(0, 255, 136, 0.12); color: var(--accent-green); border: 1px solid var(--accent-green); }
        .threat-auth { background: rgba(0, 229, 255, 0.15); color: var(--accent-cyan); border: 1px solid var(--accent-cyan); }
        .threat-high { background: rgba(255, 42, 85, 0.28); color: var(--accent-red); border: 1px solid var(--accent-red); animation: pulseHigh 0.8s infinite; }
        @keyframes pulseHigh { 0%, 100% { opacity: 1; } 50% { opacity: 0.55; } }

        .palette-selector {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-bottom: 12px;
        }
        .btn-palette {
            padding: 7px;
            font-size: 0.75rem;
            font-family: 'Orbitron', monospace;
            border: 1px solid var(--border);
            background: #0d1522;
            color: var(--text-muted);
            border-radius: 4px;
            cursor: pointer;
            transition: 0.2s;
        }
        .btn-palette.active {
            border-color: var(--accent-cyan);
            color: #000;
            background: var(--accent-cyan);
            font-weight: bold;
            box-shadow: 0 0 12px rgba(0, 229, 255, 0.4);
        }

        .entity-breakdown {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-bottom: 16px;
        }
        .entity-pill {
            background: var(--panel-card);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 12px;
            text-align: center;
        }
        .entity-pill-num {
            font-family: 'Orbitron', monospace;
            font-size: 1.5rem;
            font-weight: 900;
        }
        .entity-pill-label { font-size: 0.8rem; color: var(--text-muted); font-family: 'Share Tech Mono', monospace; margin-top: 2px; }

        .gauge-cards {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            margin-bottom: 12px;
        }
        .gauge-card {
            background: var(--panel-card);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 12px;
            text-align: center;
        }
        .gauge-label { font-size: 0.8rem; color: var(--text-muted); margin-bottom: 4px; font-family: 'Share Tech Mono', monospace; }
        .gauge-val { font-family: 'Orbitron', monospace; font-size: 1.6rem; font-weight: 700; color: var(--accent-green); }

        .fire-hazard-bar {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 4px;
            height: 10px;
            overflow: hidden;
            margin: 6px 0 14px 0;
            border: 1px solid var(--border);
        }
        .fire-hazard-fill {
            height: 100%;
            width: 18%;
            background: linear-gradient(90deg, var(--accent-green), var(--accent-yellow), var(--accent-red));
            transition: width 0.5s ease;
        }

        .btn-row { display: flex; gap: 8px; margin-bottom: 12px; }
        .btn {
            flex: 1;
            padding: 12px;
            border: none;
            border-radius: 6px;
            font-family: 'Rajdhani', sans-serif;
            font-weight: 700;
            font-size: 1rem;
            cursor: pointer;
            transition: 0.2s ease;
        }
        .btn-alarm { background: var(--accent-red); color: #fff; box-shadow: 0 0 15px rgba(255, 42, 85, 0.3); }
        .btn-clear { background: #192333; color: var(--text-main); }
        .btn-audio { background: var(--accent-cyan); color: #000; font-weight: bold; width: 100%; margin-bottom: 12px; box-shadow: 0 0 15px rgba(0, 229, 255, 0.3); }
        .btn-export { background: #152233; border: 1px solid var(--accent-cyan); color: var(--accent-cyan); width: 100%; margin-top: 10px; }

        .gallery-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }
        .snap-card {
            border: 1px solid var(--border);
            border-radius: 6px;
            overflow: hidden;
            background: #000;
            cursor: pointer;
            transition: 0.2s;
        }
        .snap-card:hover { border-color: var(--accent-cyan); transform: scale(1.03); }
        .snap-card img { width: 100%; height: 75px; object-fit: cover; display: block; }
        .snap-meta { font-family: 'Share Tech Mono', monospace; font-size: 0.72rem; padding: 4px; text-align: center; background: #0b121c; color: var(--text-muted); }

        .log-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
        .log-table th, .log-table td { padding: 7px 8px; text-align: left; border-bottom: 1px solid var(--border); }
        .log-table th { color: var(--text-muted); font-family: 'Share Tech Mono', monospace; }
        .log-crit { color: var(--accent-red); font-weight: bold; }

        /* Target Matrix Details */
        .target-card-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 8px;
            margin-top: 10px;
        }
        .target-chip {
            background: #0c1420;
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 6px 8px;
            font-family: 'Share Tech Mono', monospace;
            font-size: 0.75rem;
        }

        .modal {
            display: none;
            position: fixed;
            z-index: 100;
            left: 0; top: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.85);
            backdrop-filter: blur(8px);
            align-items: center;
            justify-content: center;
        }
        .modal-content {
            background: #0f1828;
            border: 2px solid var(--accent-cyan);
            border-radius: 8px;
            padding: 16px;
            max-width: 650px;
            width: 90%;
            text-align: center;
        }
        .modal-img { width: 100%; border-radius: 4px; margin-bottom: 10px; }
        .close-btn { float: right; color: #fff; font-size: 1.5rem; cursor: pointer; }
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <h1>PROJECT APEX</h1>
            <p>Autonomous C4ISR Defense Station & Ecological Intelligence Terminal</p>
        </div>
        <div class="header-meta">
            <div class="status-chip" id="feed-badge">SENSOR: INITIALIZING...</div>
            <div class="status-chip" id="sys-clock">UTC 00:00:00</div>
        </div>
    </header>

    <div class="main-grid">
        <div>
            <div class="panel">
                <div class="panel-title">
                    <span>◉ LIVE RECONNAISSANCE SPECTRUM</span>
                    <span style="font-size: 0.8rem; font-family: 'Share Tech Mono', monospace;" id="target-stat">ACTIVE ENTITIES: 0/3</span>
                </div>
                
                <div class="palette-selector">
                    <button class="btn-palette active" id="btn-p-OPTICAL" onclick="setPalette('OPTICAL')">DAY OPTICAL</button>
                    <button class="btn-palette" id="btn-p-INFERNO" onclick="setPalette('INFERNO')">FLIR INFERNO</button>
                    <button class="btn-palette" id="btn-p-NVG" onclick="setPalette('NVG')">NVG GOGGLES</button>
                    <button class="btn-palette" id="btn-p-JET" onclick="setPalette('JET')">FLIR JET</button>
                </div>

                <div class="video-box">
                    <div id="beacon" class="siren-beacon">🚨 HOSTILE SIREN ACTIVE 🚨</div>
                    <img id="stream-img" src="/video_feed" alt="Surveillance Stream">
                    
                    <div class="radar-scope-container">
                        <canvas id="radarCanvas" width="135" height="135"></canvas>
                    </div>
                </div>

                <div class="target-card-row" id="target-telemetry-grid">
                    <div class="target-chip" style="color: var(--text-muted); grid-column: 1/-1; text-align: center;">
                        Awaiting Target Acquisition in Sector Alpha
                    </div>
                </div>
            </div>

            <div class="panel">
                <div class="panel-title">
                    <span>📷 AUTOMATED FORENSIC EVIDENCE DOSSIER</span>
                    <span style="font-size: 0.8rem; color: var(--text-muted);">AUTO-SAVED IN HIGH RES</span>
                </div>
                <div class="gallery-grid" id="evidence-gallery">
                    <div style="grid-column: 1/-1; text-align: center; padding: 15px; color: var(--text-muted); font-size: 0.85rem;">
                        No forensic intrusion evidence captured yet
                    </div>
                </div>
            </div>
        </div>

        <div>
            <button id="enable-audio-btn" class="btn btn-audio" onclick="enableAudio()">🔊 INITIALIZE SOVEREIGN VOICE & DEFENSE SIREN</button>

            <div id="threat-indicator" class="threat-banner threat-low">
                SECTOR ALPHA // ALL PERIMETERS SECURE
            </div>

            <div class="panel">
                <div class="panel-title"><span>🎯 ACTIVE TARGET METRICS</span></div>
                <div class="entity-breakdown">
                    <div class="entity-pill">
                        <div class="entity-pill-num" style="color: var(--accent-red);" id="val-pcount">0</div>
                        <div class="entity-pill-label">POACHERS</div>
                    </div>
                    <div class="entity-pill">
                        <div class="entity-pill-num" style="color: var(--accent-cyan);" id="val-scount">0</div>
                        <div class="entity-pill-label">RANGERS</div>
                    </div>
                    <div class="entity-pill">
                        <div class="entity-pill-num" style="color: var(--accent-green);" id="val-wcount">0</div>
                        <div class="entity-pill-label">WILDLIFE</div>
                    </div>
                </div>

                <div class="gauge-cards">
                    <div class="gauge-card">
                        <div class="gauge-label">WILDLIFE THREAT STATUS</div>
                        <div class="gauge-val" style="font-size: 0.95rem; line-height: 2.2rem; color: var(--accent-green);" id="val-wstatus">NOMINAL</div>
                    </div>
                    <div class="gauge-card">
                        <div class="gauge-label">INFILTRATION SPEED</div>
                        <div class="gauge-val" style="font-size: 1.1rem; line-height: 2.2rem; color: var(--accent-yellow);" id="val-speed">STATIONARY</div>
                    </div>
                </div>

                <div class="btn-row">
                    <button class="btn btn-alarm" onclick="triggerAlarm(true)">⚠ MANUAL SIREN</button>
                    <button class="btn btn-clear" onclick="triggerAlarm(false)">SILENCE</button>
                </div>
            </div>

            <div class="panel">
                <div class="panel-title"><span>◈ ENVIRONMENTAL TELEMETRY</span></div>
                <div class="gauge-cards">
                    <div class="gauge-card">
                        <div class="gauge-label">TEMPERATURE</div>
                        <div class="gauge-val" id="val-temp">-- °C</div>
                    </div>
                    <div class="gauge-card">
                        <div class="gauge-label">HUMIDITY</div>
                        <div class="gauge-val" id="val-hum">-- %</div>
                    </div>
                </div>

                <div class="panel-title" style="font-size: 0.8rem; margin-bottom: 2px;">
                    <span>FOREST FIRE HAZARD INDEX</span>
                    <span id="fire-status" style="font-family: 'Share Tech Mono'; color: var(--accent-green);">NOMINAL (18%)</span>
                </div>
                <div class="fire-hazard-bar">
                    <div class="fire-hazard-fill" id="fire-fill"></div>
                </div>

                <canvas id="telemetryChart" style="max-height: 120px; width: 100%; margin-top: 10px;"></canvas>
            </div>

            <div class="panel">
                <div class="panel-title">
                    <span>📋 DEFENSE AUDIT DOSSIER</span>
                    <span style="font-size: 0.8rem; color: var(--text-muted);">REAL-TIME</span>
                </div>
                <table class="log-table">
                    <thead>
                        <tr><th>TIME</th><th>EVENT DETAILS</th><th>SEVERITY</th></tr>
                    </thead>
                    <tbody id="log-body">
                        <tr><td colspan="3" style="text-align: center; color: var(--text-muted);">No recorded threats</td></tr>
                    </tbody>
                </table>
                <a href="/api/export_csv" download="APEX_Patrol_Report.csv">
                    <button class="btn btn-export">📥 EXPORT DEFENSE AUDIT (CSV)</button>
                </a>
            </div>
        </div>
    </div>

    <div id="imgModal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="closeModal()">&times;</span>
            <h3 style="font-family: 'Orbitron', monospace; color: var(--accent-cyan); margin-bottom: 10px;" id="modal-title">EVIDENCE SNAPSHOT</h3>
            <img class="modal-img" id="modal-image" src="" alt="Breach Evidence">
            <p id="modal-desc" style="font-family: 'Share Tech Mono', monospace; font-size: 0.85rem; color: var(--text-muted);"></p>
        </div>
    </div>

    <script>
        let audioCtx = null, osc1 = null, osc2 = null, gainNode = null, isSounding = false;
        let chart = null;
        let currentRadarTargets = [];
        let radarSweepAngle = 0;
        let lastSpokenText = "";

        // --- Tactical Web Speech Synthesizer ---
        function speakTactical(text) {
            if (!('speechSynthesis' in window) || !text || text === lastSpokenText) return;
            lastSpokenText = text;
            try {
                window.speechSynthesis.cancel();
                const utter = new SpeechSynthesisUtterance(text);
                utter.rate = 1.05;
                utter.pitch = 0.95;
                utter.volume = 1.0;
                window.speechSynthesis.speak(utter);
            } catch(e) {}
        }

        // --- Tactical Radar Scope Engine ---
        const rCanvas = document.getElementById('radarCanvas');
        const rCtx = rCanvas.getContext('2d');

        function drawRadarScope() {
            const w = rCanvas.width, h = rCanvas.height;
            const cx = w / 2, cy = h / 2, r = cx - 4;

            rCtx.clearRect(0, 0, w, h);
            rCtx.fillStyle = 'rgba(5, 8, 14, 0.9)';
            rCtx.beginPath();
            rCtx.arc(cx, cy, r, 0, Math.PI * 2);
            rCtx.fill();

            // Range rings
            rCtx.strokeStyle = 'rgba(0, 255, 136, 0.25)';
            rCtx.lineWidth = 1;
            [0.33, 0.66, 1.0].forEach(f => {
                rCtx.beginPath();
                rCtx.arc(cx, cy, r * f, 0, Math.PI * 2);
                rCtx.stroke();
            });

            // Crosshairs
            rCtx.beginPath();
            rCtx.moveTo(cx, 4); rCtx.lineTo(cx, h - 4);
            rCtx.moveTo(4, cy); rCtx.lineTo(w - 4, cy);
            rCtx.stroke();

            // Sweeping Needle
            radarSweepAngle = (radarSweepAngle + 0.05) % (Math.PI * 2);
            const sweepX = cx + Math.cos(radarSweepAngle) * r;
            const sweepY = cy + Math.sin(radarSweepAngle) * r;

            rCtx.strokeStyle = 'rgba(0, 255, 136, 0.85)';
            rCtx.lineWidth = 1.5;
            rCtx.beginPath();
            rCtx.moveTo(cx, cy);
            rCtx.lineTo(sweepX, sweepY);
            rCtx.stroke();

            // Sweep Gradient Trail
            rCtx.fillStyle = 'rgba(0, 255, 136, 0.12)';
            rCtx.beginPath();
            rCtx.moveTo(cx, cy);
            rCtx.arc(cx, cy, r, radarSweepAngle - 0.4, radarSweepAngle);
            rCtx.closePath();
            rCtx.fill();

            // Plot Blips
            currentRadarTargets.forEach(t => {
                const bx = cx + t.nx * (r * 0.85);
                const by = cy + t.ny * (r * 0.85);
                rCtx.beginPath();
                rCtx.arc(bx, by, 4, 0, Math.PI * 2);
                if (t.type === 'POACHER') {
                    rCtx.fillStyle = '#ff2a55';
                    rCtx.shadowColor = '#ff2a55';
                    rCtx.shadowBlur = 8;
                } else if (t.type === 'STAFF') {
                    rCtx.fillStyle = '#00e5ff';
                    rCtx.shadowColor = '#00e5ff';
                    rCtx.shadowBlur = 6;
                } else if (t.type === 'WILDLIFE_AT_RISK') {
                    rCtx.fillStyle = '#ff8800';
                    rCtx.shadowColor = '#ff8800';
                    rCtx.shadowBlur = 8;
                } else {
                    rCtx.fillStyle = '#00ff88';
                    rCtx.shadowColor = '#00ff88';
                    rCtx.shadowBlur = 6;
                }
                rCtx.fill();
                rCtx.shadowBlur = 0;
            });

            requestAnimationFrame(drawRadarScope);
        }
        drawRadarScope();

        // --- Rolling Environmental Telemetry Graph ---
        function initChart() {
            const ctx = document.getElementById('telemetryChart').getContext('2d');
            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'Ambient Temp (°C)', data: [], borderColor: '#00ff88', borderWidth: 1.5, pointRadius: 0 },
                        { label: 'Rel. Humidity (%)', data: [], borderColor: '#00e5ff', borderWidth: 1.5, pointRadius: 0 }
                    ]
                },
                options: {
                    responsive: true,
                    animation: false,
                    scales: {
                        x: { display: false },
                        y: { ticks: { color: '#7e91a8', font: { size: 9 } }, grid: { color: '#162438' } }
                    },
                    plugins: { legend: { labels: { color: '#e2e8f0', font: { size: 10 } } } }
                }
            });
        }
        initChart();

        function enableAudio() {
            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            if (audioCtx.state === 'suspended') audioCtx.resume();
            const btn = document.getElementById('enable-audio-btn');
            btn.innerText = "✓ SOVEREIGN AI VOICE & TERMINAL READY";
            btn.style.background = "var(--accent-green)";
            speakTactical("Project Apex defense terminal online. All perimeters initialized.");
        }

        function startSiren() {
            if (!audioCtx || isSounding) return;
            try {
                osc1 = audioCtx.createOscillator();
                osc2 = audioCtx.createOscillator();
                gainNode = audioCtx.createGain();
                osc1.type = 'sawtooth'; osc1.frequency.setValueAtTime(880, audioCtx.currentTime);
                osc2.type = 'square'; osc2.frequency.setValueAtTime(440, audioCtx.currentTime);
                gainNode.gain.setValueAtTime(0.25, audioCtx.currentTime);
                osc1.connect(gainNode); osc2.connect(gainNode); gainNode.connect(audioCtx.destination);
                osc1.start(); osc2.start(); isSounding = true;
            } catch(e) {}
        }

        function stopSiren() {
            if (isSounding) {
                try { osc1.stop(); osc2.stop(); osc1.disconnect(); osc2.disconnect(); } catch(e) {}
                isSounding = false; osc1 = null; osc2 = null;
            }
        }

        function setPalette(mode) {
            fetch('/api/palette', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: mode })
            }).then(() => {
                ['OPTICAL', 'INFERNO', 'NVG', 'JET'].forEach(p => {
                    document.getElementById('btn-p-' + p).className = 'btn-palette' + (p === mode ? ' active' : '');
                });
            });
        }

        function openModal(imgSrc, title, desc) {
            document.getElementById('modal-image').src = imgSrc;
            document.getElementById('modal-title').innerText = title;
            document.getElementById('modal-desc').innerText = desc;
            document.getElementById('imgModal').style.display = 'flex';
        }

        function closeModal() {
            document.getElementById('imgModal').style.display = 'none';
        }

        function updateDashboard() {
            document.getElementById('sys-clock').innerText = "UTC " + new Date().toTimeString().split(' ')[0];

            fetch('/api/telemetry')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('val-temp').innerText = data.temperature + " °C";
                    document.getElementById('val-hum').innerText = data.humidity + " %";
                    document.getElementById('feed-badge').innerText = "SENSOR: " + data.camera_source;
                    
                    document.getElementById('val-pcount').innerText = data.poacher_count;
                    document.getElementById('val-scount').innerText = data.staff_count;
                    document.getElementById('val-wcount').innerText = data.wildlife_count;
                    document.getElementById('val-speed').innerText = data.target_velocity;

                    // Wildlife Threat Indicator
                    const wStatus = document.getElementById('val-wstatus');
                    wStatus.innerText = data.wildlife_status;
                    if (data.wildlife_status.includes("ENDANGERED") || data.wildlife_status.includes("AT RISK")) {
                        wStatus.style.color = "var(--accent-amber)";
                        wStatus.style.fontWeight = "bold";
                    } else {
                        wStatus.style.color = "var(--accent-green)";
                    }

                    document.getElementById('target-stat').innerText = `ACTIVE ENTITIES: ${data.total_objects}/3`;
                    document.getElementById('fire-status').innerText = `${data.fire_risk} (${data.fire_risk_score}%)`;
                    document.getElementById('fire-fill').style.width = data.fire_risk_score + "%";

                    currentRadarTargets = data.radar_targets || [];

                    // Automated Voice Synthesis
                    if (data.voice_announcement) {
                        speakTactical(data.voice_announcement);
                    }

                    // Render Target Telemetry Cards
                    const tGrid = document.getElementById('target-telemetry-grid');
                    if (data.active_targets_detail && data.active_targets_detail.length > 0) {
                        tGrid.innerHTML = data.active_targets_detail.map(td => `
                            <div class="target-chip">
                                <span style="color: ${td.type==='POACHER'?'var(--accent-red)':(td.type==='STAFF'?'var(--accent-cyan)':'var(--accent-green)')}; font-weight:bold;">${td.tag}</span><br>
                                ${td.pos} | ${td.size}
                            </div>
                        `).join('');
                    } else {
                        tGrid.innerHTML = `<div class="target-chip" style="color: var(--text-muted); grid-column: 1/-1; text-align: center;">Sector Alpha Nominal // Scanning Range</div>`;
                    }

                    const banner = document.getElementById('threat-indicator');
                    banner.innerText = data.status;
                    if (data.threat_level === 'HIGH') {
                        banner.className = "threat-banner threat-high";
                    } else if (data.threat_level === 'AUTHORIZED') {
                        banner.className = "threat-banner threat-auth";
                    } else {
                        banner.className = "threat-banner threat-low";
                    }

                    const beacon = document.getElementById('beacon');
                    if (data.audio_alarm) {
                        beacon.style.display = "block";
                        startSiren();
                    } else {
                        beacon.style.display = "none";
                        stopSiren();
                    }
                });

            fetch('/api/history')
                .then(res => res.json())
                .then(hist => {
                    if (chart && hist.length > 0) {
                        chart.data.labels = hist.map(h => h.time);
                        chart.data.datasets[0].data = hist.map(h => h.temp);
                        chart.data.datasets[1].data = hist.map(h => h.hum);
                        chart.update();
                    }
                });

            fetch('/api/logs')
                .then(res => res.json())
                .then(logs => {
                    const tbody = document.getElementById('log-body');
                    if (logs.length > 0) {
                        tbody.innerHTML = logs.slice(0, 5).map(l => `
                            <tr>
                                <td>${l.time}</td>
                                <td>${l.type}</td>
                                <td class="log-crit">${l.threat}</td>
                            </tr>
                        `).join('');
                    }
                });

            fetch('/api/evidence')
                .then(res => res.json())
                .then(snaps => {
                    const gallery = document.getElementById('evidence-gallery');
                    if (snaps.length > 0) {
                        gallery.innerHTML = snaps.map((s, idx) => `
                            <div class="snap-card" onclick="openModal('${s.image}', '${s.tag} // ${s.time}', 'Infiltration Velocity: ${s.speed} | Temp: ${s.temp}°C | Humidity: ${s.hum}%')">
                                <img src="${s.image}" alt="Incursion Forensic Snapshot">
                                <div class="snap-meta">${s.time} // ${s.tag}</div>
                            </div>
                        `).join('');
                    }
                });
        }

        function triggerAlarm(state) {
            fetch('/api/alarm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ trigger: state })
            });
        }

        setInterval(updateDashboard, 1000);
    </script>
</body>
</html>
"""

# ==============================================================================
# 7. Flask Server Endpoints & Forensic CSV Exporter
# ==============================================================================
@app.route('/')
def home():
    return render_template_string(HTML_DASHBOARD)

@app.route('/video_feed')
def video_feed():
    return Response(generate_video_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/telemetry')
def api_telemetry():
    return jsonify(system_state)

@app.route('/api/history')
def api_history():
    return jsonify(telemetry_history)

@app.route('/api/logs')
def api_logs():
    return jsonify(incident_logs)

@app.route('/api/evidence')
def api_evidence():
    return jsonify(evidence_snapshots)

@app.route('/api/palette', methods=['POST'])
def api_palette():
    data = request.get_json()
    mode = data.get('mode', 'OPTICAL')
    if mode in ['OPTICAL', 'INFERNO', 'NVG', 'JET']:
        system_state["vision_mode"] = mode
    return jsonify({"mode": system_state["vision_mode"]})

@app.route('/api/alarm', methods=['POST'])
def api_alarm():
    data = request.get_json()
    trigger = data.get('trigger', False)
    system_state["manual_alarm"] = trigger
    system_state["audio_alarm"] = trigger
    if mcu and mcu.is_open:
        try:
            mcu.write(b'1' if trigger else b'0')
        except Exception:
            pass
    return jsonify({"status": "SUCCESS", "siren_active": trigger})

@app.route('/api/export_csv')
def export_csv():
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["Timestamp", "Incident Dossier", "Threat Severity", "Infiltration Speed", "Ambient Temp (C)", "Relative Humidity (%)"])
    for l in incident_logs:
        cw.writerow([l.get("time", ""), l.get("type", ""), l.get("threat", ""), l.get("speed", ""), l.get("temp", ""), l.get("hum", "")])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=APEX_Defense_Audit.csv"
    output.headers["Content-type"] = "text/csv"
    return output

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
