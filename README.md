# 🛡️ Project APEX — Autonomous Wildlife Defense Ecosystem

**Project APEX** (Anti-Poaching Environmental eXperience) is an integrated, modular security and environmental monitoring system designed for forest reserves:

* **👁️ Module 1: AI Anti-Poaching Surveillance** — Edge-AI computer vision running on OpenCV/Python with a Logitech C270 HD camera mounted on a 360° continuous pan servo. Distinguishes poachers, rangers, and wildlife with a local Flask dashboard (Port 5000).
* **🔥 Module 2: Wildfire & Satellite SOS (Arduino UNO Q)** — Environmental hazard station using MQ-135 smoke and IR flame sensors. Automatically retrieves satellite coordinates via NEO-6M GPS and dispatches emergency SMS alerts with Google Maps links and phone calls via SIM800L GSM.
* **🚪 Module 3: 2FA Smart Security Gate (Arduino Mega 2560)** — Two-factor physical perimeter access control requiring an MFRC522 RFID badge and an R307S biometric fingerprint match before opening the barrier servo.
