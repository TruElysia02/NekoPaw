#include "nekopaw/core/EventManager.h"

#include <Arduino.h>

#include <math.h>
#include <new>

#include "NekoPaw.h"
#include "nekopaw/core/Protocol.h"
#include "nekopaw/providers/SensorProvider.h"

namespace nekopaw {

namespace {

struct SensorSnapshot {
  bool ready = false;
  SensorProvider::Info info;
  SensorProvider::Reading reading;
};

bool isPrintableString(const char* value) { return value != nullptr && value[0] != '\0'; }

} // namespace

EventManager::EventManager(size_t maxEventQueue, size_t maxWatches)
    : maxEventQueue_(maxEventQueue), maxWatches_(maxWatches) {}

bool EventManager::begin() {
  if (started_) {
    return true;
  }

  if (maxWatches_ > 0 && watches_ == nullptr) {
    watches_ = new (std::nothrow) WatchRecord[maxWatches_];
    if (watches_ == nullptr) {
      return false;
    }
  }

  if (maxEventQueue_ > 0 && events_ == nullptr) {
    events_ = new (std::nothrow) EventRecord[maxEventQueue_];
    if (events_ == nullptr) {
      return false;
    }
  }

  started_ = true;
  return true;
}

bool EventManager::parseConditionOp(const String& value, WatchRegistration::ConditionOp& op) {
  String normalized = value;
  normalized.trim();
  normalized.toLowerCase();

  if (normalized == "gt") {
    op = WatchRegistration::ConditionOp::Gt;
    return true;
  }
  if (normalized == "lt") {
    op = WatchRegistration::ConditionOp::Lt;
    return true;
  }
  if (normalized == "gte") {
    op = WatchRegistration::ConditionOp::Gte;
    return true;
  }
  if (normalized == "lte") {
    op = WatchRegistration::ConditionOp::Lte;
    return true;
  }
  if (normalized == "eq") {
    op = WatchRegistration::ConditionOp::Eq;
    return true;
  }
  if (normalized == "change") {
    op = WatchRegistration::ConditionOp::Change;
    return true;
  }
  return false;
}

const char* EventManager::conditionOpName(WatchRegistration::ConditionOp op) {
  switch (op) {
    case WatchRegistration::ConditionOp::Gt:
      return "gt";
    case WatchRegistration::ConditionOp::Lt:
      return "lt";
    case WatchRegistration::ConditionOp::Gte:
      return "gte";
    case WatchRegistration::ConditionOp::Lte:
      return "lte";
    case WatchRegistration::ConditionOp::Eq:
      return "eq";
    case WatchRegistration::ConditionOp::Change:
      return "change";
    case WatchRegistration::ConditionOp::None:
    default:
      return "none";
  }
}

bool EventManager::parseInputTrigger(const String& value, InputProvider::Event& trigger) {
  String normalized = value;
  normalized.trim();
  normalized.toLowerCase();

  if (normalized == "click") {
    trigger = InputProvider::Event::Click;
    return true;
  }
  if (normalized == "double_click") {
    trigger = InputProvider::Event::DoubleClick;
    return true;
  }
  if (normalized == "long_press") {
    trigger = InputProvider::Event::LongPress;
    return true;
  }
  if (normalized == "release") {
    trigger = InputProvider::Event::Release;
    return true;
  }
  return false;
}

const char* EventManager::inputTriggerName(InputProvider::Event trigger) {
  switch (trigger) {
    case InputProvider::Event::Click:
      return "click";
    case InputProvider::Event::DoubleClick:
      return "double_click";
    case InputProvider::Event::LongPress:
      return "long_press";
    case InputProvider::Event::Release:
      return "release";
    case InputProvider::Event::None:
    default:
      return "none";
  }
}

EventManager::WatchRecord* EventManager::findWatchById(const char* id) {
  if (!isPrintableString(id) || watches_ == nullptr) {
    return nullptr;
  }

  for (size_t i = 0; i < maxWatches_; ++i) {
    if (watches_[i].active && strcmp(watches_[i].id, id) == 0) {
      return &watches_[i];
    }
  }
  return nullptr;
}

const EventManager::WatchRecord* EventManager::findWatchById(const char* id) const {
  if (!isPrintableString(id) || watches_ == nullptr) {
    return nullptr;
  }

  for (size_t i = 0; i < maxWatches_; ++i) {
    if (watches_[i].active && strcmp(watches_[i].id, id) == 0) {
      return &watches_[i];
    }
  }
  return nullptr;
}

bool EventManager::canInsertNewWatch(const char* id) const {
  if (findWatchById(id) != nullptr) {
    return true;
  }
  return watchCount_ < maxWatches_;
}

bool EventManager::cooldownElapsed(uint32_t nowSeconds, uint32_t lastTriggeredAtSeconds, uint32_t cooldownSeconds) const {
  if (cooldownSeconds == 0 || lastTriggeredAtSeconds == 0) {
    return true;
  }
  if (nowSeconds < lastTriggeredAtSeconds) {
    return true;
  }
  return (nowSeconds - lastTriggeredAtSeconds) >= cooldownSeconds;
}

bool EventManager::upsertWatch(const WatchRegistration& registration, NekoPaw& paw, String& errorMessage,
                               const char*& errorCode) {
  errorCode = "INVALID_PARAMS";

  if (watches_ == nullptr || maxWatches_ == 0) {
    errorCode = "WATCH_LIMIT";
    errorMessage = "watch capacity is 0";
    return false;
  }

  if (!isPrintableString(registration.id)) {
    errorMessage = "watch id is required";
    return false;
  }
  if (strlen(registration.id) >= kWatchIdCapacity) {
    errorMessage = "watch id is too long";
    return false;
  }
  if (!isPrintableString(registration.sourceId)) {
    errorMessage = registration.kind == WatchRegistration::Kind::Sensor ? "sensor is required" : "input is required";
    return false;
  }
  if (strlen(registration.sourceId) >= kSourceIdCapacity) {
    errorMessage = registration.kind == WatchRegistration::Kind::Sensor ? "sensor id is too long" : "input id is too long";
    return false;
  }
  if (registration.message != nullptr && strlen(registration.message) >= kMessageCapacity) {
    errorMessage = "message is too long";
    return false;
  }

  uint8_t sourceIndex = 0;
  if (registration.kind == WatchRegistration::Kind::Sensor) {
    bool found = false;
    for (size_t i = 0; i < paw.sensorCount_; ++i) {
      const SensorProvider::Info info = paw.sensors_[i]->info();
      if (info.id != nullptr && strcmp(info.id, registration.sourceId) == 0) {
        sourceIndex = static_cast<uint8_t>(i);
        found = true;
        break;
      }
    }
    if (!found) {
      errorMessage = String("sensor '") + registration.sourceId + "' not registered";
      return false;
    }
    if (registration.conditionOp == WatchRegistration::ConditionOp::None) {
      errorMessage = "condition.op is required for sensor watch";
      return false;
    }
  } else {
    bool found = false;
    for (size_t i = 0; i < paw.inputCount_; ++i) {
      const InputProvider::Info info = paw.inputs_[i]->info();
      if (info.id != nullptr && strcmp(info.id, registration.sourceId) == 0) {
        sourceIndex = static_cast<uint8_t>(i);
        found = true;
        break;
      }
    }
    if (!found) {
      errorMessage = String("input '") + registration.sourceId + "' not registered";
      return false;
    }
    if (registration.inputTrigger == InputProvider::Event::None) {
      errorMessage = "trigger is required for input watch";
      return false;
    }
  }

  WatchRecord* slot = findWatchById(registration.id);
  if (slot == nullptr) {
    if (!canInsertNewWatch(registration.id)) {
      errorCode = "WATCH_LIMIT";
      errorMessage = "watch limit reached";
      return false;
    }

    for (size_t i = 0; i < maxWatches_; ++i) {
      if (!watches_[i].active) {
        slot = &watches_[i];
        break;
      }
    }
    if (slot == nullptr) {
      errorCode = "WATCH_LIMIT";
      errorMessage = "watch limit reached";
      return false;
    }
    *slot = WatchRecord{};
    slot->active = true;
    ++watchCount_;
  } else {
    const uint32_t lastTriggeredAtSeconds = slot->lastTriggeredAtSeconds;
    const float lastSensorValue = slot->lastSensorValue;
    const bool hasLastSensorValue = slot->hasLastSensorValue;
    *slot = WatchRecord{};
    slot->active = true;
    slot->lastTriggeredAtSeconds = lastTriggeredAtSeconds;
    slot->lastSensorValue = lastSensorValue;
    slot->hasLastSensorValue = hasLastSensorValue;
  }

  slot->kind = registration.kind;
  slot->sourceIndex = sourceIndex;
  slot->cooldownSeconds = registration.cooldownSeconds;
  slot->conditionOp = registration.conditionOp;
  slot->hasConditionValue = registration.hasConditionValue;
  slot->conditionValue = registration.conditionValue;
  slot->inputTrigger = registration.inputTrigger;
  core::copyCString(slot->id, sizeof(slot->id), registration.id);
  core::copyCString(slot->sourceId, sizeof(slot->sourceId), registration.sourceId);
  core::copyCString(slot->message, sizeof(slot->message), registration.message != nullptr ? registration.message : "");

  return true;
}

bool EventManager::removeWatch(const char* id, String& errorMessage, const char*& errorCode) {
  errorCode = "INVALID_PARAMS";
  if (!isPrintableString(id)) {
    errorMessage = "id is required";
    return false;
  }

  WatchRecord* slot = findWatchById(id);
  if (slot == nullptr) {
    errorCode = "WATCH_NOT_FOUND";
    errorMessage = String("watch '") + id + "' not found";
    return false;
  }

  *slot = WatchRecord{};
  if (watchCount_ > 0) {
    --watchCount_;
  }
  return true;
}

void EventManager::appendWatches(ArduinoJson::JsonArray watches) const {
  if (watches_ == nullptr) {
    return;
  }

  for (size_t i = 0; i < maxWatches_; ++i) {
    const WatchRecord& watch = watches_[i];
    if (!watch.active) {
      continue;
    }

    ArduinoJson::JsonObject item = watches.add<ArduinoJson::JsonObject>();
    item["id"] = watch.id;
    if (watch.kind == WatchRegistration::Kind::Sensor) {
      item["sensor"] = watch.sourceId;
      ArduinoJson::JsonObject condition = item["condition"].to<ArduinoJson::JsonObject>();
      condition["op"] = conditionOpName(watch.conditionOp);
      if (watch.hasConditionValue) {
        condition["value"] = watch.conditionValue;
      } else {
        condition["value"] = nullptr;
      }
      item["cooldown"] = watch.cooldownSeconds;
    } else {
      item["input"] = watch.sourceId;
      item["trigger"] = inputTriggerName(watch.inputTrigger);
    }

    if (watch.message[0] != '\0') {
      item["message"] = watch.message;
    } else {
      item["message"] = nullptr;
    }
  }
}

void EventManager::drainEvents(ArduinoJson::JsonArray events, size_t& remaining) {
  if (events_ == nullptr || eventCount_ == 0) {
    remaining = 0;
    return;
  }

  for (size_t i = 0; i < eventCount_; ++i) {
    const size_t index = (eventHead_ + i) % maxEventQueue_;
    const EventRecord& event = events_[index];
    if (!event.active) {
      continue;
    }

    ArduinoJson::JsonObject item = events.add<ArduinoJson::JsonObject>();
    item["id"] = event.id;
    item["watchId"] = event.watchId;
    item["ts"] = event.ts;
    ArduinoJson::JsonObject payload = item["payload"].to<ArduinoJson::JsonObject>();
    if (event.kind == WatchRegistration::Kind::Sensor) {
      payload["sensor"] = event.sourceId;
      payload["value"] = event.value;
      payload["unit"] = event.unit;
      payload["status"] = event.status;
    } else {
      payload["input"] = event.sourceId;
      payload["trigger"] = inputTriggerName(event.inputTrigger);
    }
    if (event.message[0] != '\0') {
      payload["message"] = event.message;
    }
  }

  eventHead_ = 0;
  eventCount_ = 0;
  remaining = 0;
}

void EventManager::enqueueSensorEvent(const WatchRecord& watch, uint32_t nowSeconds, float value, const char* unit,
                                      const char* status) {
  if (events_ == nullptr || maxEventQueue_ == 0) {
    return;
  }

  if (eventCount_ == maxEventQueue_) {
    eventHead_ = (eventHead_ + 1) % maxEventQueue_;
    --eventCount_;
  }

  const size_t index = (eventHead_ + eventCount_) % maxEventQueue_;
  EventRecord& event = events_[index];
  event = EventRecord{};
  event.active = true;
  event.kind = WatchRegistration::Kind::Sensor;
  snprintf(event.id, sizeof(event.id), "evt_%06lu", static_cast<unsigned long>(nextEventSequence_++));
  core::copyCString(event.watchId, sizeof(event.watchId), watch.id);
  event.ts = nowSeconds;
  core::copyCString(event.sourceId, sizeof(event.sourceId), watch.sourceId);
  event.value = value;
  core::copyCString(event.unit, sizeof(event.unit), unit != nullptr ? unit : "");
  core::copyCString(event.status, sizeof(event.status), status != nullptr ? status : "ok");
  core::copyCString(event.message, sizeof(event.message), watch.message);
  ++eventCount_;
}

void EventManager::enqueueInputEvent(const WatchRecord& watch, uint32_t nowSeconds, InputProvider::Event trigger) {
  if (events_ == nullptr || maxEventQueue_ == 0) {
    return;
  }

  if (eventCount_ == maxEventQueue_) {
    eventHead_ = (eventHead_ + 1) % maxEventQueue_;
    --eventCount_;
  }

  const size_t index = (eventHead_ + eventCount_) % maxEventQueue_;
  EventRecord& event = events_[index];
  event = EventRecord{};
  event.active = true;
  event.kind = WatchRegistration::Kind::Input;
  snprintf(event.id, sizeof(event.id), "evt_%06lu", static_cast<unsigned long>(nextEventSequence_++));
  core::copyCString(event.watchId, sizeof(event.watchId), watch.id);
  event.ts = nowSeconds;
  core::copyCString(event.sourceId, sizeof(event.sourceId), watch.sourceId);
  event.inputTrigger = trigger;
  core::copyCString(event.message, sizeof(event.message), watch.message);
  ++eventCount_;
}

void EventManager::handleInputEvent(size_t inputIndex, InputProvider::Event event, uint32_t nowSeconds) {
  if (!started_ || watches_ == nullptr || watchCount_ == 0 || event == InputProvider::Event::None) {
    return;
  }

  for (size_t watchIndex = 0; watchIndex < maxWatches_; ++watchIndex) {
    WatchRecord& watch = watches_[watchIndex];
    if (!watch.active || watch.kind != WatchRegistration::Kind::Input || watch.sourceIndex != inputIndex ||
        watch.inputTrigger != event) {
      continue;
    }
    if (!cooldownElapsed(nowSeconds, watch.lastTriggeredAtSeconds, watch.cooldownSeconds)) {
      continue;
    }

    enqueueInputEvent(watch, nowSeconds, event);
    watch.lastTriggeredAtSeconds = nowSeconds;
  }
}

void EventManager::tick(NekoPaw& paw) {
  if (!started_ || watches_ == nullptr || watchCount_ == 0) {
    return;
  }

  const uint32_t nowSeconds = paw.nowSeconds();
  const uint32_t nowMs = millis();
  const bool shouldPollSensors =
      paw.sensorCount_ > 0 && (lastSensorPollAtMs_ == 0 || nowMs < lastSensorPollAtMs_ ||
                               (nowMs - lastSensorPollAtMs_) >= kSensorPollIntervalMs);

  SensorSnapshot sensorSnapshots[NekoPaw::kMaxSensors] = {};
  if (shouldPollSensors) {
    lastSensorPollAtMs_ = nowMs;
  }

  for (size_t i = 0; i < maxWatches_; ++i) {
    WatchRecord& watch = watches_[i];
    if (!watch.active || watch.kind != WatchRegistration::Kind::Sensor || !shouldPollSensors ||
        watch.sourceIndex >= paw.sensorCount_) {
      continue;
    }

    SensorSnapshot& snapshot = sensorSnapshots[watch.sourceIndex];
    if (!snapshot.ready) {
      snapshot.info = paw.sensors_[watch.sourceIndex]->info();
      snapshot.reading = paw.sensors_[watch.sourceIndex]->read();
      snapshot.ready = true;
    }

    if (!snapshot.reading.valid) {
      continue;
    }

    const float value = snapshot.reading.value;
    bool matched = false;
    switch (watch.conditionOp) {
      case WatchRegistration::ConditionOp::Gt:
        matched = watch.hasConditionValue && value > watch.conditionValue;
        break;
      case WatchRegistration::ConditionOp::Lt:
        matched = watch.hasConditionValue && value < watch.conditionValue;
        break;
      case WatchRegistration::ConditionOp::Gte:
        matched = watch.hasConditionValue && value >= watch.conditionValue;
        break;
      case WatchRegistration::ConditionOp::Lte:
        matched = watch.hasConditionValue && value <= watch.conditionValue;
        break;
      case WatchRegistration::ConditionOp::Eq:
        matched = watch.hasConditionValue && fabsf(value - watch.conditionValue) <= kEqTolerance;
        break;
      case WatchRegistration::ConditionOp::Change: {
        const float threshold = watch.hasConditionValue ? watch.conditionValue : 0.0f;
        matched = watch.hasLastSensorValue && fabsf(value - watch.lastSensorValue) >= threshold;
        break;
      }
      case WatchRegistration::ConditionOp::None:
      default:
        matched = false;
        break;
    }

    watch.lastSensorValue = value;
    watch.hasLastSensorValue = true;

    if (!matched || !cooldownElapsed(nowSeconds, watch.lastTriggeredAtSeconds, watch.cooldownSeconds)) {
      continue;
    }

    enqueueSensorEvent(watch, nowSeconds, value, snapshot.info.unit, "ok");
    watch.lastTriggeredAtSeconds = nowSeconds;
  }
}

} // namespace nekopaw
