#include "NekoPaw.h"

namespace nekopaw {

NekoPaw::NekoPaw() = default;

NekoPaw::NekoPaw(const Config& config) : config_(config) {}

void NekoPaw::setDisplay(DisplayProvider* provider) { display_ = provider; }

void NekoPaw::addSensor(SensorProvider* provider) { (void)provider; }
void NekoPaw::addInput(InputProvider* provider) { (void)provider; }
void NekoPaw::addOutput(OutputProvider* provider) { (void)provider; }

bool NekoPaw::begin() { return true; }

void NekoPaw::loop() {
  // Skeleton: Phase 1+ will implement server loop, provider ticks, etc.
}

} // namespace nekopaw
