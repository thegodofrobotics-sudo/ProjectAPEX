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

// --- GSM (SIM900A) HARDWARE SERIAL 2 ---
// SIM900A 5VT -> Arduino Mega Pin 17 (RX2)
// SIM900A 5VR -> Arduino Mega Pin 16 (TX2)
// SIM900A GND -> Arduino Mega GND (Common Ground)

// --- GSM PARAMETERS ---
const String TARGET_PHONE = "+1234567890";  // Replace with target mobile number with country code

// --- SCANNED RFID UIDS & USER NAMES ---
byte user1_UID[4] = {0x2C, 0x4A, 0x55, 0x4A}; // Person 1: ARNAV GUPTA (Fingerprint IDs: 1, 2, 3, 4)
byte user2_UID[4] = {0x33, 0x37, 0x1F, 0x17}; // Person 2: ADAMYA BHUSHAN (Fingerprint IDs: 5, 6, 7, 8)

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
int getUserIdFromFingerprint(int fpID);
void processAccess(int userId);
void triggerUnauthorizedAlarm(String reason);
void initGSM();
void sendSMS(String text);
void makeCall();

void setup() {
  Serial.begin(9600);   // USB Serial Monitor
  Serial1.begin(57600); // Hardware Serial 1 (R307/R307S Fingerprint)
  Serial2.begin(9600);  // Hardware Serial 2 (SIM900A GSM)

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
  gateServo.write(0); // Lock gate at initial position

  // 4. Verify Fingerprint Sensor Connection
  delay(1000);
  if (finger.verifyPassword()) {
    Serial.println("[SYSTEM] R307S Fingerprint Sensor Connected.");
  } else {
    Serial.println("[ERROR] R307S Sensor Not Detected! Check Mega Pins 18/19 and 5V/GND.");
  }

  // 5. Initialize SIM900A GSM Module
  initGSM();

  Serial.println("==============================================");
  Serial.println(" ARDUINO MEGA SECURITY SYSTEM READY ");
  Serial.println(" User 1: ARNAV GUPTA    | Enrolled IDs: 1, 2, 3, 4");
  Serial.println(" User 2: ADAMYA BHUSHAN | Enrolled IDs: 5, 6, 7, 8");
  Serial.println("==============================================");

  updateLCDDefault();
}

void loop() {
  // Check for an RFID Card Scan
  int authenticatedUser = checkRFID();

  // Unauthorized / Invalid RFID Card scanned
  if (authenticatedUser == -1) {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("INVALID CARD!");
    lcd.setCursor(0, 1);
    lcd.print("UNAUTHORIZED!");
    
    Serial.println("[SECURITY BREACH] Unregistered RFID card scanned!");
    triggerUnauthorizedAlarm("Unregistered RFID card scanned");
    updateLCDDefault();
    return;
  }

  // Valid RFID Card scanned -> Prompt for Fingerprint
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
      int rawFpID = checkFingerprint();
      
      // Case 1: Fingerprint detected & verified in memory
      if (rawFpID > 0) {
        int matchedUser = getUserIdFromFingerprint(rawFpID);

        if (matchedUser == authenticatedUser) {
          fpMatched = true;
          break; // Correct card + matching finger
        } else if (matchedUser > 0 && matchedUser != authenticatedUser) {
          // Card belongs to User A, but finger belongs to User B
          lcd.clear();
          lcd.setCursor(0, 0);
          lcd.print("ACCESS DENIED!");
          lcd.setCursor(0, 1);
          lcd.print("USER MISMATCH!");
          
          Serial.println("[ALERT] RFID and Fingerprint user mismatch!");
          triggerUnauthorizedAlarm("RFID & Fingerprint User Mismatch");
          updateLCDDefault();
          return;
        } else {
          // Finger is enrolled in flash but not mapped to User 1 or 2
          lcd.clear();
          lcd.setCursor(0, 0);
          lcd.print("ACCESS DENIED!");
          lcd.setCursor(0, 1);
          lcd.print("UNMAPPED FINGER!");
          
          Serial.println("[ALERT] Fingerprint ID not in 1-8 range!");
          triggerUnauthorizedAlarm("Unmapped Fingerprint Scanned");
          updateLCDDefault();
          return;
        }
      }
      
      // Case 2: Finger was placed, but NOT found in database (Intruder)
      else if (rawFpID == -1) {
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("ACCESS DENIED!");
        lcd.setCursor(0, 1);
        lcd.print("UNKNOWN FINGER!");
        
        Serial.println("[ALERT] Unregistered fingerprint scanned!");
        triggerUnauthorizedAlarm("Unregistered Fingerprint Scanned");
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

// Maps 8 enrolled fingerprint slots across User 1 and User 2
int getUserIdFromFingerprint(int fpID) {
  if (fpID >= 1 && fpID <= 4) {
    return 1; // Arnav Gupta (IDs 1, 2, 3, 4)
  } else if (fpID >= 5 && fpID <= 8) {
    return 2; // Adamya Bhushan (IDs 5, 6, 7, 8)
  }
  return 0; // Unrecognized slot ID
}

void updateLCDDefault() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("SYSTEM SECURED");
  lcd.setCursor(0, 1);
  lcd.print("ARN:" + String(arnav_Inside ? "IN " : "OUT") + " ADA:" + String(adamya_Inside ? "IN " : "OUT"));
}

// Read RFID Card
// Returns: 1 (User 1), 2 (User 2), -1 (Unauthorized card), 0 (No card present)
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
    user = -1; // Flagged as unauthorized card
  }

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
  return user;
}

