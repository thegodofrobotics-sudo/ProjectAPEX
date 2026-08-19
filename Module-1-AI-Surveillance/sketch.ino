#include <DHT.h>

// ==========================================
// 1. Pin Definitions & Constants
// ==========================================
#define DHTPIN 2        // DHT11 Data line connected to Digital Pin D2
#define DHTTYPE DHT11   // Sensor Type: DHT11
#define ALARM_PIN 8     // Hardware Piezo Buzzer / Relay on Pin D8
#define LED_PIN 13      // Built-in Visual Status LED on Pin D13

// ==========================================
// 2. Object Instantiation
// ==========================================
DHT dht(DHTPIN, DHTTYPE);
unsigned long lastSensorRead = 0;

void setup() {
  // Initialize UART serial bridge communicating with Qualcomm Linux MPU
  Serial.begin(9600);
  
  // Initialize DHT11 sensor
  dht.begin();

  // Configure hardware actuator output pins
  pinMode(ALARM_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);

  // Default state: Alarm and LED turned OFF
  digitalWrite(ALARM_PIN, LOW);
  digitalWrite(LED_PIN, LOW);

  // Send startup acknowledgment
  Serial.println(F("[APEX-MCU] STM32 Real-Time Core Initialized."));
}

void loop() {
  // --------------------------------------------------------------------------
  // 1. Process Real-Time Actuation Commands from Linux Vision AI (app.py)
  // --------------------------------------------------------------------------
  if (Serial.available() > 0) {
    char cmd = Serial.read();

    if (cmd == '1') {
      // Intruder/Poacher Detected: Trigger Hardware Siren & Status LED
      digitalWrite(ALARM_PIN, HIGH);
      digitalWrite(LED_PIN, HIGH);
    } 
    else if (cmd == '0') {
      // Sector Clear / Silenced: Deactivate Siren & Status LED
      digitalWrite(ALARM_PIN, LOW);
      digitalWrite(LED_PIN, LOW);
    }
  }

  // --------------------------------------------------------------------------
  // 2. Read & Stream Environmental Telemetry Every 2000 ms (2 seconds)
  // --------------------------------------------------------------------------
  if (millis() - lastSensorRead >= 2000) {
    lastSensorRead = millis();

    float temp = dht.readTemperature();
    float hum = dht.readHumidity();

    // Verify valid non-NaN readings before transmitting
    if (!isnan(temp) && !isnan(hum)) {
      // Transmission Protocol Format: "DATA:<temperature>,<humidity>\n"
      Serial.print(F("DATA:"));
      Serial.print(temp, 1);
      Serial.print(F(","));
      Serial.println(hum, 1);
    }
  }
}
