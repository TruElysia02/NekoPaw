#pragma once

#include <stddef.h>
#include <stdint.h>

namespace nekopaw {

/// Abstract display interface.
/// Implement this for your specific display hardware (e-ink, TFT, OLED, etc.).
class DisplayProvider {
public:
  virtual ~DisplayProvider() = default;

  struct Capabilities {
    uint16_t width = 0;
    uint16_t height = 0;
    const char* type = "unknown"; // "epd_bw", "tft_color", "oled"
    bool supportsPartial = false;
  };
  virtual Capabilities capabilities() const = 0;

  struct TextContent {
    const char* title = nullptr;
    const char* body = nullptr;    // required
    const char* footer = nullptr;
    const char* style = "default"; // "default"/"alert"/"success"/"compact"
  };
  virtual bool showText(const TextContent& content, bool fullRefresh) = 0;

  virtual bool showBitmap(const uint8_t* data, size_t len, bool fullRefresh) = 0;

  struct ConfirmContent {
    const char* title = nullptr;
    const char* body = nullptr;
    const char* confirmLabel = "Confirm";
    const char* cancelLabel = "Cancel";
    const char* style = "default";
  };
  virtual bool showConfirm(const ConfirmContent& content, bool fullRefresh) = 0;

  virtual void clear() = 0;
};

} // namespace nekopaw
