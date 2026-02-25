#pragma once

#include <stdint.h>

namespace nekopaw {

/// Abstract input interface (buttons, touch, rotary encoder, etc.).
class InputProvider {
public:
  virtual ~InputProvider() = default;

  struct Info {
    const char* id = nullptr;   // "button1"
    const char* type = nullptr; // "button", "touch", "encoder"
  };
  virtual Info info() const = 0;

  enum class Event : uint8_t {
    None = 0,
    Click = 1,
    DoubleClick = 2,
    LongPress = 3,
    Release = 4,
  };

  /// Poll and return a single event (if any).
  virtual Event poll() = 0;

  /// Non-blocking update (debounce, state machine, etc.). Called from NekoPaw::loop().
  virtual void tick() = 0;
};

} // namespace nekopaw
