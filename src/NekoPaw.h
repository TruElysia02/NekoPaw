#pragma once

#include <stdint.h>

#include "nekopaw/providers/DisplayProvider.h"
#include "nekopaw/providers/InputProvider.h"
#include "nekopaw/providers/OutputProvider.h"
#include "nekopaw/providers/SensorProvider.h"

namespace nekopaw {

class NekoPaw {
public:
  struct Config {
    uint16_t httpPort = 80;
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
  Config config_;
  DisplayProvider* display_ = nullptr;
};

} // namespace nekopaw
