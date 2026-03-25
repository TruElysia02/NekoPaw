#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>

#include "nekopaw/providers/OutputProvider.h"

namespace nekopaw {

class RgbLedAdapter : public OutputProvider {
public:
  struct Config {
    uint8_t redPin = 255;
    uint8_t greenPin = 255;
    uint8_t bluePin = 255;
    const char* id = "led_rgb";
    const char* type = "led";
    bool activeLow = true;
  };

  explicit RgbLedAdapter(const Config& config) : config_(config) {}

  Info info() const override {
    Info result;
    result.id = config_.id;
    result.type = config_.type;
    return result;
  }

  bool execute(ArduinoJson::JsonObjectConst params) override {
    beginIfNeeded();

    String action = params["action"] | "";
    action.trim();
    action.toLowerCase();

    if (action == "set") {
      String colorName = params["color"] | "";
      ColorLevels color;
      if (!parseColor(colorName, color)) {
        return false;
      }

      uint32_t durationMs = 0;
      if (!parseOptionalUint32(params["duration"], durationMs)) {
        return false;
      }

      applyColor(color);
      if (durationMs > 0) {
        autoOffArmed_ = true;
        autoOffStartedAtMs_ = millis();
        autoOffDurationMs_ = durationMs;
      } else {
        autoOffArmed_ = false;
      }
      return true;
    }

    if (action == "off") {
      turnOff();
      return true;
    }

    return false;
  }

  void tick() override {
    beginIfNeeded();

    if (!autoOffArmed_) {
      return;
    }

    if ((millis() - autoOffStartedAtMs_) < autoOffDurationMs_) {
      return;
    }

    turnOff();
  }

private:
  struct ColorLevels {
    bool red = false;
    bool green = false;
    bool blue = false;
  };

  static bool parseOptionalUint32(ArduinoJson::JsonVariantConst value, uint32_t& outValue) {
    if (value.isNull()) {
      outValue = 0;
      return true;
    }

    if (value.is<uint32_t>()) {
      outValue = value.as<uint32_t>();
      return true;
    }

    if (value.is<int32_t>()) {
      const int32_t signedValue = value.as<int32_t>();
      if (signedValue < 0) {
        return false;
      }

      outValue = static_cast<uint32_t>(signedValue);
      return true;
    }

    return false;
  }

  static bool parseColor(String value, ColorLevels& color) {
    value.trim();
    value.toLowerCase();

    if (value == "off") {
      color = {};
      return true;
    }
    if (value == "red") {
      color.red = true;
      return true;
    }
    if (value == "green") {
      color.green = true;
      return true;
    }
    if (value == "blue") {
      color.blue = true;
      return true;
    }
    if (value == "yellow") {
      color.red = true;
      color.green = true;
      return true;
    }
    if (value == "cyan") {
      color.green = true;
      color.blue = true;
      return true;
    }
    if (value == "magenta") {
      color.red = true;
      color.blue = true;
      return true;
    }
    if (value == "white") {
      color.red = true;
      color.green = true;
      color.blue = true;
      return true;
    }

    return false;
  }

  void beginIfNeeded() {
    if (started_) {
      return;
    }

    pinMode(config_.redPin, OUTPUT);
    pinMode(config_.greenPin, OUTPUT);
    pinMode(config_.bluePin, OUTPUT);
    started_ = true;
    turnOff();
  }

  void writeChannel(uint8_t pin, bool on) {
    if (pin == 255) {
      return;
    }

    const uint8_t level = on ? (config_.activeLow ? LOW : HIGH) : (config_.activeLow ? HIGH : LOW);
    digitalWrite(pin, level);
  }

  void applyColor(const ColorLevels& color) {
    writeChannel(config_.redPin, color.red);
    writeChannel(config_.greenPin, color.green);
    writeChannel(config_.bluePin, color.blue);
  }

  void turnOff() {
    autoOffArmed_ = false;
    applyColor({});
  }

  Config config_;
  bool started_ = false;
  bool autoOffArmed_ = false;
  uint32_t autoOffStartedAtMs_ = 0;
  uint32_t autoOffDurationMs_ = 0;
};

} // namespace nekopaw
