#include "nekopaw/core/CommandDispatcher.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESP.h>
#include <Preferences.h>
#include <WebServer.h>

#include <new>

#include "NekoPaw.h"
#include "nekopaw/core/Config.h"
#include "nekopaw/core/EventManager.h"
#include "nekopaw/core/Protocol.h"

namespace nekopaw {

namespace {

bool isEmptyString(const String& value) { return value.length() == 0; }
constexpr uint32_t kDefaultConfirmTimeoutSeconds = 30;

uint32_t sensorReadingTsSeconds(const SensorProvider::Reading& reading, uint32_t fallbackTs) {
  if (reading.timestamp == 0) {
    return fallbackTs;
  }
  return reading.timestamp / 1000UL;
}

void fillSensorReadingJson(ArduinoJson::JsonObject data, const SensorProvider::Info& info,
                           const SensorProvider::Reading& reading, uint32_t fallbackTs) {
  data["id"] = info.id != nullptr ? info.id : "";
  data["type"] = info.type != nullptr ? info.type : "";
  data["unit"] = info.unit != nullptr ? info.unit : "";
  if (info.description != nullptr && info.description[0] != '\0') {
    data["description"] = info.description;
  } else {
    data["description"] = nullptr;
  }

  if (reading.valid) {
    data["value"] = reading.value;
    data["status"] = "ok";
  } else {
    data["value"] = nullptr;
    data["status"] = "unavailable";
  }
  data["ts"] = sensorReadingTsSeconds(reading, fallbackTs);
}

bool parseRequiredQueryArg(WebServer& server, const char* name, String& value, String& errorMessage) {
  if (name == nullptr || name[0] == '\0') {
    errorMessage = "query argument name is required";
    return false;
  }

  if (!server.hasArg(name)) {
    errorMessage = String(name) + " is required";
    return false;
  }

  value = server.arg(name);
  value.trim();
  if (value.length() == 0) {
    errorMessage = String(name) + " is required";
    return false;
  }
  return true;
}

String normalizedArgValue(const String& value) {
  String normalized = value;
  normalized.trim();
  normalized.toLowerCase();
  return normalized;
}

bool isConfirmBitmapPackRequest(WebServer& server) {
  if (!server.hasArg("format")) {
    return false;
  }

  return normalizedArgValue(server.arg("format")) == "bitmap-pack";
}

bool parseOptionalPositiveUint32Arg(WebServer& server, const char* name, uint32_t& outValue, String& errorMessage) {
  if (name == nullptr || name[0] == '\0' || !server.hasArg(name)) {
    outValue = 0;
    return true;
  }

  String normalized = server.arg(name);
  normalized.trim();
  if (normalized.length() == 0) {
    outValue = 0;
    return true;
  }

  char* end = nullptr;
  const unsigned long parsed = strtoul(normalized.c_str(), &end, 10);
  if (end == nullptr || *end != '\0') {
    errorMessage = String(name) + " must be an integer";
    return false;
  }

  if (parsed == 0) {
    errorMessage = String(name) + " must be >= 1";
    return false;
  }

  outValue = static_cast<uint32_t>(parsed);
  return true;
}

} // namespace

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
  if (paw_.hasPendingConfirm()) {
    return core::sendError(server, 409, paw_.deviceIdBuffer_, paw_.nowSeconds(), "DISPLAY_BUSY",
                           "confirm is in progress");
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

void CommandDispatcher::handleDisplayConfirmCreateRaw(WebServer& server) {
  HTTPRaw& raw = server.raw();
  if (raw.status == RAW_START) {
    confirmBitmapLength_ = 0;
    confirmBitmapOverflow_ = false;
    confirmBitmapUnavailable_ = false;
    confirmBitmapCaptureActive_ = false;

    if (!isConfirmBitmapPackRequest(server) || paw_.hasPendingConfirm()) {
      return;
    }

    const size_t expectedBytes = expectedBitmapBytes();
    const size_t expectedPackBytes = expectedBytes * NekoPaw::kConfirmBitmapStateCount;
    if (expectedBytes == 0 || expectedPackBytes > core::kConfirmBitmapPackBufferLimit) {
      confirmBitmapUnavailable_ = true;
      confirmBitmapCaptureActive_ = true;
      return;
    }

    if (!paw_.ensureConfirmBitmapStorage(expectedBytes)) {
      confirmBitmapUnavailable_ = true;
      confirmBitmapCaptureActive_ = true;
      return;
    }

    confirmBitmapCaptureActive_ = true;
    return;
  }

  if (!confirmBitmapCaptureActive_) {
    return;
  }

  if (raw.status == RAW_ABORTED) {
    confirmBitmapOverflow_ = true;
    return;
  }

  if (raw.status != RAW_WRITE) {
    return;
  }

  if (confirmBitmapUnavailable_ || confirmBitmapOverflow_ || paw_.confirmBitmapStorage_ == nullptr) {
    confirmBitmapOverflow_ = true;
    return;
  }

  const size_t expectedBytes = expectedBitmapBytes();
  const size_t expectedPackBytes = expectedBytes * NekoPaw::kConfirmBitmapStateCount;
  if (confirmBitmapLength_ + raw.currentSize > expectedPackBytes) {
    confirmBitmapOverflow_ = true;
    return;
  }

  memcpy(paw_.confirmBitmapStorage_ + confirmBitmapLength_, raw.buf, raw.currentSize);
  confirmBitmapLength_ += raw.currentSize;
}

int CommandDispatcher::handleDisplayBitmap(WebServer& server) {
  if (paw_.display_ == nullptr) {
    return sendDisplayUnavailable(server);
  }
  if (paw_.hasPendingConfirm()) {
    return core::sendError(server, 409, paw_.deviceIdBuffer_, paw_.nowSeconds(), "DISPLAY_BUSY",
                           "confirm is in progress");
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
    } else {
      const uint32_t now = paw_.nowSeconds();
      const uint32_t elapsed =
          now >= paw_.displayState_.updatedAtSeconds ? now - paw_.displayState_.updatedAtSeconds : 0;
      data["ttlRemaining"] = elapsed >= paw_.displayState_.ttlSeconds ? 0 : paw_.displayState_.ttlSeconds - elapsed;
    }

    data["hasConfirmPending"] = paw_.hasPendingConfirm();
    if (paw_.hasPendingConfirm()) {
      data["confirmRequestId"] = paw_.confirm_.requestId;
    } else {
      data["confirmRequestId"] = nullptr;
    }
  });
}

