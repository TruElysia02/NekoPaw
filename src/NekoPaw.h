#pragma once

#include <stddef.h>
#include <stdint.h>

#include "nekopaw/providers/DisplayProvider.h"
#include "nekopaw/providers/InputProvider.h"
#include "nekopaw/providers/OutputProvider.h"
#include "nekopaw/providers/SensorProvider.h"

namespace nekopaw {

class BridgeServer;
class CommandDispatcher;
class EventManager;

class NekoPaw {
public:
  enum class ConfirmState : uint8_t {
    Idle = 0,
    Pending = 1,
    Confirmed = 2,
    Cancelled = 3,
    Timeout = 4,
  };

  struct Config {
    uint16_t httpPort = 80;
    size_t maxEventQueue = 16;
    size_t maxWatches = 8;
    const char* deviceId = nullptr;
    const char* description = nullptr;
  };

  NekoPaw();
  explicit NekoPaw(const Config& config);

  void setDisplay(DisplayProvider* provider);
  void addSensor(SensorProvider* provider);
  void addInput(InputProvider* provider);
  void addOutput(OutputProvider* provider);

  bool begin();
  void loop();
  ConfirmState confirmState() const;

private:
  friend class BridgeServer;
  friend class CommandDispatcher;
  friend class EventManager;

  static constexpr size_t kMaxSensors = 8;
  static constexpr size_t kMaxInputs = 4;
  static constexpr size_t kMaxOutputs = 4;
  static constexpr size_t kDeviceIdCapacity = 32;
  static constexpr size_t kDescriptionCapacity = 160;
  static constexpr size_t kConfirmRequestIdCapacity = 20;

  enum class DescriptionSource : uint8_t {
    None = 0,
    User = 1,
    AiGenerated = 2,
  };

  enum class DisplaySource : uint8_t {
    None = 0,
    Text = 1,
    Bitmap = 2,
  };

  struct DisplayState {
    DisplaySource source = DisplaySource::None;
    uint32_t updatedAtSeconds = 0;
    uint32_t ttlSeconds = 0;
  };

  struct ConfirmSession {
    bool occupied = false;
    ConfirmState state = ConfirmState::Idle;
    char requestId[kConfirmRequestIdCapacity] = {};
    uint32_t startedAtSeconds = 0;
    uint32_t startedAtMillis = 0;
    uint32_t timeoutSeconds = 0;
    uint32_t respondedAtSeconds = 0;
    uint32_t responseTimeMs = 0;
  };

  void ensureDeviceId();
  void loadDescription();
  uint32_t nowSeconds() const;
  const char* descriptionSourceLabel() const;
  const char* confirmStateLabel() const;
  void markDisplayState(DisplaySource source, uint32_t ttlSeconds);
  bool hasPendingConfirm() const;
  bool matchesConfirmRequestId(const char* requestId) const;
  bool startConfirm(const DisplayProvider::ConfirmContent& content, uint32_t timeoutSeconds, bool fullRefresh);
  bool resolveConfirm(ConfirmState state);
  bool cancelConfirm();
  void handleInputEvent(const InputProvider::Info& info, InputProvider::Event event);
  void tickConfirm();

  Config config_;
  DisplayProvider* display_ = nullptr;
  SensorProvider* sensors_[kMaxSensors] = {};
  size_t sensorCount_ = 0;
  InputProvider* inputs_[kMaxInputs] = {};
  size_t inputCount_ = 0;
  OutputProvider* outputs_[kMaxOutputs] = {};
  size_t outputCount_ = 0;
  char deviceIdBuffer_[kDeviceIdCapacity] = {};
  char descriptionBuffer_[kDescriptionCapacity] = {};
  bool hasDescription_ = false;
  DescriptionSource descriptionSource_ = DescriptionSource::None;
  DisplayState displayState_;
  ConfirmSession confirm_;
  uint32_t nextConfirmSequence_ = 1;
  BridgeServer* bridge_ = nullptr;
  CommandDispatcher* dispatcher_ = nullptr;
  EventManager* eventManager_ = nullptr;
};

} // namespace nekopaw
