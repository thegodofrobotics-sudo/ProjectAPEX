# 🛡️ Project APEX — Autonomous Wildlife Defense Ecosystem

**Project APEX** (Anti-Poaching Environmental eXperience) is an integrated, modular security and environmental monitoring system designed for forest reserves:

* **👁️ Module 1: AI Anti-Poaching Surveillance** — Edge-AI computer vision running on OpenCV/Python with a Logitech C270 HD camera mounted on a 360° continuous pan servo. Distinguishes poachers, rangers, and wildlife with a local Flask dashboard (Port 5000).
* **🔥 Module 2: Wildfire & Satellite SOS (Arduino UNO Q)** — Environmental hazard station using MQ-135 smoke and IR flame sensors. Automatically retrieves satellite coordinates via NEO-6M GPS and dispatches emergency SMS alerts with Google Maps links and phone calls via SIM800L GSM.
* **🚪 Module 3: 2FA Smart Security Gate (Arduino Mega 2560)** — Two-factor physical perimeter access control requiring an MFRC522 RFID badge and an R307S biometric fingerprint match before opening the barrier servo.

---

## 🔌 Hardware Circuit & Pin Connections

### **Module 1: AI Optical Surveillance (Logitech C270 + 360° Pan Base)**
* **Camera Interface:** Connected directly to Host SBC / PC USB-A / OTG Port (`/dev/video*`).
* **Pan Mechanism:** $360^\circ$ Continuous Rotation Servo controlled independently via Hardware Servo Tester Module on an external 5V rail.
* **Environmental Telemetry:** DHT11 Sensor connected to **Digital Pin D2** on the local controller.
* **Dashboard Output:** Flask Tactical Web HUD hosted on **HTTP Port 5000** (Live video stream & Web Audio API synthesized alert).

---

### **Module 2: Wildfire & Satellite SOS (Arduino UNO Q)**

| Component | Sensor Pin | Arduino UNO Q Pin | Description / Purpose |
| :--- | :--- | :--- | :--- |
| **MQ-135 / MQ-2 Smoke** | `AOUT / AO` | **Analog Pin A0** | Analog air quality / smoke density reading |
| **IR Optical Flame** | `DOUT / DO` | **Digital Pin D2** | Active-LOW open-flame detection interrupt |
| **NEO-6M Satellite GPS** | `TX` | **Digital Pin D3 (SoftRX)**| Receives NMEA satellite coordinates |
| **NEO-6M Satellite GPS** | `RX` | **Digital Pin D4 (SoftTX)**| GPS serial configuration line |
| **SIM800L Cellular GSM** | `TXD` | **Digital Pin D8 (SoftRX)**| Receives AT command responses |
| **SIM800L Cellular GSM** | `RXD` | **Digital Pin D7 (SoftTX)**| Transmits emergency SMS & Call AT commands |
| **LM2596 Buck Regulator** | `4.0V Out` | **SIM800L VCC** | Dedicated 4.0V (2A peak) supply (Common GND) |

---

### **Module 3: 2-Factor Smart Forest Gate (Arduino Mega 2560)**

| Component | Component Pin | Arduino Mega Pin | Operating Role / Voltage |
| :--- | :--- | :--- | :--- |
| **16x2 LCD Display** | `SDA` / `SCL` | **Pin 20 (SDA) / Pin 21 (SCL)** | 5V I2C status & countdown display |
| **MFRC522 RFID Reader** | `SDA (SS)` | **Pin 53 (SS)** | SPI Chip Select |
| **MFRC522 RFID Reader** | `SCK` | **Pin 52 (SCK)** | SPI Serial Clock |
| **MFRC522 RFID Reader** | `MOSI` | **Pin 51 (MOSI)** | Master Out Slave In |
| **MFRC522 RFID Reader** | `MISO` | **Pin 50 (MISO)** | Master In Slave Out |
| **MFRC522 RFID Reader** | `RST` | **Pin 9** | RFID Module Reset |
| **MFRC522 RFID Reader** | `VCC` | **3.3V ONLY** | ⚠️ Connect strictly to 3.3V rail |
| **R307S Fingerprint** | `TXD (Green)` | **Pin 19 (RX1)** | Hardware Serial1 RX (57600 baud) |
| **R307S Fingerprint** | `RXD (White)` | **Pin 18 (TX1)** | Hardware Serial1 TX |
| **Gate SIM800L GSM** | `TXD` | **Pin 17 (RX2)** | Hardware Serial2 RX (Gate entry SMS logs) |
| **Gate SIM800L GSM** | `RXD` | **Pin 16 (TX2)** | Hardware Serial2 TX |
| **Barrier Servo Motor** | `Signal (Orange)`| **Digital Pin 6 (PWM)** | Barrier arm rotation ($0^\circ$ to $90^\circ$) |

---

## ⚡ Power Supply Architecture
* **Main Supply:** 12V DC Adapter distributed to central power rails.
* **Arduino Mega / UNO Q:** Powered via onboard regulators / USB-C.
* **SIM800L GSM Modules:** Powered independently via **LM2596 DC-DC Buck Regulators** tuned to **4.0V (2A peak)**.
* **Common Ground:** All GND lines across all sensors, modules, and microcontrollers are tied to a single shared Ground Plane.
