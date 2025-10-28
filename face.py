from ultralytics import YOLO
import streamlit as st
import cv2
import face_recognition
import numpy as np
import os
from datetime import datetime
import pandas as pd
from PIL import Image
import requests
from math import radians, sin, cos, sqrt, atan2

# ----------------------- Configuration -----------------------
TRAIN_DIR = "Training_images"
CAPTURED_DIR = "Captured_Images"
LOG_FILE = "Log_Data.csv"
YOLO_MODEL_PATH = r"C:\Users\Hp\Desktop\intern\l\runs\detect\n_version_4_75.pt"

os.makedirs(TRAIN_DIR, exist_ok=True)
os.makedirs(CAPTURED_DIR, exist_ok=True)

if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w") as f:
        f.write("Name,LoginTime,Status,Distance(m)\n")

# ----------------------- Helper Functions -----------------------
def find_encodings(images):
    encodings = []
    for img in images:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        faces = face_recognition.face_encodings(img)
        if faces:
            encodings.append(faces[0])
    return encodings

def load_training_data():
    images, names = [], []
    for file in os.listdir(TRAIN_DIR):
        img_path = os.path.join(TRAIN_DIR, file)
        img = cv2.imread(img_path)
        if img is not None:
            images.append(img)
            names.append(os.path.splitext(file)[0])
    return images, names

def log_attendance(name, status, distance):
    now = datetime.now()
    with open(LOG_FILE, "a") as f:
        f.write(f"{name},{now.strftime('%H:%M:%S')},{status},{distance:.1f}\n")

# ----------------------- Geofencing -----------------------
OFFICE_LAT, OFFICE_LON = 12.9719, 77.5937  # Example coords (Bellary)
RADIUS = 150  # in meters

def get_user_location():
    try:
        res = requests.get("https://ipinfo.io/json").json()
        lat, lon = map(float, res["loc"].split(","))
        return lat, lon
    except:
        return None, None

def is_within_geofence(user_lat, user_lon):
    R = 6371000  # Earth radius (m)
    dlat = radians(user_lat - OFFICE_LAT)
    dlon = radians(user_lon - OFFICE_LON)
    a = sin(dlat / 2) ** 2 + cos(radians(OFFICE_LAT)) * cos(radians(user_lat)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = R * c
    return distance <= RADIUS, distance

# ----------------------- Streamlit UI -----------------------
st.set_page_config(layout="wide")
st.title("acs_pro")

with st.sidebar:
    st.header("⚙️ Controls & Uploads")

    # Upload Training Images
    uploaded_files = st.file_uploader("📤 Upload Training Images", type=["jpg", "png"], accept_multiple_files=True)
    if uploaded_files:
        for uploaded in uploaded_files:
            img = Image.open(uploaded)
            img.save(os.path.join(TRAIN_DIR, uploaded.name))
        st.success("✅ Training images uploaded!")

    # Reset Log
    if st.button("🧹 Reset Log File"):
        with open(LOG_FILE, "w") as f:
            f.write("Name,LoginTime,Status,Distance(m)\n")
        st.success("✅ Log file reset successfully.")

    # Preview Training Images
    st.markdown("🖼️ **Training Image Previews**")
    for file in os.listdir(TRAIN_DIR):
        st.image(os.path.join(TRAIN_DIR, file), width=100, caption=file)

# ----------------------- Attendance Section -----------------------
st.subheader("📸 Take Attendance")
start_attendance = st.button("▶️ Start Attendance Capture")

if start_attendance:
    st.info("Starting camera for YOLO + Face Recognition...")

    known_imgs, known_names = load_training_data()
    if not known_imgs:
        st.error("⚠️ Please upload training images first.")
        st.stop()

    known_encodings = find_encodings(known_imgs)
    model = YOLO(YOLO_MODEL_PATH)
    cap = cv2.VideoCapture(0)
    frame_placeholder = st.empty()
    recognized_name = None

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # YOLO for Spoof Detection
        results = model(frame, stream=True)
        valid_yolo = any(model.names[int(cls)] == "real"
                         for r in results
                         for cls in (r.boxes.cls.tolist() if r.boxes else []))

        if valid_yolo:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            faces = face_recognition.face_locations(rgb_frame)
            encodes = face_recognition.face_encodings(rgb_frame, faces)

            for encode_face, face_loc in zip(encodes, faces):
                matches = face_recognition.compare_faces(known_encodings, encode_face)
                face_dist = face_recognition.face_distance(known_encodings, encode_face)
                if len(face_dist) == 0:
                    continue
                best_match = np.argmin(face_dist)
                if matches[best_match]:
                    recognized_name = known_names[best_match].upper()
                    y1, x2, y2, x1 = face_loc
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, recognized_name, (x1 + 6, y1 - 6),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                    break

        frame_placeholder.image(frame, channels="BGR")

        if recognized_name:
            st.success(f"✅ {recognized_name} recognized! Checking location...")
            cap.release()

            lat, lon = get_user_location()
            if lat and lon:
                inside, dist = is_within_geofence(lat, lon)
                now = datetime.now().strftime("%H:%M:%S")

                if inside:
                    st.success(f"✅ Within Geofence ({dist:.1f} m) — Attendance marked at {now}")
                    log_attendance(recognized_name, "Present", dist)
                else:
                    st.error(f"🚫 Outside permitted area ({dist:.1f} m) — Attendance not recorded.")
                    log_attendance(recognized_name, "Outside", dist)
            else:
                st.error("⚠️ Could not fetch location.")
            break

    cap.release()
    frame_placeholder.empty()

# ----------------------- Log Display -----------------------
st.subheader("📋 Attendance Log Summary")
try:
    df = pd.read_csv(LOG_FILE)
    if not df.empty:
        st.dataframe(df)
        st.bar_chart(df.groupby("Name")["Distance(m)"].mean())
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Log CSV", csv, "Log_Data.csv", "text/csv")
    else:
        st.info("No log data available yet.")
except Exception as e:
    st.warning(f"Error reading log data: {e}")
