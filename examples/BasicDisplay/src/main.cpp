// NekoPaw 🐾 — AI-IoT Bridge for ESP32
// Minimal skeleton sketch — compiles but does nothing useful yet.
// Phase 1 will replace this with a working example.

#include <Arduino.h>
#include <NekoPaw.h>

static nekopaw::NekoPaw paw;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("NekoPaw skeleton — waiting for Phase 1 implementation");
  (void)paw.begin();
}

void loop() {
  paw.loop();
  delay(1000);
}
