// Tank Drive Control with Slew-Rate Limiting for Stepper Motors
// Arduino IDE (e.g. UNO, Mega, Leonardo)
// Responds "ack" to "hello" and accepts "L,R" commands over Serial.

#include <Arduino.h>

// Motor Pins
const uint8_t LEFT_STEP_PIN  = 10;
const uint8_t LEFT_DIR_PIN   = 11;
const uint8_t RIGHT_STEP_PIN = 14;
const uint8_t RIGHT_DIR_PIN  = 15;

const float STEP_PULSE_DURATION_US = 1.0f;  // Step pulse width in μs

// Speed Limits (full steps per second)
const float MAX_SPEED_LEFT  = 1500.0f;
const float MAX_SPEED_RIGHT = 1500.0f;

// Slew-Rate Limiting (steps/sec per millisecond)
const float ACCEL_RATE = 50.0f;
const float DECEL_RATE = 100.0f;

// Motor state
float leftCurrentSpeed  = 0, leftTargetSpeed  = 0;
float rightCurrentSpeed = 0, rightTargetSpeed = 0;
unsigned long leftLastStepUs  = 0;
unsigned long rightLastStepUs = 0;
unsigned long lastUpdateMs    = 0;

// Serial input buffer
String inputString;
bool   stringComplete = false;

void setup() {
  Serial.begin(115200);
  while (!Serial) { ; }
  pinMode(LEFT_STEP_PIN,  OUTPUT);
  pinMode(LEFT_DIR_PIN,   OUTPUT);
  pinMode(RIGHT_STEP_PIN, OUTPUT);
  pinMode(RIGHT_DIR_PIN,  OUTPUT);
  digitalWrite(LEFT_STEP_PIN,  LOW);
  digitalWrite(RIGHT_STEP_PIN, LOW);

  leftLastStepUs  = micros();
  rightLastStepUs = micros();
  lastUpdateMs    = millis();

  Serial.println("Tank Drive Ready. Send 'L,R' (e.g. 500,-500) or 'hello'.");
}

void loop() {
  // --- Read Serial into inputString ---
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      stringComplete = true;
    } else if (c != '\r') {
      inputString += c;
    }
  }

  // --- Process complete line ---
  if (stringComplete) {
    String s = inputString;
    s.trim();
    s.toLowerCase();
    if (s == "hello") {
      Serial.println("ack");
    } else {
      int comma = s.indexOf(',');
      if (comma >= 0) {
        float lt = s.substring(0, comma).toFloat();
        float rt = s.substring(comma + 1).toFloat();
        leftTargetSpeed  = constrain(lt, -MAX_SPEED_LEFT,  MAX_SPEED_LEFT);
        rightTargetSpeed = -constrain(rt, -MAX_SPEED_RIGHT, MAX_SPEED_RIGHT);
        Serial.print("Set Target → L:");
        Serial.print(leftTargetSpeed);
        Serial.print("  R:");
        Serial.println(rightTargetSpeed);
      } else {
        Serial.println("Err: use 'L,R' or 'hello'");
      }
    }
    inputString = "";
    stringComplete = false;
  }

  // --- Slew-Rate Limiting ---
  unsigned long nowMs = millis();
  float dtMs = nowMs - lastUpdateMs;
  lastUpdateMs = nowMs;

  // Left motor
  if (leftCurrentSpeed < leftTargetSpeed) {
    bool accelPhase = (leftCurrentSpeed < 0 && leftTargetSpeed >= 0)
                   || (leftCurrentSpeed >= 0 && leftTargetSpeed >= leftCurrentSpeed);
    float rate = accelPhase ? ACCEL_RATE : DECEL_RATE;
    leftCurrentSpeed += rate * dtMs;
    if (leftCurrentSpeed > leftTargetSpeed)
      leftCurrentSpeed = leftTargetSpeed;
  } else if (leftCurrentSpeed > leftTargetSpeed) {
    bool accelPhase = (leftCurrentSpeed > 0 && leftTargetSpeed <= 0)
                   || (leftCurrentSpeed <= 0 && leftTargetSpeed <= leftCurrentSpeed);
    float rate = accelPhase ? ACCEL_RATE : DECEL_RATE;
    leftCurrentSpeed -= rate * dtMs;
    if (leftCurrentSpeed < leftTargetSpeed)
      leftCurrentSpeed = leftTargetSpeed;
  }

  // Right motor
  if (rightCurrentSpeed < rightTargetSpeed) {
    bool accelPhase = (rightCurrentSpeed < 0 && rightTargetSpeed >= 0)
                   || (rightCurrentSpeed >= 0 && rightTargetSpeed >= rightCurrentSpeed);
    float rate = accelPhase ? ACCEL_RATE : DECEL_RATE;
    rightCurrentSpeed += rate * dtMs;
    if (rightCurrentSpeed > rightTargetSpeed)
      rightCurrentSpeed = rightTargetSpeed;
  } else if (rightCurrentSpeed > rightTargetSpeed) {
    bool accelPhase = (rightCurrentSpeed > 0 && rightTargetSpeed <= 0)
                   || (rightCurrentSpeed <= 0 && rightTargetSpeed <= rightCurrentSpeed);
    float rate = accelPhase ? ACCEL_RATE : DECEL_RATE;
    rightCurrentSpeed -= rate * dtMs;
    if (rightCurrentSpeed < rightTargetSpeed)
      rightCurrentSpeed = rightTargetSpeed;
  }

  // --- Generate Step Pulses ---
  unsigned long nowUs = micros();

  // Left
  if (fabs(leftCurrentSpeed) > 0.0f) {
    unsigned long delayUs =
      (unsigned long)(1000000.0f / fabs(leftCurrentSpeed));
    if (nowUs - leftLastStepUs >= delayUs) {
      digitalWrite(LEFT_DIR_PIN,
                   leftCurrentSpeed >= 0 ? HIGH : LOW);
      digitalWrite(LEFT_STEP_PIN, HIGH);
      delayMicroseconds((int)STEP_PULSE_DURATION_US);
      digitalWrite(LEFT_STEP_PIN, LOW);
      leftLastStepUs = micros();
    }
  }

  // Right
  if (fabs(rightCurrentSpeed) > 0.0f) {
    unsigned long delayUs =
      (unsigned long)(1000000.0f / fabs(rightCurrentSpeed));
    if (nowUs - rightLastStepUs >= delayUs) {
      digitalWrite(RIGHT_DIR_PIN,
                   rightCurrentSpeed >= 0 ? HIGH : LOW);
      digitalWrite(RIGHT_STEP_PIN, HIGH);
      delayMicroseconds((int)STEP_PULSE_DURATION_US);
      digitalWrite(RIGHT_STEP_PIN, LOW);
      rightLastStepUs = micros();
    }
  }

  delay(1); // yield to background tasks
}