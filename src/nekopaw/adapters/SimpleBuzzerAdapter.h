#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>

#include "nekopaw/providers/OutputProvider.h"

namespace nekopaw {

class SimpleBuzzerAdapter : public OutputProvider {
public:
  struct Config {
    uint8_t pin = 255;
    const char* id = "buzzer";
    const char* type = "buzzer";
    uint32_t defaultFrequency = 1000;
    uint32_t defaultDurationMs = 200;
    uint32_t defaultCount = 1;
    uint32_t gapMs = 120;
  };

  explicit SimpleBuzzerAdapter(const Config& config) : config_(config) {}

  Info info() const override {
    Info result;
    result.id = config_.id;
    result.type = config_.type;
    return result;
  }

  bool execute(ArduinoJson::JsonObjectConst params) override {
    String action = params["action"] | "";
    action.trim();
    action.toLowerCase();
    if (action != "beep") {
      return false;
    }

    uint32_t frequency = config_.defaultFrequency;
    uint32_t durationMs = config_.defaultDurationMs;
    uint32_t count = config_.defaultCount;
    if (!parsePositiveUint32(params["frequency"], frequency) || !parsePositiveUint32(params["duration"], durationMs) ||
        !parsePositiveUint32(params["count"], count)) {
      return false;
    }

    beginIfNeeded();
    stopTone();

    frequencyHz_ = frequency;
    toneDurationMs_ = durationMs;
    beepsRemaining_ = count;
    phase_ = Phase::Tone;
    phaseStartedAtMs_ = millis();
    tone(config_.pin, static_cast<unsigned int>(frequencyHz_), static_cast<unsigned long>(toneDurationMs_));
    return true;
  }

  void tick() override {
    beginIfNeeded();

    // Alternate between tone and silence so repeated beeps stay non-blocking.
    if (phase_ == Phase::Tone) {
      if ((millis() - phaseStartedAtMs_) < toneDurationMs_) {
        return;
      }

      noTone(config_.pin);
      if (beepsRemaining_ <= 1) {
        phase_ = Phase::Idle;
        beepsRemaining_ = 0;
        digitalWrite(config_.pin, LOW);
        return;
      }

      --beepsRemaining_;
      phase_ = Phase::Gap;
      phaseStartedAtMs_ = millis();
      return;
    }

    if (phase_ == Phase::Gap && (millis() - phaseStartedAtMs_) >= config_.gapMs) {
      phase_ = Phase::Tone;
      phaseStartedAtMs_ = millis();
      tone(config_.pin, static_cast<unsigned int>(frequencyHz_), static_cast<unsigned long>(toneDurationMs_));
    }
  }

private:
  enum class Phase : uint8_t {
    Idle = 0,
    Tone = 1,
    Gap = 2,
  };

  static bool parsePositiveUint32(ArduinoJson::JsonVariantConst value, uint32_t& outValue) {
    if (value.isNull()) {
      return outValue > 0;
    }

    if (value.is<uint32_t>()) {
      outValue = value.as<uint32_t>();
      return outValue > 0;
    }

    if (value.is<int32_t>()) {
      const int32_t signedValue = value.as<int32_t>();
      if (signedValue <= 0) {
        return false;
      }

      outValue = static_cast<uint32_t>(signedValue);
      return true;
    }

    return false;
  }

  void beginIfNeeded() {
    if (started_) {
      return;
    }

    pinMode(config_.pin, OUTPUT);
    digitalWrite(config_.pin, LOW);
    started_ = true;
  }

  void stopTone() {
    if (!started_) {
      return;
    }

    noTone(config_.pin);
    digitalWrite(config_.pin, LOW);
    phase_ = Phase::Idle;
    beepsRemaining_ = 0;
  }

  Config config_;
  bool started_ = false;
  Phase phase_ = Phase::Idle;
  uint32_t frequencyHz_ = 0;
  uint32_t toneDurationMs_ = 0;
  uint32_t phaseStartedAtMs_ = 0;
  uint32_t beepsRemaining_ = 0;
};

} // namespace nekopaw
