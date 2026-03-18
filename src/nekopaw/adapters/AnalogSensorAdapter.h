#pragma once

#include <Arduino.h>

#if defined(ESP32)
#include <driver/adc.h>
#endif

#include "nekopaw/providers/SensorProvider.h"

namespace nekopaw {

class AnalogSensorAdapter : public SensorProvider {
public:
  struct Config {
    uint8_t pin = 0;
    const char* id = nullptr;
    const char* type = "voltage";
    const char* unit = "V";
    const char* description = nullptr;
    uint8_t adcResolutionBits = 12;
    uint8_t sampleCount = 9;
    uint16_t sampleDelayMs = 5;
    float multiplier = 1.0f;
  };

  explicit AnalogSensorAdapter(const Config& config) : config_(config) {}

  Info info() const override {
    Info result;
    result.id = config_.id;
    result.type = config_.type;
    result.unit = config_.unit;
    result.description = config_.description;
    return result;
  }

  Reading read() override {
    beginIfNeeded();

    Reading result;
    const uint32_t millivolts = readMillivoltsFiltered();
    if (millivolts == 0) {
      result.valid = false;
      result.timestamp = millis();
      return result;
    }

    result.value = static_cast<float>(millivolts) / 1000.0f;
    result.valid = true;
    result.timestamp = millis();
    return result;
  }

private:
  static uint16_t clampU16(uint32_t value) {
    return value > UINT16_MAX ? UINT16_MAX : static_cast<uint16_t>(value);
  }

  static void insertionSort(uint16_t* values, size_t count) {
    for (size_t i = 1; i < count; ++i) {
      const uint16_t key = values[i];
      size_t j = i;
      while (j > 0 && values[j - 1] > key) {
        values[j] = values[j - 1];
        --j;
      }
      values[j] = key;
    }
  }

  static uint16_t smooth(uint16_t previous, uint16_t next) {
    if (previous == 0) {
      return next;
    }
    return clampU16((static_cast<uint32_t>(previous) * 3U + static_cast<uint32_t>(next)) / 4U);
  }

  void beginIfNeeded() {
    if (started_) {
      return;
    }

#if defined(ESP32)
    analogReadResolution(config_.adcResolutionBits);
    analogSetAttenuation(ADC_11db);
#endif
    pinMode(config_.pin, INPUT);
    started_ = true;
  }

  uint32_t readMillivoltsFiltered() {
    (void)analogReadMilliVolts(config_.pin);
    delay(2);

    uint16_t samples[16] = {};
    const uint8_t sampleCount = config_.sampleCount == 0 ? 1 : min<uint8_t>(config_.sampleCount, 16);
    size_t count = 0;

    for (uint8_t i = 0; i < sampleCount; ++i) {
      const int adcMillivolts = analogReadMilliVolts(config_.pin);
      if (adcMillivolts > 0) {
        const float scaled = static_cast<float>(adcMillivolts) * config_.multiplier;
        samples[count++] = clampU16(static_cast<uint32_t>(scaled + 0.5f));
      }
      delay(config_.sampleDelayMs);
    }

    if (count == 0) {
      return filteredMillivolts_;
    }

    insertionSort(samples, count);
    filteredMillivolts_ = smooth(filteredMillivolts_, samples[count / 2]);
    return filteredMillivolts_;
  }

  Config config_;
  bool started_ = false;
  uint16_t filteredMillivolts_ = 0;
};

} // namespace nekopaw
