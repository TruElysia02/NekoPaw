#include "NekoPaw.h"

#include <ESP.h>
#include <Preferences.h>

#include <new>

#include "nekopaw/core/BridgeServer.h"
#include "nekopaw/core/CommandDispatcher.h"
#include "nekopaw/core/Config.h"
#include "nekopaw/core/EventManager.h"
#include "nekopaw/core/Protocol.h"

namespace nekopaw {

NekoPaw::NekoPaw() = default;

NekoPaw::NekoPaw(const Config& config) : config_(config) {}

void NekoPaw::setDisplay(DisplayProvider* provider) { display_ = provider; }

void NekoPaw::addSensor(SensorProvider* provider) {
  if (provider == nullptr || sensorCount_ >= kMaxSensors) {
    return;
  }

  sensors_[sensorCount_++] = provider;
}

void NekoPaw::addInput(InputProvider* provider) {
  if (provider == nullptr || inputCount_ >= kMaxInputs) {
    return;
  }

  inputs_[inputCount_++] = provider;
}

void NekoPaw::addOutput(OutputProvider* provider) {
  if (provider == nullptr || outputCount_ >= kMaxOutputs) {
    return;
  }

  outputs_[outputCount_++] = provider;
}

void NekoPaw::ensureDeviceId() {
  if (deviceIdBuffer_[0] != '\0') {
    return;
  }

  if (config_.deviceId != nullptr && config_.deviceId[0] != '\0') {
    core::copyCString(deviceIdBuffer_, sizeof(deviceIdBuffer_), config_.deviceId);
    return;
  }

  const uint64_t efuseMac = ESP.getEfuseMac();
  snprintf(deviceIdBuffer_, sizeof(deviceIdBuffer_), "NekoPaw-%02X%02X%02X",
           static_cast<unsigned>((efuseMac >> 16) & 0xFF), static_cast<unsigned>((efuseMac >> 8) & 0xFF),
           static_cast<unsigned>(efuseMac & 0xFF));
}

void NekoPaw::loadDescription() {
  descriptionBuffer_[0] = '\0';
  hasDescription_ = false;
  descriptionSource_ = DescriptionSource::None;

  if (config_.description != nullptr && config_.description[0] != '\0') {
    core::copyCString(descriptionBuffer_, sizeof(descriptionBuffer_), config_.description);
    hasDescription_ = true;
    descriptionSource_ = DescriptionSource::User;
    return;
  }

  Preferences preferences;
  if (!preferences.begin(core::kPreferencesNamespace, true)) {
    return;
  }

  const String persisted = preferences.getString(core::kDescriptionKey, "");
  preferences.end();

  if (persisted.length() == 0) {
    return;
  }

  core::copyCString(descriptionBuffer_, sizeof(descriptionBuffer_), persisted);
  hasDescription_ = true;
  descriptionSource_ = DescriptionSource::AiGenerated;
}

uint32_t NekoPaw::nowSeconds() const { return millis() / 1000UL; }

const char* NekoPaw::descriptionSourceLabel() const {
  switch (descriptionSource_) {
    case DescriptionSource::User:
      return "user";
    case DescriptionSource::AiGenerated:
      return "ai_generated";
    case DescriptionSource::None:
    default:
      return "none";
  }
}

void NekoPaw::markDisplayState(DisplaySource source, uint32_t ttlSeconds) {
  displayState_.source = source;
  displayState_.updatedAtSeconds = nowSeconds();
  displayState_.ttlSeconds = ttlSeconds;
}

bool NekoPaw::begin() {
  ensureDeviceId();
  loadDescription();

  if (eventManager_ == nullptr) {
    eventManager_ = new (std::nothrow) EventManager(config_.maxEventQueue, config_.maxWatches);
    if (eventManager_ == nullptr || !eventManager_->begin()) {
      return false;
    }
  }

  if (dispatcher_ == nullptr) {
    dispatcher_ = new (std::nothrow) CommandDispatcher(*this);
    if (dispatcher_ == nullptr) {
      return false;
    }
  }

  if (bridge_ == nullptr) {
    bridge_ = new (std::nothrow) BridgeServer(config_.httpPort, *dispatcher_);
    if (bridge_ == nullptr) {
      return false;
    }
  }

  bridge_->begin();

  NEKOPAW_LOGF("device=%s", deviceIdBuffer_);
  NEKOPAW_LOGF("http listening on port %u", config_.httpPort);
  if (display_ == nullptr) {
    NEKOPAW_LOG("no display provider registered");
  }

  return true;
}

void NekoPaw::loop() {
  if (bridge_ != nullptr) {
    bridge_->poll();
  }

  for (size_t i = 0; i < inputCount_; ++i) {
    if (inputs_[i] != nullptr) {
      inputs_[i]->tick();
    }
  }

  for (size_t i = 0; i < outputCount_; ++i) {
    if (outputs_[i] != nullptr) {
      outputs_[i]->tick();
    }
  }

  if (eventManager_ != nullptr) {
    eventManager_->tick(*this);
  }
}

} // namespace nekopaw
