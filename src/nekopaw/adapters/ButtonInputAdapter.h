#pragma once

#include <Arduino.h>
#include <OneButton.h>

#include "nekopaw/providers/InputProvider.h"

namespace nekopaw {

class ButtonInputAdapter : public InputProvider {
public:
  struct Config {
    uint8_t pin = 0;
    const char* id = nullptr;
    const char* type = "button";
    bool activeLow = true;
    bool pullup = true;
    uint16_t debounceMs = 50;
    uint16_t clickMs = 400;
    uint16_t pressMs = 800;
  };

  explicit ButtonInputAdapter(const Config& config) : config_(config) {}

  Info info() const override {
    Info result;
    result.id = config_.id;
    result.type = config_.type;
    return result;
  }

  Event poll() override {
    if (queuedCount_ == 0) {
      return Event::None;
    }

    const Event result = queuedEvents_[queueHead_];
    queueHead_ = static_cast<uint8_t>((queueHead_ + 1U) % kQueueCapacity);
    --queuedCount_;
    return result;
  }

  void tick() override {
    beginIfNeeded();
    button_.tick();
    updateReleaseState();
  }

private:
  static constexpr uint8_t kQueueCapacity = 8;

  static void onClick(void* context) { static_cast<ButtonInputAdapter*>(context)->enqueue(Event::Click); }
  static void onDoubleClick(void* context) { static_cast<ButtonInputAdapter*>(context)->enqueue(Event::DoubleClick); }
  static void onLongPress(void* context) { static_cast<ButtonInputAdapter*>(context)->enqueue(Event::LongPress); }

  void beginIfNeeded() {
    if (started_) {
      return;
    }

    const uint8_t mode = config_.pullup ? INPUT_PULLUP : INPUT;
    button_.setup(config_.pin, mode, config_.activeLow);
    button_.setDebounceMs(config_.debounceMs);
    button_.setClickMs(config_.clickMs);
    button_.setPressMs(config_.pressMs);
    button_.attachClick(onClick, this);
    button_.attachDoubleClick(onDoubleClick, this);
    button_.attachLongPressStart(onLongPress, this);

    const bool currentPressed = isPressed();
    rawPressed_ = currentPressed;
    debouncedPressed_ = currentPressed;
    lastRawChangeAtMs_ = millis();
    started_ = true;
  }

  bool isPressed() const {
    const int pressedLevel = config_.activeLow ? LOW : HIGH;
    return digitalRead(config_.pin) == pressedLevel;
  }

  void updateReleaseState() {
    const bool currentPressed = isPressed();
    const uint32_t nowMs = millis();

    if (currentPressed != rawPressed_) {
      rawPressed_ = currentPressed;
      lastRawChangeAtMs_ = nowMs;
    }

    if (debouncedPressed_ == rawPressed_) {
      return;
    }

    if (nowMs < lastRawChangeAtMs_ || (nowMs - lastRawChangeAtMs_) < config_.debounceMs) {
      return;
    }

    debouncedPressed_ = rawPressed_;
    if (!debouncedPressed_) {
      enqueue(Event::Release);
    }
  }

  void enqueue(Event event) {
    if (event == Event::None) {
      return;
    }

    if (queuedCount_ == kQueueCapacity) {
      queueHead_ = static_cast<uint8_t>((queueHead_ + 1U) % kQueueCapacity);
      --queuedCount_;
    }

    const uint8_t tail = static_cast<uint8_t>((queueHead_ + queuedCount_) % kQueueCapacity);
    queuedEvents_[tail] = event;
    ++queuedCount_;
  }

  Config config_;
  OneButton button_;
  bool started_ = false;
  bool rawPressed_ = false;
  bool debouncedPressed_ = false;
  uint32_t lastRawChangeAtMs_ = 0;
  Event queuedEvents_[kQueueCapacity] = {};
  uint8_t queueHead_ = 0;
  uint8_t queuedCount_ = 0;
};

} // namespace nekopaw
