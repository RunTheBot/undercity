#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>

const char* ssid     = "Archer";
const char* password = "qgrj3146";

// joystick pins
const int VRxPin = 3;
const int VRyPin = 5;
const int swPin  = 7;

// calibration
int centerX, centerY;
int maxRangeX, maxRangeY;

// websocket client
WebSocketsClient webSocket;

void webSocketEvent(WStype_t type, uint8_t* payload, size_t len) {
  switch (type) {
    case WStype_DISCONNECTED:
      Serial.println("[WSc] Disconnected");
      break;
    case WStype_CONNECTED:
      Serial.print  ("[WSc] Connected to ");
      Serial.println((char*)payload);
      break;
    case WStype_TEXT:
      Serial.print  ("[WSc] Received: ");
      Serial.println((char*)payload);
      break;
    default: break;
  }
}

void calibrateJoystick() {
  const int samples = 50;
  long sumX = 0, sumY = 0;
  Serial.println("Calibrating joystick...");
  for (int i = 0; i < samples; i++) {
    sumX += analogRead(VRxPin);
    sumY += analogRead(VRyPin);
    delay(20);
  }
  centerX    = sumX / samples;
  centerY    = sumY / samples;
  maxRangeX  = max(centerX, 4095 - centerX);
  maxRangeY  = max(centerY, 4095 - centerY);
  Serial.printf("CenterX=%d CenterY=%d\n", centerX, centerY);
  Serial.printf("maxRangeX=%d maxRangeY=%d\n",
                maxRangeX, maxRangeY);
}

void setup() {
  Serial.begin(115200);
  pinMode(swPin, INPUT_PULLUP);

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi up, IP: ");
  Serial.println(WiFi.localIP());

  webSocket.begin("192.168.8.224", 6969, "/");
  webSocket.onEvent(webSocketEvent);

  calibrateJoystick();
}

void loop() {
  webSocket.loop();

  // raw reads
  int rawX = analogRead(VRxPin);
  int rawY = analogRead(VRyPin);

  // relative (invert Y so up = positive)
  float relX = rawX - centerX;
  float relY = centerY - rawY;

  // normalize to [-1,1]
  float normX = constrain(relX / maxRangeX, -1.0, 1.0);
  float normY = constrain(relY / maxRangeY, -1.0, 1.0);

  // tank mix
  float leftF  = normY + normX;
  float rightF = normY - normX;

  leftF  = constrain(leftF,  -1.0, 1.0);
  rightF = constrain(rightF, -1.0, 1.0);

  int leftVal  = round(leftF  * 750);
  int rightVal = round(rightF * 750);

  // send "L,R"
  char msg[16];
  snprintf(msg, sizeof(msg), "%d,%d", leftVal, rightVal);
  webSocket.sendTXT(msg);

  Serial.printf(
    "L=%4d R=%4d rawX=%4d rawY=%4d\n",
    leftVal, rightVal, rawX, rawY
  );

  delay(50);
}