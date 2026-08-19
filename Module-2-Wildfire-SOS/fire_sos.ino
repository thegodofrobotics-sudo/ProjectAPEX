#include <SoftwareSerial.h>

#include <TinyGPS++.h>



// GSM on pins 7,8 | GPS on pins 3,4

SoftwareSerial gsmSerial(8, 7);   // RX, TX

SoftwareSerial gpsSerial(3, 4);   // RX, TX

TinyGPSPlus gps;



#define MQ135_PIN A0

#define FLAME_PIN 2

#define BUZZER_PIN 9



int smokeThreshold = 400;   // recalibrate after wiring the AOUT divider

bool alertSent = false;



String phoneNumber = "+91XXXXXXXXXX"; // your number



float latitude = 0.0;

float longitude = 0.0;



void setup() {

  Serial.begin(9600);

  gsmSerial.begin(9600);

  gpsSerial.begin(9600);



  pinMode(FLAME_PIN, INPUT);

  pinMode(BUZZER_PIN, OUTPUT);



  Serial.println("System Initializing...");

  delay(2000);



  gsmSerial.println("AT");

  delay(1000);

  gsmSerial.println("AT+CMGF=1"); // SMS text mode

  delay(1000);



  Serial.println("System Ready");

}



void loop() {

  int smokeValue = analogRead(MQ135_PIN);

  int flameStatus = digitalRead(FLAME_PIN); // usually LOW = flame detected



  Serial.print("Smoke: ");

  Serial.print(smokeValue);

  Serial.print(" | Flame: ");

  Serial.println(flameStatus);



  if (smokeValue > smokeThreshold || flameStatus == LOW) {

    digitalWrite(BUZZER_PIN, HIGH);



    if (!alertSent) {

      getGPSLocation();

      sendSMSAlert(smokeValue, flameStatus);

      makePhoneCall();

      alertSent = true;

    }

  } else {

    digitalWrite(BUZZER_PIN, LOW);

    alertSent = false; // reset once fire clears

  }



  delay(1000);

}



void getGPSLocation() {

  unsigned long start = millis();

  while (millis() - start < 3000) { // read GPS for 3 sec

    while (gpsSerial.available() > 0) {

      if (gps.encode(gpsSerial.read())) {

        if (gps.location.isValid()) {

          latitude = gps.location.lat();

          longitude = gps.location.lng();

        }

      }

    }

  }

}



void sendSMSAlert(int smokeValue, int flameStatus) {

  String message = "FIRE ALERT!\n";

  message += "Smoke Level: " + String(smokeValue) + "\n";

  message += "Flame Detected: " + String(flameStatus == LOW ? "YES" : "NO") + "\n";

  message += "Location: http://maps.google.com/maps?q=";

  message += String(latitude, 6) + "," + String(longitude, 6);



  gsmSerial.println("AT+CMGS=\"" + phoneNumber + "\"");

  delay(1000);

  gsmSerial.print(message);

  delay(500);

  gsmSerial.write(26); // Ctrl+Z to send SMS

  delay(5000);



  Serial.println("SMS Sent!");

}



void makePhoneCall() {

  Serial.println("Calling...");

  gsmSerial.println("ATD" + phoneNumber + ";"); // semicolon = voice call

  delay(20000); // let it ring for 20 sec

  gsmSerial.println("ATH"); // hang up

  delay(1000);

  Serial.println("Call Ended");

}