int CommandDispatcher::handleDisplayConfirmCreate(WebServer& server) {
  if (paw_.display_ == nullptr) {
    return sendDisplayUnavailable(server);
  }
  if (paw_.hasPendingConfirm()) {
    return core::sendError(server, 409, paw_.deviceIdBuffer_, paw_.nowSeconds(), "CONFIRM_ACTIVE",
                           "a confirm request is already pending");
  }

  const String format = server.hasArg("format") ? normalizedArgValue(server.arg("format")) : "";
  if (format.length() > 0 && format != "bitmap-pack") {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                           "format must be 'bitmap-pack'");
  }

  String errorMessage;
  if (format == "bitmap-pack") {
    uint32_t timeoutSeconds = kDefaultConfirmTimeoutSeconds;
    if (!parseOptionalPositiveUint32Arg(server, "timeout", timeoutSeconds, errorMessage)) {
      return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
    }
    if (timeoutSeconds == 0) {
      timeoutSeconds = kDefaultConfirmTimeoutSeconds;
    }

    const size_t expectedBytes = expectedBitmapBytes();
    const size_t expectedPackBytes = expectedBytes * NekoPaw::kConfirmBitmapStateCount;
    if (confirmBitmapUnavailable_) {
      return core::sendError(server, 503, paw_.deviceIdBuffer_, paw_.nowSeconds(), "DISPLAY_UNAVAILABLE",
                             "display rejected confirm bitmap pack");
    }
    if (confirmBitmapOverflow_ || confirmBitmapLength_ != expectedPackBytes) {
      return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "BITMAP_SIZE_MISMATCH",
                             String("expected ") + expectedPackBytes + " bytes, got " + confirmBitmapLength_);
    }

    if (!paw_.startConfirmBitmap(timeoutSeconds, false)) {
      return core::sendError(server, 500, paw_.deviceIdBuffer_, paw_.nowSeconds(), "DISPLAY_UNAVAILABLE",
                             "display rejected confirm bitmap pack");
    }

    return core::sendOk(server, paw_.deviceIdBuffer_, paw_.confirm_.startedAtSeconds,
                        [&](ArduinoJson::JsonObject data) {
                          data["requestId"] = paw_.confirm_.requestId;
                          data["status"] = paw_.confirmStateLabel();
                        });
  }

  ArduinoJson::JsonDocument doc;
  if (!core::parseJsonBody(server, doc, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  const ArduinoJson::JsonVariantConst root = doc.as<ArduinoJson::JsonVariantConst>();
  const String body = root["body"] | "";
  if (body.length() == 0) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                           "body is required");
  }

  uint32_t timeoutSeconds = kDefaultConfirmTimeoutSeconds;
  if (!root["timeout"].isNull()) {
    if (!core::parseOptionalUint32(root["timeout"], timeoutSeconds, errorMessage)) {
      return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
    }
    if (timeoutSeconds == 0) {
      return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                             "timeout must be >= 1");
    }
  }

  const String title = root["title"] | "";
  const String confirmLabel = root["confirmLabel"] | "Confirm (BTN1)";
  const String cancelLabel = root["cancelLabel"] | "Cancel (BTN2)";
  const String style = root["style"] | "default";

  DisplayProvider::ConfirmContent content;
  content.title = title.length() > 0 ? title.c_str() : nullptr;
  content.body = body.c_str();
  content.confirmLabel = confirmLabel.c_str();
  content.cancelLabel = cancelLabel.c_str();
  content.style = style.c_str();

  if (!paw_.startConfirm(content, timeoutSeconds, false)) {
    return core::sendError(server, 500, paw_.deviceIdBuffer_, paw_.nowSeconds(), "DISPLAY_UNAVAILABLE",
                           "display rejected confirm content");
  }

  return core::sendOk(server, paw_.deviceIdBuffer_, paw_.confirm_.startedAtSeconds,
                      [&](ArduinoJson::JsonObject data) {
                        data["requestId"] = paw_.confirm_.requestId;
                        data["status"] = paw_.confirmStateLabel();
                      });
}

