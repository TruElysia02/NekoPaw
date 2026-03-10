#pragma once

#include <Arduino.h>
#include <GxEPD2_BW.h>
#include <SPI.h>

#include "nekopaw/providers/DisplayProvider.h"

namespace nekopaw {

template <typename DisplayT>
class GxEPD2DisplayAdapter : public DisplayProvider {
public:
  struct Pins {
    int16_t sclk;
    int16_t miso;
    int16_t mosi;
    int16_t cs;
    int16_t dc;
    int16_t rst;
    int16_t busy;
  };

  struct Layout {
    uint16_t width;
    uint16_t height;
    uint8_t rotation = 0;
    bool supportsPartial = true;
  };

  GxEPD2DisplayAdapter(DisplayT& display, const Pins& pins, const Layout& layout)
      : display_(display), pins_(pins), layout_(layout) {}

  Capabilities capabilities() const override {
    Capabilities caps;
    caps.width = layout_.width;
    caps.height = layout_.height;
    caps.type = "epd_bw";
    caps.supportsPartial = layout_.supportsPartial;
    return caps;
  }

  bool showText(const TextContent& content, bool fullRefresh) override {
    if (content.body == nullptr || content.body[0] == '\0') {
      return false;
    }

    beginIfNeeded();
    refresh(fullRefresh, [&]() {
      display_.setTextColor(GxEPD_BLACK);
      display_.setTextWrap(true);
      display_.cp437(true);

      const bool isCompact = content.style != nullptr && strcmp(content.style, "compact") == 0;
      const bool isAlert = content.style != nullptr && strcmp(content.style, "alert") == 0;
      const bool isSuccess = content.style != nullptr && strcmp(content.style, "success") == 0;
      const int16_t margin = isCompact ? 4 : 8;
      int16_t cursorY = margin + 12;

      if (isAlert) {
        display_.drawRect(0, 0, layout_.width, layout_.height, GxEPD_BLACK);
      } else if (isSuccess) {
        display_.drawLine(0, 0, layout_.width - 1, 0, GxEPD_BLACK);
        display_.drawLine(0, 1, layout_.width - 1, 1, GxEPD_BLACK);
      }

      if (content.title != nullptr && content.title[0] != '\0') {
        display_.setTextSize(isCompact ? 1 : 2);
        display_.setCursor(margin, cursorY);
        display_.println(content.title);
        cursorY += isCompact ? 10 : 16;
        display_.drawLine(margin, cursorY, layout_.width - margin, cursorY, GxEPD_BLACK);
        cursorY += 8;
      }

      display_.setTextSize(1);
      display_.setCursor(margin, cursorY);
      display_.print(content.body);

      if (content.footer != nullptr && content.footer[0] != '\0') {
        display_.setTextWrap(false);
        display_.setCursor(margin, static_cast<int16_t>(layout_.height - 8));
        display_.print(content.footer);
      }
    });

    return true;
  }

  bool showBitmap(const uint8_t* data, size_t len, bool fullRefresh) override {
    if (data == nullptr || len != expectedBitmapBytes()) {
      return false;
    }

    beginIfNeeded();
    refresh(fullRefresh, [&]() { display_.drawBitmap(0, 0, data, layout_.width, layout_.height, GxEPD_BLACK); });
    return true;
  }

  bool showConfirm(const ConfirmContent& content, bool fullRefresh) override {
    String body = content.body != nullptr ? content.body : "";
    body += "\n\n[";
    body += content.confirmLabel != nullptr ? content.confirmLabel : "Confirm";
    body += "]  [";
    body += content.cancelLabel != nullptr ? content.cancelLabel : "Cancel";
    body += "]";

    TextContent text;
    text.title = content.title;
    text.body = body.c_str();
    text.footer = nullptr;
    text.style = content.style != nullptr ? content.style : "default";
    return showText(text, fullRefresh);
  }

  void clear() override {
    beginIfNeeded();
    display_.setFullWindow();
    display_.firstPage();
    do {
      display_.fillScreen(GxEPD_WHITE);
    } while (display_.nextPage());
    hasDrawn_ = true;
    partialSinceFull_ = 0;
  }

private:
  void beginIfNeeded() {
    if (started_) {
      return;
    }

    SPI.begin(pins_.sclk, pins_.miso, pins_.mosi, pins_.cs);
    display_.init(0, true);
    display_.setRotation(layout_.rotation);
    started_ = true;
  }

  template <typename DrawFn>
  void refresh(bool fullRefresh, DrawFn drawFn) {
    const bool shouldUseFullRefresh =
        !layout_.supportsPartial || !hasDrawn_ || fullRefresh || partialSinceFull_ >= partialFullRefreshEvery_;

    if (shouldUseFullRefresh) {
      display_.setFullWindow();
    } else {
      display_.setPartialWindow(0, 0, layout_.width, layout_.height);
    }

    display_.firstPage();
    do {
      display_.fillScreen(GxEPD_WHITE);
      drawFn();
    } while (display_.nextPage());

    hasDrawn_ = true;
    if (shouldUseFullRefresh) {
      partialSinceFull_ = 0;
    } else {
      ++partialSinceFull_;
    }
  }

  size_t expectedBitmapBytes() const { return static_cast<size_t>((layout_.width + 7U) / 8U) * layout_.height; }

  DisplayT& display_;
  Pins pins_;
  Layout layout_;
  bool started_ = false;
  bool hasDrawn_ = false;
  uint8_t partialSinceFull_ = 0;
  uint8_t partialFullRefreshEvery_ = 8;
};

} // namespace nekopaw
