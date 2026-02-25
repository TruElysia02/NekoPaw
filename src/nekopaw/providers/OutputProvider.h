#pragma once

#include <stdint.h>

// Forward declaration — ArduinoJson
class JsonObject;

namespace nekopaw {

/// Abstract output (LED/buzzer/relay) interface.
class OutputProvider {
public:
  virtual ~OutputProvider() = default;

  struct Info {
    const char* id = nullptr;   // "led_rgb", "buzzer"
    const char* type = nullptr; // "led", "buzzer", "relay"
  };
  virtual Info info() const = 0;

  /// Execute a command described by JSON params.
  /// Example LED:    { "action":"set", "color":"green", "duration":3000 }
  /// Example Buzzer: { "action":"beep", "frequency":1000, "duration":200, "count":2 }
  virtual bool execute(const JsonObject& params) = 0;

  /// Non-blocking update (PWM animations, timed-off, etc.). Called from NekoPaw::loop().
  virtual void tick() = 0;
};

} // namespace nekopaw