int CommandDispatcher::handleDisplayConfirmGet(WebServer& server) {
  String requestId;
  String errorMessage;
  if (!parseRequiredQueryArg(server, "id", requestId, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  if (!paw_.matchesConfirmRequestId(requestId.c_str())) {
    return core::sendError(server, 404, paw_.deviceIdBuffer_, paw_.nowSeconds(), "CONFIRM_NOT_FOUND",
                           String("confirm '") + requestId + "' not found");
  }

  const uint32_t responseTs =
      paw_.confirm_.respondedAtSeconds > 0 ? paw_.confirm_.respondedAtSeconds : paw_.confirm_.startedAtSeconds;
  return core::sendOk(server, paw_.deviceIdBuffer_, responseTs, [&](ArduinoJson::JsonObject data) {
    data["requestId"] = paw_.confirm_.requestId;
    data["status"] = paw_.confirmStateLabel();
    if (paw_.confirm_.state == NekoPaw::ConfirmState::Pending) {
      data["responseTime"] = nullptr;
      data["respondedAt"] = nullptr;
    } else {
      data["responseTime"] = paw_.confirm_.responseTimeMs;
      data["respondedAt"] = paw_.confirm_.respondedAtSeconds;
    }
  });
}

int CommandDispatcher::handleDisplayConfirmDelete(WebServer& server) {
  String requestId;
  String errorMessage;
  if (!parseRequiredQueryArg(server, "id", requestId, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  if (!paw_.matchesConfirmRequestId(requestId.c_str())) {
    return core::sendError(server, 404, paw_.deviceIdBuffer_, paw_.nowSeconds(), "CONFIRM_NOT_FOUND",
                           String("confirm '") + requestId + "' not found");
  }
  if (!paw_.cancelConfirm()) {
    return core::sendError(server, 409, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                           "confirm is not pending");
  }

  return core::sendOk(server, paw_.deviceIdBuffer_, paw_.confirm_.respondedAtSeconds,
                      [&](ArduinoJson::JsonObject data) {
                        data["requestId"] = paw_.confirm_.requestId;
                        data["status"] = paw_.confirmStateLabel();
                        data["responseTime"] = paw_.confirm_.responseTimeMs;
                        data["respondedAt"] = paw_.confirm_.respondedAtSeconds;
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

int CommandDispatcher::handleSensors(WebServer& server) {
  const uint32_t nowSeconds = paw_.nowSeconds();

  if (server.hasArg("id")) {
    String sensorId = server.arg("id");
    sensorId.trim();
    if (sensorId.length() == 0) {
      return core::sendError(server, 400, paw_.deviceIdBuffer_, nowSeconds, "INVALID_PARAMS", "id is required");
    }

    for (size_t i = 0; i < paw_.sensorCount_; ++i) {
      const SensorProvider::Info info = paw_.sensors_[i]->info();
      if (info.id == nullptr || sensorId != info.id) {
        continue;
      }

      const SensorProvider::Reading reading = paw_.sensors_[i]->read();
      return core::sendOk(server, paw_.deviceIdBuffer_, nowSeconds, [&](ArduinoJson::JsonObject data) {
        fillSensorReadingJson(data, info, reading, nowSeconds);
      });
    }

    return core::sendError(server, 404, paw_.deviceIdBuffer_, nowSeconds, "SENSOR_NOT_FOUND",
                           String("sensor '") + sensorId + "' not registered");
  }

  return core::sendOk(server, paw_.deviceIdBuffer_, nowSeconds, [&](ArduinoJson::JsonObject data) {
    ArduinoJson::JsonArray sensors = data["sensors"].to<ArduinoJson::JsonArray>();
    for (size_t i = 0; i < paw_.sensorCount_; ++i) {
      const SensorProvider::Info info = paw_.sensors_[i]->info();
      const SensorProvider::Reading reading = paw_.sensors_[i]->read();
      fillSensorReadingJson(sensors.add<ArduinoJson::JsonObject>(), info, reading, nowSeconds);
    }
  });
}

int CommandDispatcher::handleEventsWatchCreate(WebServer& server) {
  if (paw_.eventManager_ == nullptr) {
    return core::sendError(server, 500, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INTERNAL_ERROR",
                           "event manager is not available");
  }

  ArduinoJson::JsonDocument doc;
  String errorMessage;
  if (!core::parseJsonBody(server, doc, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  const ArduinoJson::JsonVariantConst root = doc.as<ArduinoJson::JsonVariantConst>();
  const ArduinoJson::JsonArrayConst watches = root["watches"].as<ArduinoJson::JsonArrayConst>();
  if (watches.isNull() || watches.size() == 0) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                           "watches must be a non-empty array");
  }

  const char* errorCode = "INVALID_PARAMS";
  for (ArduinoJson::JsonVariantConst item : watches) {
    const ArduinoJson::JsonObjectConst watch = item.as<ArduinoJson::JsonObjectConst>();
    if (watch.isNull()) {
      return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                             "each watch must be an object");
    }

    EventManager::WatchRegistration registration;
    const String watchId = watch["id"] | "";
    const String sensorId = watch["sensor"] | "";
    const String inputId = watch["input"] | "";
    const String message = watch["message"] | "";
    if (isEmptyString(watchId)) {
      return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                             "watch id is required");
    }
    if (sensorId.length() > 0 && inputId.length() > 0) {
      return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                             "watch must declare either sensor or input, not both");
    }
    if (sensorId.length() == 0 && inputId.length() == 0) {
      return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                             "watch must declare either sensor or input");
    }

    registration.id = watchId.c_str();
    registration.message = message.length() > 0 ? message.c_str() : nullptr;
    if (!core::parseOptionalUint32(watch["cooldown"], registration.cooldownSeconds, errorMessage)) {
      return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
    }

    if (sensorId.length() > 0) {
      registration.kind = EventManager::WatchRegistration::Kind::Sensor;
      registration.sourceId = sensorId.c_str();

      const ArduinoJson::JsonObjectConst condition = watch["condition"].as<ArduinoJson::JsonObjectConst>();
      if (condition.isNull()) {
        return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                               "condition is required for sensor watch");
      }

      const String op = condition["op"] | "";
      if (!EventManager::parseConditionOp(op, registration.conditionOp)) {
        return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                               "condition.op must be one of gt, lt, gte, lte, eq, change");
      }

      if (!core::parseOptionalFloat(condition["value"], registration.conditionValue, registration.hasConditionValue,
                                    errorMessage)) {
        return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
      }

      if (registration.conditionOp != EventManager::WatchRegistration::ConditionOp::Change &&
          !registration.hasConditionValue) {
        return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                               "condition.value is required for this operator");
      }
    } else {
      registration.kind = EventManager::WatchRegistration::Kind::Input;
      registration.sourceId = inputId.c_str();

      const String trigger = watch["trigger"] | "";
      if (!EventManager::parseInputTrigger(trigger, registration.inputTrigger)) {
        return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                               "trigger must be one of click, double_click, long_press, release");
      }
    }

    if (!paw_.eventManager_->upsertWatch(registration, paw_, errorMessage, errorCode)) {
      const int statusCode = strcmp(errorCode, "WATCH_LIMIT") == 0 ? 409 : 400;
      return core::sendError(server, statusCode, paw_.deviceIdBuffer_, paw_.nowSeconds(), errorCode, errorMessage);
    }
  }

  return core::sendOk(server, paw_.deviceIdBuffer_, paw_.nowSeconds(), [&](ArduinoJson::JsonObject data) {
    data["watchCount"] = paw_.eventManager_->watchCount();
    data["maxWatches"] = paw_.eventManager_->maxWatchCount();
    ArduinoJson::JsonArray watchesData = data["watches"].to<ArduinoJson::JsonArray>();
    paw_.eventManager_->appendWatches(watchesData);
  });
}