// Optical Fingerprint check
// Returns: ID (1-127 if matched), -1 (Finger placed but not recognized), 0 (No finger placed)
int checkFingerprint() {
  uint8_t p = finger.getImage();
  if (p == FINGERPRINT_NOFINGER) return 0;
  if (p != FINGERPRINT_OK) return 0;

  p = finger.image2Tz();
  if (p != FINGERPRINT_OK) return 0;

  p = finger.fingerFastSearch();
  if (p == FINGERPRINT_OK) {
    Serial.print("[FP DETECTED] Matched Slot ID: #");
    Serial.print(finger.fingerID);
    Serial.print(" | Confidence Score: ");
    Serial.println(finger.confidence);

    if (finger.confidence >= 40) {
      return finger.fingerID;
    }
  } else if (p == FINGERPRINT_NOTFOUND) {
    return -1; // Finger detected but template not found in database
  }
  
  return 0;
}

void processAccess(int userId) {
  // 1. Open Servo Gate
  gateServo.write(90);

  // 2. Toggle occupancy state & format notification text
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

  // 3. Display status on LCD
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("ACCESS GRANTED!");
  lcd.setCursor(0, 1);
  lcd.print(shortName + " " + String(isInside ? "ENTERED" : "EXITED"));

  Serial.println("[SMS NOTIFICATION]: " + msg);
  sendSMS(msg);

  // Allow passage time (5 seconds)
  delay(5000);

  // 4. Lock Servo Gate
  gateServo.write(0);
  delay(1000);

  updateLCDDefault();
}

// Alarm & GSM Alert Function (Handles Buzzer, SMS, and Call)
void triggerUnauthorizedAlarm(String reason) {
  digitalWrite(BUZZER_PIN, HIGH);

  Serial.println("[ALARM TRIGGERED]: " + reason);
  
  // Send SMS Alert
  sendSMS("SECURITY ALERT: " + reason);
  
  // Make Phone Call Alert
  makeCall();

  delay(5000);
  digitalWrite(BUZZER_PIN, LOW);
}

void initGSM() {
  Serial.println("[GSM] Initializing SIM900A Module...");
  
  for (int i = 0; i < 4; i++) {
    Serial2.println("AT");
    delay(500);
  }

  Serial2.println("ATE0");              // Turn off local echo
  delay(500);
  Serial2.println("AT+CMGF=1");         // Set SMS text mode
  delay(500);
  Serial2.println("AT+CNMI=2,2,0,0,0"); // Direct SMS routing to UART
  delay(500);

  Serial.println("[GSM] SIM900A Ready.");
}

void sendSMS(String text) {
  Serial2.println("AT+CMGF=1");
  delay(300);
  Serial2.print("AT+CMGS=\"");
  Serial2.print(TARGET_PHONE);
  Serial2.println("\"");
  delay(500);
  Serial2.print(text);
  delay(500);
  Serial2.write(26); // ASCII 26 (CTRL+Z) sends SMS
  delay(4000);       // Wait for SIM900A transmission ACK
}

void makeCall() {
  Serial2.print("ATD");
  Serial2.print(TARGET_PHONE);
  Serial2.println(";");
  delay(10000); // Ring target for 10 seconds
  Serial2.println("ATH"); // Disconnect call
  delay(500);
}