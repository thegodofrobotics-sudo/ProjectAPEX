#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Adafruit_Fingerprint.h>
#include <Servo.h>

// --- I2C LCD CONFIGURATION ---
LiquidCrystal_I2C lcd(0x27, 16, 2); // Change address to 0x3F if 0x27 shows blank

// --- ARDUINO MEGA HARDWARE PINS ---
#define RFID_SS_PIN    53  // Mega Hardware SS Pin
#define RFID_RST_PIN   9
#define SERVO_PIN      6
#define BUZZER_PIN     8

// --- GSM PARAMETERS ---
const String TARGET_PHONE = "+1234567890";  // Replace with your target mobile number (with country code)

// --- SCANNED RFID UIDS & USER NAMES ---
byte user1_UID[4] = {0x2C, 0x4A, 0x55, 0x4A}; // Person 1: ARNAV GUPTA (Enrolled as Fingerprint ID 1)
byte user2_UID[4] = {0x33, 0x37, 0x1F, 0x17}; // Person 2: ADAMYA BHUSHAN (Enrolled as Fingerprint ID 2)

const String USER1_NAME = "ARNAV GUPTA";
const String USER2_NAME = "ADAMYA BHUSHAN";

// Occupancy State Trackers
bool arnav_Inside = false;
bool adamya_Inside = false;

// Hardware Objects
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);
Adafruit_Fingerprint finger = Adafruit_Fingerprint(&Serial1); // Hardware Serial1 (Pins 18 TX1, 19 RX1)
Servo gateServo;

// Function Prototypes
void updateLCDDefault();
int checkRFID();
int checkFingerprint();
void processAccess(int userId);
void triggerUnauthorizedAlarm(String reason);
void initGSM();
void sendSMS(String text);
void makeCall();

void setup() {
  Serial.begin(9600);   // USB Serial Monitor
  Serial1.begin(57600); // Hardware Serial 1 (R307S Fingerprint)
  Serial2.begin(9600);  // Hardware Serial 2 (SIM800L GSM)

  // 1. Initialize LCD
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print(" SYSTEM INITIAL ");
  lcd.setCursor(0, 1);
  lcd.print(" PLEASE WAIT... ");

  // 2. Initialize SPI & RFID
  SPI.begin();
  rfid.PCD_Init();

  // 3. Configure Output Pins
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  gateServo.attach(SERVO_PIN);
  gateServo.write(0); // Position gate locked (0 degrees)

  // 4. Verify Fingerprint Sensor Connection
  delay(1000);
  if (finger.verifyPassword()) {
    Serial.println("[SYSTEM] R307S Fingerprint Sensor Connected.");
  } else {
    Serial.println("[ERROR] R307S Sensor Not Detected! Check TX/RX on Pins 18/19.");
  }

  // 5. Initialize GSM Module
  initGSM();

  Serial.println("==============================================");
  Serial.println(" ARDUINO MEGA SECURITY SYSTEM READY ");
  Serial.println(" User 1: ARNAV GUPTA");
  Serial.println(" User 2: ADAMYA BHUSHAN");
  Serial.println("==============================================");

  updateLCDDefault();
}

void loop() {
  // Check for an RFID Card Scan
  int authenticatedUser = checkRFID();

  if (authenticatedUser > 0) {
    String currentName = (authenticatedUser == 1) ? USER1_NAME : USER2_NAME;
    
    lcd.clear();
    lcd.setCursor(0, 0);
    if (authenticatedUser == 1) {
      lcd.print("TAG: ARNAV GUPTA");
    } else {
      lcd.print("TAG: ADAMYA B.");
    }
    lcd.setCursor(0, 1);
    lcd.print("SCAN FINGERPRINT");

    Serial.print("[RFID SCAN SUCCESS] Matched User: ");
    Serial.println(currentName);

    // 10-Second Window to Scan Fingerprint
    unsigned long startTime = millis();
    bool fpMatched = false;

    while (millis() - startTime < 10000) {
      int fpID = checkFingerprint();
      
      if (fpID == authenticatedUser) {
        fpMatched = true;
        break;
      } else if (fpID > 0 && fpID != authenticatedUser) {
        // Fingerprint belonged to a different person than the scanned card
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("ACCESS DENIED!");
        lcd.setCursor(0, 1);
        lcd.print("ID MISMATCH!");
        
        Serial.println("[ALERT] RFID Card and Fingerprint ID mismatch!");
        triggerUnauthorizedAlarm("RFID & Fingerprint ID Mismatch");
        updateLCDDefault();
        return;
      }
    }

    if (fpMatched) {
      processAccess(authenticatedUser);
    } else {
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("SCAN TIMEOUT!");
      lcd.setCursor(0, 1);
      lcd.print("TRY AGAIN...");
      delay(2000);
      updateLCDDefault();
    }
  }
}

