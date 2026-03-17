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
      display_.setTextWrap(false);
      display_.cp437(true);

      const bool isCompact = content.style != nullptr && strcmp(content.style, "compact") == 0;
      const bool isAlert = content.style != nullptr && strcmp(content.style, "alert") == 0;
      const int16_t margin = isCompact ? 6 : 8;
      const uint8_t titleSize = isCompact ? 1 : 2;
      const int16_t bodyTracking = isCompact ? 0 : 1;
      const int16_t titleTracking = isCompact ? 0 : 1;
      const int16_t bodyLineSpacing = isCompact ? 2 : 3;
      const int16_t contentWidth = layout_.width - margin * 2;
      int16_t bodyTop = margin;
      int16_t bodyBottom = layout_.height - margin;

      if (isAlert) {
        display_.drawRect(0, 0, layout_.width, layout_.height, GxEPD_BLACK);
      }

      if (content.title != nullptr && content.title[0] != '\0') {
        const int16_t titleY = margin - (isCompact ? 1 : 2);
        drawTextBlock(margin, titleY, contentWidth, layout_.height - margin, content.title, titleSize, titleTracking,
                      0);

        const int16_t separatorY = titleY + glyphHeight(titleSize) + (isCompact ? 3 : 4);
        display_.drawLine(margin, separatorY, layout_.width - margin, separatorY, GxEPD_BLACK);
        bodyTop = separatorY + (isCompact ? 7 : 10);
      }

      if (content.footer != nullptr && content.footer[0] != '\0') {
        const int16_t footerY = layout_.height - margin - glyphHeight(1);
        drawTextBlock(margin, footerY, contentWidth, layout_.height - margin, content.footer, 1, bodyTracking, 0);
        bodyBottom = footerY - (isCompact ? 8 : 10);
      }

      drawTextBlock(margin, bodyTop, contentWidth, bodyBottom, content.body, 1, bodyTracking, bodyLineSpacing);
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
  static constexpr int16_t kClassicFontWidth = 6;
  static constexpr int16_t kClassicFontHeight = 8;

  static int16_t glyphWidth(uint8_t textSize) { return static_cast<int16_t>(kClassicFontWidth * textSize); }

  static int16_t glyphHeight(uint8_t textSize) { return static_cast<int16_t>(kClassicFontHeight * textSize); }

  void drawTextBlock(int16_t startX, int16_t startY, int16_t maxWidth, int16_t maxBottom, const char* text,
                     uint8_t textSize, int16_t tracking, int16_t lineSpacing) {
    if (text == nullptr || text[0] == '\0' || maxWidth <= 0) {
      return;
    }

    const int16_t charWidth = glyphWidth(textSize);
    const int16_t charHeight = glyphHeight(textSize);
    const int16_t lineHeight = charHeight + lineSpacing;
    const int16_t maxX = startX + maxWidth;

    int16_t cursorX = startX;
    int16_t cursorY = startY;

    display_.setTextSize(textSize);
    display_.setTextWrap(false);

    for (const char* p = text; *p != '\0'; ++p) {
      const char ch = *p;
      if (ch == '\r') {
        continue;
      }

      if (ch == '\n') {
        cursorX = startX;
        cursorY = static_cast<int16_t>(cursorY + lineHeight);
        if (cursorY + charHeight > maxBottom) {
          return;
        }
        continue;
      }

      if (cursorX > startX && cursorX + charWidth > maxX) {
        cursorX = startX;
        cursorY = static_cast<int16_t>(cursorY + lineHeight);
        if (cursorY + charHeight > maxBottom) {
          return;
        }
      }

      display_.setCursor(cursorX, cursorY);
      display_.write(static_cast<uint8_t>(ch));
      cursorX = static_cast<int16_t>(cursorX + charWidth);

      if (tracking > 0 && p[1] != '\0' && p[1] != '\n' && p[1] != '\r') {
        cursorX = static_cast<int16_t>(cursorX + tracking);
      }
    }
  }

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
