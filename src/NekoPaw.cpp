#include "NekoPaw.h"

#include <ESP.h>
#include <Preferences.h>

#include <string.h>

#include <new>

#include "nekopaw/core/BridgeServer.h"
#include "nekopaw/core/CommandDispatcher.h"
#include "nekopaw/core/Config.h"
#include "nekopaw/core/EventManager.h"
#include "nekopaw/core/Protocol.h"

namespace nekopaw {

namespace {

size_t confirmBitmapOffset(NekoPaw::ConfirmState state, size_t pageBytes) {
  size_t pageIndex = 0;
  switch (state) {
    case NekoPaw::ConfirmState::Pending:
      pageIndex = 0;
      break;
    case NekoPaw::ConfirmState::Confirmed:
      pageIndex = 1;
      break;
    case NekoPaw::ConfirmState::Cancelled:
      pageIndex = 2;
      break;
    case NekoPaw::ConfirmState::Timeout:
      pageIndex = 3;
      break;
    case NekoPaw::ConfirmState::Idle:
    default:
      return 0;
  }

  return pageIndex * pageBytes;
}

} // namespace

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

NekoPaw::ConfirmState NekoPaw::confirmState() const {
  return confirm_.occupied ? confirm_.state : ConfirmState::Idle;
}

const char* NekoPaw::confirmStateLabel() const {
  switch (confirmState()) {
    case ConfirmState::Pending:
      return "pending";
    case ConfirmState::Confirmed:
      return "confirmed";
    case ConfirmState::Cancelled:
      return "cancelled";
    case ConfirmState::Timeout:
      return "timeout";
    case ConfirmState::Idle:
    default:
      return "idle";
  }
}

bool NekoPaw::hasPendingConfirm() const {
  return confirm_.occupied && confirm_.state == ConfirmState::Pending;
}

bool NekoPaw::matchesConfirmRequestId(const char* requestId) const {
  return confirm_.occupied && requestId != nullptr && requestId[0] != '\0' && strcmp(confirm_.requestId, requestId) == 0;
}

bool NekoPaw::startConfirm(const DisplayProvider::ConfirmContent& content, uint32_t timeoutSeconds, bool fullRefresh) {
  if (display_ == nullptr || hasPendingConfirm()) {
    return false;
  }

  ConfirmSession nextConfirm;
  nextConfirm.occupied = true;
  nextConfirm.state = ConfirmState::Pending;
  nextConfirm.renderMode = ConfirmRenderMode::Text;
  nextConfirm.startedAtSeconds = nowSeconds();
  nextConfirm.startedAtMillis = millis();
  nextConfirm.timeoutSeconds = timeoutSeconds;

  snprintf(nextConfirm.requestId, sizeof(nextConfirm.requestId), "cfm_%06lu",
           static_cast<unsigned long>(nextConfirmSequence_));
  ++nextConfirmSequence_;
  if (nextConfirmSequence_ == 0) {
    nextConfirmSequence_ = 1;
  }

  if (!display_->showConfirm(content, fullRefresh)) {
    return false;
  }

  confirm_ = nextConfirm;
  markDisplayState(DisplaySource::Text, 0);
  return true;
}

bool NekoPaw::startConfirmBitmap(uint32_t timeoutSeconds, bool fullRefresh) {
  if (display_ == nullptr || hasPendingConfirm() || confirmBitmapStorage_ == nullptr) {
    return false;
  }

  const DisplayProvider::Capabilities capabilities = display_->capabilities();
  const size_t pageBytes = core::bitmapByteLength(capabilities.width, capabilities.height);
  if (pageBytes == 0 || confirmBitmapStorageCapacity_ < pageBytes * kConfirmBitmapStateCount) {
    return false;
  }

  ConfirmSession nextConfirm;
  nextConfirm.occupied = true;
  nextConfirm.state = ConfirmState::Pending;
  nextConfirm.renderMode = ConfirmRenderMode::Bitmap;
  nextConfirm.startedAtSeconds = nowSeconds();
  nextConfirm.startedAtMillis = millis();
  nextConfirm.timeoutSeconds = timeoutSeconds;
  nextConfirm.bitmapPageBytes = pageBytes;

  snprintf(nextConfirm.requestId, sizeof(nextConfirm.requestId), "cfm_%06lu",
           static_cast<unsigned long>(nextConfirmSequence_));
  ++nextConfirmSequence_;
  if (nextConfirmSequence_ == 0) {
    nextConfirmSequence_ = 1;
  }

  if (!display_->showBitmap(confirmBitmapStorage_, pageBytes, fullRefresh)) {
    return false;
  }

  confirm_ = nextConfirm;
  markDisplayState(DisplaySource::Bitmap, 0);
  return true;
}

bool NekoPaw::resolveConfirm(ConfirmState state) {
  if (!hasPendingConfirm() || state == ConfirmState::Idle || state == ConfirmState::Pending) {
    return false;
  }

  confirm_.state = state;
  confirm_.respondedAtSeconds = nowSeconds();
  confirm_.responseTimeMs = millis() - confirm_.startedAtMillis;
  if (confirm_.renderMode == ConfirmRenderMode::Bitmap) {
    (void)showConfirmBitmapState(state, true);
    markDisplayState(DisplaySource::Bitmap, 0);
  }
  return true;
}

bool NekoPaw::cancelConfirm() { return resolveConfirm(ConfirmState::Cancelled); }

void NekoPaw::handleInputEvent(const InputProvider::Info& info, InputProvider::Event event) {
  if (!hasPendingConfirm() || event != InputProvider::Event::Click || info.id == nullptr) {
    return;
  }

  if (strcmp(info.id, "button1") == 0) {
    (void)resolveConfirm(ConfirmState::Confirmed);
  } else if (strcmp(info.id, "button2") == 0) {
    (void)resolveConfirm(ConfirmState::Cancelled);
  }
}

void NekoPaw::tickConfirm() {
  if (!hasPendingConfirm() || confirm_.timeoutSeconds == 0) {
    return;
  }

  const uint32_t elapsedMs = millis() - confirm_.startedAtMillis;
  if (elapsedMs < static_cast<uint32_t>(confirm_.timeoutSeconds * 1000UL)) {
    return;
  }

  (void)resolveConfirm(ConfirmState::Timeout);
}

bool NekoPaw::ensureConfirmBitmapStorage(size_t pageBytes) {
  if (pageBytes == 0) {
    return false;
  }

  const size_t requiredBytes = pageBytes * kConfirmBitmapStateCount;
  if (confirmBitmapStorage_ != nullptr && confirmBitmapStorageCapacity_ >= requiredBytes) {
    return true;
  }

  uint8_t* nextStorage = new (std::nothrow) uint8_t[requiredBytes];
  if (nextStorage == nullptr) {
    return false;
  }

  delete[] confirmBitmapStorage_;
  confirmBitmapStorage_ = nextStorage;
  confirmBitmapStorageCapacity_ = requiredBytes;
  return true;
}

bool NekoPaw::showConfirmBitmapState(ConfirmState state, bool fullRefresh) {
  if (display_ == nullptr || confirmBitmapStorage_ == nullptr || confirm_.bitmapPageBytes == 0) {
    return false;
  }

  if (state != ConfirmState::Pending && state != ConfirmState::Confirmed && state != ConfirmState::Cancelled &&
      state != ConfirmState::Timeout) {
    return false;
  }

  const size_t offset = confirmBitmapOffset(state, confirm_.bitmapPageBytes);
  return display_->showBitmap(confirmBitmapStorage_ + offset, confirm_.bitmapPageBytes, fullRefresh);
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

  for (size_t i = 0; i < outputCount_; ++i) {
    if (outputs_[i] != nullptr) {
      outputs_[i]->tick();
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

  const uint32_t now = nowSeconds();
  for (size_t i = 0; i < inputCount_; ++i) {
    if (inputs_[i] == nullptr) {
      continue;
    }

    const InputProvider::Info info = inputs_[i]->info();
    while (true) {
      const InputProvider::Event event = inputs_[i]->poll();
      if (event == InputProvider::Event::None) {
        break;
      }

      handleInputEvent(info, event);
      if (eventManager_ != nullptr) {
        eventManager_->handleInputEvent(i, event, now);
      }
    }
  }

  tickConfirm();

  if (eventManager_ != nullptr) {
    eventManager_->tick(*this);
  }
}

} // namespace nekopaw