// Update LCD to show system ready state and occupancy status
void updateLCDDefault() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("SYSTEM SECURED");
  lcd.setCursor(0, 1);
  lcd.print("ARN:" + String(arnav_Inside ? "IN " : "OUT") + " ADA:" + String(adamya_Inside ? "IN " : "OUT"));
}

// Read RFID Card
int checkRFID() {
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    return 0;
  }

  int user = 0;
  if (memcmp(rfid.uid.uidByte, user1_UID, 4) == 0) {
    user = 1;
  } else if (memcmp(rfid.uid.uidByte, user2_UID, 4) == 0) {
    user = 2;
  } else {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("INVALID CARD!");
    lcd.setCursor(0, 1);
    lcd.print("UNAUTHORIZED!");
    
    Serial.println("[SECURITY BREACH] Unregistered RFID card scanned!");
    triggerUnauthorizedAlarm("Unregistered RFID card scanned");
    updateLCDDefault();
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  return user;
}

// Read Fingerprint from R307S via Hardware Serial1
int checkFingerprint() {
  uint8_t p = finger.getImage();
  if (p != FINGERPRINT_OK) return 0;

  p = finger.image2Tz();
  if (p != FINGERPRINT_OK) return 0;

  p = finger.fingerSearch();
  if (p == FINGERPRINT_OK) {
    return finger.fingerID; // Returns 1 or 2
  }
  return 0;
}

// Perform Gate Opening and SMS Sequence
void processAccess(int userId) {
  // 1. Open Servo Gate
  gateServo.write(90);

  // 2. Toggle state & format alert text
  String msg = "";
  String shortName = "";
  bool isInside = false;

  if (userId == 1) {
    arnav_Inside = !arnav_Inside;
    isInside = arnav_Inside;
    shortName = "ARNAV";
    msg = "ARNAV GUPTA is " + String(arnav_Inside ? "INSIDE" : "OUTSIDE");
  } else if (userId == 2) {
    adamya_Inside = !adamya_Inside;
    isInside = adamya_Inside;
    shortName = "ADAMYA";
    msg = "ADAMYA BHUSHAN is " + String(adamya_Inside ? "INSIDE" : "OUTSIDE");
  }

  // Display status on LCD
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("ACCESS GRANTED!");
  lcd.setCursor(0, 1);
  lcd.print(shortName + " " + String(isInside ? "ENTERED" : "EXITED"));

  Serial.println("[SMS NOTIFICATION]: " + msg);
  sendSMS(msg);

  // Delay for user passage (5 seconds)
  delay(5000);

  // 3. Lock Servo Gate
  gateServo.write(0);
  delay(1000);

  updateLCDDefault();
}

// Alarm & GSM Alert Function
void triggerUnauthorizedAlarm(String reason) {
  digitalWrite(BUZZER_PIN, HIGH);

  Serial.println("[ALARM TRIGGERED]: " + reason);
  
  sendSMS("SECURITY ALERT: " + reason);
  makeCall();

  delay(5000);
  digitalWrite(BUZZER_PIN, LOW);
}

// GSM Commands
void initGSM() {
  Serial2.println("AT");
  delay(1000);
  Serial2.println("AT+CMGF=1"); // Set SMS to Text Mode
  delay(1000);
}

void sendSMS(String text) {
  Serial2.println("AT+CMGF=1");
  delay(500);
  Serial2.print("AT+CMGS=\"");
  Serial2.print(TARGET_PHONE);
  Serial2.println("\"");
  delay(500);
  Serial2.print(text);
  delay(500);
  Serial2.write(26); // ASCII 26 (CTRL+Z) to send SMS
  delay(3000);
}

void makeCall() {
  Serial2.print("ATD");
  Serial2.print(TARGET_PHONE);
  Serial2.println(";");
  delay(10000); // Ring for 10 seconds
  Serial2.println("ATH"); // Hang up line
}
