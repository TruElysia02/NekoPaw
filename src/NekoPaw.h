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

private:
  friend class BridgeServer;
  friend class CommandDispatcher;
  friend class EventManager;

  static constexpr size_t kMaxSensors = 8;
  static constexpr size_t kMaxInputs = 4;
  static constexpr size_t kMaxOutputs = 4;
  static constexpr size_t kDeviceIdCapacity = 32;
  static constexpr size_t kDescriptionCapacity = 160;

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

  void ensureDeviceId();
  void loadDescription();
  uint32_t nowSeconds() const;
  const char* descriptionSourceLabel() const;
  void markDisplayState(DisplaySource source, uint32_t ttlSeconds);

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
  BridgeServer* bridge_ = nullptr;
  CommandDispatcher* dispatcher_ = nullptr;
  EventManager* eventManager_ = nullptr;
};

} // namespace nekopaw