int CommandDispatcher::handleEventsWatchDelete(WebServer& server) {
  if (paw_.eventManager_ == nullptr) {
    return core::sendError(server, 500, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INTERNAL_ERROR",
                           "event manager is not available");
  }

  String watchId;
  String errorMessage;
  if (!parseRequiredQueryArg(server, "id", watchId, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  const char* errorCode = "INVALID_PARAMS";
  if (!paw_.eventManager_->removeWatch(watchId.c_str(), errorMessage, errorCode)) {
    const int statusCode = strcmp(errorCode, "WATCH_NOT_FOUND") == 0 ? 404 : 400;
    return core::sendError(server, statusCode, paw_.deviceIdBuffer_, paw_.nowSeconds(), errorCode, errorMessage);
  }

  return core::sendOk(server, paw_.deviceIdBuffer_, paw_.nowSeconds(), [&](ArduinoJson::JsonObject data) {
    data["id"] = watchId;
    data["watchCount"] = paw_.eventManager_->watchCount();
  });
}

int CommandDispatcher::handleEventsPoll(WebServer& server) {
  if (paw_.eventManager_ == nullptr) {
    return core::sendError(server, 500, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INTERNAL_ERROR",
                           "event manager is not available");
  }

  return core::sendOk(server, paw_.deviceIdBuffer_, paw_.nowSeconds(), [&](ArduinoJson::JsonObject data) {
    ArduinoJson::JsonArray events = data["events"].to<ArduinoJson::JsonArray>();
    size_t remaining = 0;
    paw_.eventManager_->drainEvents(events, remaining);
    data["remaining"] = remaining;
  });
}

int CommandDispatcher::handleOutputs(WebServer& server) {
  String outputId;
  String errorMessage;
  if (!parseRequiredQueryArg(server, "id", outputId, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  OutputProvider* output = nullptr;
  OutputProvider::Info info;
  for (size_t i = 0; i < paw_.outputCount_; ++i) {
    if (paw_.outputs_[i] == nullptr) {
      continue;
    }

    const OutputProvider::Info candidate = paw_.outputs_[i]->info();
    if (candidate.id == nullptr || outputId != candidate.id) {
      continue;
    }

    output = paw_.outputs_[i];
    info = candidate;
    break;
  }

  if (output == nullptr) {
    return core::sendError(server, 404, paw_.deviceIdBuffer_, paw_.nowSeconds(), "OUTPUT_NOT_FOUND",
                           String("output '") + outputId + "' not registered");
  }

  ArduinoJson::JsonDocument doc;
  if (!core::parseJsonBody(server, doc, errorMessage)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS", errorMessage);
  }

  const ArduinoJson::JsonObjectConst params = doc.as<ArduinoJson::JsonObjectConst>();
  if (params.isNull()) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                           "JSON body must be an object");
  }

  if (!output->execute(params)) {
    return core::sendError(server, 400, paw_.deviceIdBuffer_, paw_.nowSeconds(), "INVALID_PARAMS",
                           "output rejected command");
  }

  return core::sendOk(server, paw_.deviceIdBuffer_, paw_.nowSeconds(), [&](ArduinoJson::JsonObject data) {
    data["id"] = info.id != nullptr ? info.id : "";
    data["type"] = info.type != nullptr ? info.type : "";
  });
}

int CommandDispatcher::handleNotFound(WebServer& server) {
  return core::sendError(server, 404, paw_.deviceIdBuffer_, paw_.nowSeconds(), "NOT_FOUND",
                         String("unknown endpoint: ") + server.uri());
}

} // namespace nekopaw
