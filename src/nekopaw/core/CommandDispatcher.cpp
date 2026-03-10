#include "nekopaw/core/CommandDispatcher.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESP.h>
#include <Preferences.h>
#include <WebServer.h>

#include <new>

#include "NekoPaw.h"
#include "nekopaw/core/Config.h"
#include "nekopaw/core/Protocol.h"

namespace nekopaw {

CommandDispatcher::CommandDispatcher(NekoPaw& paw) : paw_(paw) {}

size_t CommandDispatcher::expectedBitmapBytes() const {
  if (paw_.display_ == nullptr) {
    return 0;
  }

  const DisplayProvider::Capabilities capabilities = paw_.display_->capabilities();
  return core::bitmapByteLength(capabilities.width, capabilities.height);
}

int CommandDispatcher::sendDisplayUnavailable(WebServer& server) {
  return core::sendError(server, 503, paw_.deviceIdBuffer_, paw_.nowSeconds(), "DISPLAY_UNAVAILABLE",
                         "display provider is not registered");
}

int CommandDispatcher::handleDevice(WebServer& server) {
  return core::sendOk(server, paw_.deviceIdBuffer_, paw_.nowSeconds(), [&](ArduinoJson::JsonObject data) {
    data["id"] = paw_.deviceIdBuffer_;
    data["protocolVersion"] = core::kProtocolVersion;
    data["firmware"] = core::kFirmwareVersion;
    data["platform"] = ESP.getChipModel();
    data["uptime"] = paw_.nowSeconds();
    data["freeHeap"] = ESP.getFreeHeap();
    if (paw_.hasDescription_) {
      data["description"] = paw_.descriptionBuffer_;
    } else {
      data["description"] = nullptr;
    }
    data["descriptionSource"] = paw_.descriptionSourceLabel();

    ArduinoJson::JsonObject capabilities = data["capabilities"].to<ArduinoJson::JsonObject>();
    if (paw_.display_ != nullptr) {
      const DisplayProvider::Capabilities displayCaps = paw_.display_->capabilities();
      ArduinoJson::JsonObject display = capabilities["display"].to<ArduinoJson::JsonObject>();
      display["type"] = displayCaps.type;
      display["width"] = displayCaps.width;
      display["height"] = displayCaps.height;
      display["supportsPartial"] = displayCaps.supportsPartial;
    } else {
      capabilities["display"] = nullptr;
    }

    ArduinoJson::JsonArray sensors = capabilities["sensors"].to<ArduinoJson::JsonArray>();
    for (size_t i = 0; i < paw_.sensorCount_; ++i) {
      const SensorProvider::Info info = paw_.sensors_[i]->info();
      sensors.add(info.id != nullptr ? info.id : "");
    }

    ArduinoJson::JsonArray inputs = capabilities["inputs"].to<ArduinoJson::JsonArray>();
    for (size_t i = 0; i < paw_.inputCount_; ++i) {
      const InputProvider::Info info = paw_.inputs_[i]->info();
      inputs.add(info.id != nullptr ? info.id : "");
    }

    ArduinoJson::JsonArray outputs = capabilities["outputs"].to<ArduinoJson::JsonArray>();
    for (size_t i = 0; i < paw_.outputCount_; ++i) {
      const OutputProvider::Info info = paw_.outputs_[i]->info();
      outputs.add(info.id != nullptr ? info.id : "");
    }
  });
}

int CommandDispatcher::handleDisplayText(WebServer& server) {
  if (paw_.display_ == nullptr) {
    return sendDisplayUnavailable(server);
  }

  ArduinoJson::JsonDocument doc;
  String errorMessage;
  if (!core::parseJsonBody(server, doc, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  const ArduinoJson::JsonVariantConst root = doc.as<ArduinoJson::JsonVariantConst>();
  const String body = root["body"] | "";
  if (body.length() == 0) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                           "body is required");
  }

  bool fullRefresh = false;
  if (!core::parseRefreshField(root["refresh"], fullRefresh, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  uint32_t ttlSeconds = 0;
  if (!core::parseOptionalUint32(root["ttl"], ttlSeconds, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  const String title = root["title"] | "";
  const String footer = root["footer"] | "";
  const String style = root["style"] | "default";

  DisplayProvider::TextContent content;
  content.title = title.length() > 0 ? title.c_str() : nullptr;
  content.body = body.c_str();
  content.footer = footer.length() > 0 ? footer.c_str() : nullptr;
  content.style = style.c_str();

  if (!paw_.display_->showText(content, fullRefresh)) {
    return core::sendError(server, 500, paw_.deviceIdBuffer_, paw_.nowSeconds(), "DISPLAY_UNAVAILABLE",
                           "display rejected text content");
  }

  paw_.markDisplayState(NekoPaw::DisplaySource::Text, ttlSeconds);

  return core::sendOk(server, paw_.deviceIdBuffer_, paw_.displayState_.updatedAtSeconds,
                      [&](ArduinoJson::JsonObject data) {
    data["source"] = "text";
    data["ts"] = paw_.displayState_.updatedAtSeconds;
    if (ttlSeconds > 0) {
      data["ttl"] = ttlSeconds;
    } else {
      data["ttl"] = nullptr;
    }
  });
}

void CommandDispatcher::handleDisplayBitmapRaw(WebServer& server) {
  HTTPRaw& raw = server.raw();
  if (raw.status == RAW_START) {
    delete[] bitmapBuffer_;
    bitmapBuffer_ = nullptr;
    bitmapBufferCapacity_ = 0;
    bitmapLength_ = 0;
    bitmapOverflow_ = false;

    const size_t expectedBytes = expectedBitmapBytes();
    if (expectedBytes == 0 || expectedBytes > core::kBitmapBufferLimit) {
      bitmapOverflow_ = true;
      return;
    }

    bitmapBuffer_ = new (std::nothrow) uint8_t[expectedBytes];
    if (bitmapBuffer_ == nullptr) {
      bitmapOverflow_ = true;
      return;
    }

    bitmapBufferCapacity_ = expectedBytes;
    return;
  }

  if (raw.status == RAW_ABORTED) {
    bitmapOverflow_ = true;
    return;
  }

  if (raw.status != RAW_WRITE) {
    return;
  }

  if (bitmapOverflow_ || bitmapBuffer_ == nullptr) {
    bitmapOverflow_ = true;
    return;
  }

  if (bitmapLength_ + raw.currentSize > bitmapBufferCapacity_) {
    bitmapOverflow_ = true;
    return;
  }

  memcpy(bitmapBuffer_ + bitmapLength_, raw.buf, raw.currentSize);
  bitmapLength_ += raw.currentSize;
}

int CommandDispatcher::handleDisplayBitmap(WebServer& server) {
  if (paw_.display_ == nullptr) {
    return sendDisplayUnavailable(server);
  }

  String errorMessage;
  bool fullRefresh = false;
  if (server.hasArg("refresh") && !core::parseRefreshValue(server.arg("refresh"), fullRefresh, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  uint32_t ttlSeconds = 0;
  if (server.hasArg("ttl") && !core::parseOptionalUint32Arg(server.arg("ttl"), ttlSeconds, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  const size_t expectedBytes = expectedBitmapBytes();
  if (bitmapOverflow_ || bitmapBuffer_ == nullptr || bitmapLength_ != expectedBytes) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "BITMAP_SIZE_MISMATCH",
                           String("expected ") + expectedBytes + " bytes, got " + bitmapLength_);
  }

  if (!paw_.display_->showBitmap(bitmapBuffer_, bitmapLength_, fullRefresh)) {
    return core::sendError(server, 500, paw_.deviceIdBuffer_, paw_.nowSeconds(), "DISPLAY_UNAVAILABLE",
                           "display rejected bitmap payload");
  }

  paw_.markDisplayState(NekoPaw::DisplaySource::Bitmap, ttlSeconds);

  return core::sendOk(server, paw_.deviceIdBuffer_, paw_.displayState_.updatedAtSeconds,
                      [&](ArduinoJson::JsonObject data) {
    data["source"] = "bitmap";
    data["bytes"] = bitmapLength_;
    data["ts"] = paw_.displayState_.updatedAtSeconds;
    if (ttlSeconds > 0) {
      data["ttl"] = ttlSeconds;
    } else {
      data["ttl"] = nullptr;
    }
  });
}

int CommandDispatcher::handleDisplayState(WebServer& server) {
  return core::sendOk(server, paw_.deviceIdBuffer_, paw_.nowSeconds(), [&](ArduinoJson::JsonObject data) {
    switch (paw_.displayState_.source) {
      case NekoPaw::DisplaySource::Text:
        data["source"] = "text";
        break;
      case NekoPaw::DisplaySource::Bitmap:
        data["source"] = "bitmap";
        break;
      case NekoPaw::DisplaySource::None:
      default:
        data["source"] = "none";
        break;
    }
    if (paw_.displayState_.updatedAtSeconds > 0) {
      data["ts"] = paw_.displayState_.updatedAtSeconds;
    } else {
      data["ts"] = nullptr;
    }

    if (paw_.displayState_.ttlSeconds == 0 || paw_.displayState_.updatedAtSeconds == 0) {
      data["ttlRemaining"] = nullptr;
      return;
    }

    const uint32_t now = paw_.nowSeconds();
    const uint32_t elapsed = now >= paw_.displayState_.updatedAtSeconds ? now - paw_.displayState_.updatedAtSeconds : 0;
    data["ttlRemaining"] = elapsed >= paw_.displayState_.ttlSeconds ? 0 : paw_.displayState_.ttlSeconds - elapsed;
  });
}

int CommandDispatcher::handleDeviceDescriptionPatch(WebServer& server) {
  ArduinoJson::JsonDocument doc;
  String errorMessage;
  if (!core::parseJsonBody(server, doc, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  const String description = doc["description"] | "";
  if (description.length() == 0) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                           "description is required");
  }

  if (description.length() >= sizeof(paw_.descriptionBuffer_)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                           "description is too long");
  }

  Preferences preferences;
  if (!preferences.begin(core::kPreferencesNamespace, false)) {
    return core::sendError(server, 500, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INTERNAL_ERROR",
                           "failed to open preferences");
  }
  preferences.putString(core::kDescriptionKey, description);
  preferences.end();

  core::copyCString(paw_.descriptionBuffer_, sizeof(paw_.descriptionBuffer_), description);
  paw_.hasDescription_ = true;
  paw_.descriptionSource_ = NekoPaw::DescriptionSource::AiGenerated;

  return core::sendOk(server, paw_.deviceIdBuffer_, paw_.nowSeconds(), [&](ArduinoJson::JsonObject data) {
    data["description"] = paw_.descriptionBuffer_;
    data["descriptionSource"] = paw_.descriptionSourceLabel();
  });
}

int CommandDispatcher::handleNotFound(WebServer& server) {
  return core::sendError(server, 404, paw_.deviceIdBuffer_, paw_.nowSeconds(), "NOT_FOUND",
                         String("unknown endpoint: ") + server.uri());
}

} // namespace nekopaw
