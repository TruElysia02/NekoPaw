#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include <WebServer.h>

#include <stddef.h>
#include <stdint.h>

namespace nekopaw::core {

inline void copyCString(char* dest, size_t destSize, const char* src) {
  if (dest == nullptr || destSize == 0) {
    return;
  }

  if (src == nullptr) {
    dest[0] = '\0';
    return;
  }

  strncpy(dest, src, destSize - 1);
  dest[destSize - 1] = '\0';
}

inline void copyCString(char* dest, size_t destSize, const String& src) { copyCString(dest, destSize, src.c_str()); }

template <typename FillDataFn>
String buildOkResponse(const char* deviceId, uint32_t ts, FillDataFn fillData) {
  ArduinoJson::JsonDocument doc;
  doc["ok"] = true;
  ArduinoJson::JsonObject data = doc["data"].to<ArduinoJson::JsonObject>();
  fillData(data);
  doc["error"] = nullptr;
  doc["ts"] = ts;
  doc["device"] = deviceId != nullptr ? deviceId : "";

  String payload;
  serializeJson(doc, payload);
  return payload;
}

inline String buildErrorResponse(const char* deviceId, uint32_t ts, const char* code, const String& message) {
  ArduinoJson::JsonDocument doc;
  doc["ok"] = false;
  doc["data"] = nullptr;
  ArduinoJson::JsonObject error = doc["error"].to<ArduinoJson::JsonObject>();
  error["code"] = code;
  error["message"] = message;
  doc["ts"] = ts;
  doc["device"] = deviceId != nullptr ? deviceId : "";

  String payload;
  serializeJson(doc, payload);
  return payload;
}

inline void sendJson(WebServer& server, int statusCode, const String& payload) {
  server.send(statusCode, "application/json", payload);
}

template <typename FillDataFn>
int sendOk(WebServer& server, const char* deviceId, uint32_t ts, FillDataFn fillData) {
  sendJson(server, 200, buildOkResponse(deviceId, ts, fillData));
  return 200;
}

inline int sendError(WebServer& server, int statusCode, const char* deviceId, uint32_t ts, const char* code,
                     const String& message) {
  sendJson(server, statusCode, buildErrorResponse(deviceId, ts, code, message));
  return statusCode;
}

inline bool parseJsonBody(WebServer& server, ArduinoJson::JsonDocument& doc, String& errorMessage) {
  if (!server.hasArg("plain")) {
    errorMessage = "missing JSON body";
    return false;
  }

  const String body = server.arg("plain");
  if (body.length() == 0) {
    errorMessage = "empty JSON body";
    return false;
  }

  const ArduinoJson::DeserializationError err = ArduinoJson::deserializeJson(doc, body);
  if (err) {
    errorMessage = String("invalid JSON: ") + err.c_str();
    return false;
  }

  return true;
}

inline bool parseRefreshValue(const String& value, bool& fullRefresh, String& errorMessage) {
  String normalized = value;
  normalized.trim();
  normalized.toLowerCase();

  if (normalized.length() == 0 || normalized == "partial") {
    fullRefresh = false;
    return true;
  }

  if (normalized == "full") {
    fullRefresh = true;
    return true;
  }

  errorMessage = "refresh must be 'full' or 'partial'";
  return false;
}

inline bool parseRefreshField(ArduinoJson::JsonVariantConst value, bool& fullRefresh, String& errorMessage) {
  if (value.isNull()) {
    fullRefresh = false;
    return true;
  }

  return parseRefreshValue(value.as<String>(), fullRefresh, errorMessage);
}

inline bool parseOptionalUint32(ArduinoJson::JsonVariantConst value, uint32_t& outValue, String& errorMessage) {
  if (value.isNull()) {
    outValue = 0;
    return true;
  }

  if (value.is<uint32_t>()) {
    outValue = value.as<uint32_t>();
    return true;
  }

  if (value.is<int32_t>()) {
    const int32_t signedValue = value.as<int32_t>();
    if (signedValue < 0) {
      errorMessage = "value must be >= 0";
      return false;
    }

    outValue = static_cast<uint32_t>(signedValue);
    return true;
  }

  errorMessage = "value must be an integer";
  return false;
}

inline bool parseOptionalUint32Arg(const String& value, uint32_t& outValue, String& errorMessage) {
  String normalized = value;
  normalized.trim();
  if (normalized.length() == 0) {
    outValue = 0;
    return true;
  }

  char* end = nullptr;
  const unsigned long parsed = strtoul(normalized.c_str(), &end, 10);
  if (end == nullptr || *end != '\0') {
    errorMessage = "ttl must be an integer";
    return false;
  }

  outValue = static_cast<uint32_t>(parsed);
  return true;
}

inline bool parseOptionalFloat(ArduinoJson::JsonVariantConst value, float& outValue, bool& hasValue,
                               String& errorMessage) {
  if (value.isNull()) {
    outValue = 0.0f;
    hasValue = false;
    return true;
  }

  if (value.is<float>() || value.is<double>() || value.is<int32_t>() || value.is<uint32_t>()) {
    outValue = value.as<float>();
    hasValue = true;
    return true;
  }

  errorMessage = "value must be a number";
  return false;
}

inline size_t bitmapByteLength(uint16_t width, uint16_t height) {
  return static_cast<size_t>((width + 7U) / 8U) * static_cast<size_t>(height);
}

} // namespace nekopaw::core
