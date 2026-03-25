#pragma once

#include <ArduinoJson.h>
#include <stddef.h>
#include <stdint.h>

#include "nekopaw/providers/InputProvider.h"

namespace nekopaw {

class NekoPaw;

class EventManager {
public:
  struct WatchRegistration {
    enum class Kind : uint8_t {
      Sensor = 1,
      Input = 2,
    };

    Kind kind = Kind::Sensor;
    const char* id = nullptr;
    const char* sourceId = nullptr;
    const char* message = nullptr;
    uint32_t cooldownSeconds = 0;

    enum class ConditionOp : uint8_t {
      None = 0,
      Gt = 1,
      Lt = 2,
      Gte = 3,
      Lte = 4,
      Eq = 5,
      Change = 6,
    };

    ConditionOp conditionOp = ConditionOp::None;
    bool hasConditionValue = false;
    float conditionValue = 0.0f;
    InputProvider::Event inputTrigger = InputProvider::Event::None;
  };

  EventManager(size_t maxEventQueue, size_t maxWatches);

  bool begin();
  void tick(NekoPaw& paw);
  void handleInputEvent(size_t inputIndex, InputProvider::Event event, uint32_t nowSeconds);

  bool upsertWatch(const WatchRegistration& registration, NekoPaw& paw, String& errorMessage, const char*& errorCode);
  bool removeWatch(const char* id, String& errorMessage, const char*& errorCode);

  void appendWatches(ArduinoJson::JsonArray watches) const;
  void drainEvents(ArduinoJson::JsonArray events, size_t& remaining);

  size_t watchCount() const { return watchCount_; }
  size_t maxWatchCount() const { return maxWatches_; }
  size_t eventCount() const { return eventCount_; }
  size_t maxEventCount() const { return maxEventQueue_; }

  static bool parseConditionOp(const String& value, WatchRegistration::ConditionOp& op);
  static const char* conditionOpName(WatchRegistration::ConditionOp op);
  static bool parseInputTrigger(const String& value, InputProvider::Event& trigger);
  static const char* inputTriggerName(InputProvider::Event trigger);

private:
  static constexpr uint32_t kSensorPollIntervalMs = 250;
  static constexpr float kEqTolerance = 0.01f;
  static constexpr size_t kWatchIdCapacity = 32;
  static constexpr size_t kSourceIdCapacity = 32;
  static constexpr size_t kMessageCapacity = 96;
  static constexpr size_t kEventIdCapacity = 16;
  static constexpr size_t kUnitCapacity = 16;
  static constexpr size_t kStatusCapacity = 16;

  struct WatchRecord {
    bool active = false;
    WatchRegistration::Kind kind = WatchRegistration::Kind::Sensor;
    char id[kWatchIdCapacity] = {};
    char sourceId[kSourceIdCapacity] = {};
    char message[kMessageCapacity] = {};
    uint8_t sourceIndex = 0;
    uint32_t cooldownSeconds = 0;
    uint32_t lastTriggeredAtSeconds = 0;
    WatchRegistration::ConditionOp conditionOp = WatchRegistration::ConditionOp::None;
    bool hasConditionValue = false;
    float conditionValue = 0.0f;
    float lastSensorValue = 0.0f;
    bool hasLastSensorValue = false;
    InputProvider::Event inputTrigger = InputProvider::Event::None;
  };

  struct EventRecord {
    bool active = false;
    WatchRegistration::Kind kind = WatchRegistration::Kind::Sensor;
    char id[kEventIdCapacity] = {};
    char watchId[kWatchIdCapacity] = {};
    uint32_t ts = 0;
    char sourceId[kSourceIdCapacity] = {};
    float value = 0.0f;
    char unit[kUnitCapacity] = {};
    char status[kStatusCapacity] = {};
    InputProvider::Event inputTrigger = InputProvider::Event::None;
    char message[kMessageCapacity] = {};
  };

  WatchRecord* findWatchById(const char* id);
  const WatchRecord* findWatchById(const char* id) const;
  bool canInsertNewWatch(const char* id) const;
  bool cooldownElapsed(uint32_t nowSeconds, uint32_t lastTriggeredAtSeconds, uint32_t cooldownSeconds) const;
  void enqueueSensorEvent(const WatchRecord& watch, uint32_t nowSeconds, float value, const char* unit, const char* status);
  void enqueueInputEvent(const WatchRecord& watch, uint32_t nowSeconds, InputProvider::Event trigger);

  size_t maxEventQueue_;
  size_t maxWatches_;
  bool started_ = false;
  WatchRecord* watches_ = nullptr;
  size_t watchCount_ = 0;
  EventRecord* events_ = nullptr;
  size_t eventHead_ = 0;
  size_t eventCount_ = 0;
  uint32_t nextEventSequence_ = 1;
  uint32_t lastSensorPollAtMs_ = 0;
};

} // namespace nekopaw
