#pragma once

#include <stdint.h>

namespace nekopaw {

/// Abstract sensor interface.
/// Implement this for each sensor you want to expose to AI.
class SensorProvider {
public:
  virtual ~SensorProvider() = default;

  struct Info {
    const char* id = nullptr;          // "battery", "dht22_temp"
    const char* type = nullptr;        // "temperature", "voltage", "humidity"
    const char* unit = nullptr;        // "°C", "V", "%RH"
    const char* description = nullptr; // human-readable
  };
  virtual Info info() const = 0;

  struct Reading {
    float value = 0;
    bool valid = false;
    uint32_t timestamp = 0; // millis()
  };
  virtual Reading read() = 0;
};

} // namespace nekopaw
