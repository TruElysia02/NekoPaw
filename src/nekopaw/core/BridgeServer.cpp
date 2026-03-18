#include "nekopaw/core/BridgeServer.h"

#include "nekopaw/core/CommandDispatcher.h"
#include "nekopaw/core/Config.h"

namespace nekopaw {

BridgeServer::BridgeServer(uint16_t port, CommandDispatcher& dispatcher)
    : port_(port), server_(port), dispatcher_(dispatcher) {}

void BridgeServer::begin() {
  if (started_) {
    return;
  }

  attachRoutes();
  server_.begin();
  started_ = true;

  NEKOPAW_LOGF("bridge server started on port %u", port_);
}

void BridgeServer::poll() { server_.handleClient(); }

void BridgeServer::attachRoutes() {
  server_.on("/api/bridge/device", HTTP_GET, [this]() { dispatch(&CommandDispatcher::handleDevice); });
  server_.on("/api/bridge/display/text", HTTP_POST, [this]() { dispatch(&CommandDispatcher::handleDisplayText); });
  server_.on("/api/bridge/display/bitmap", HTTP_POST, [this]() { dispatch(&CommandDispatcher::handleDisplayBitmap); },
             [this]() { dispatcher_.handleDisplayBitmapRaw(server_); });
  server_.on("/api/bridge/display/state", HTTP_GET, [this]() { dispatch(&CommandDispatcher::handleDisplayState); });
  server_.on("/api/bridge/device/description", HTTP_PATCH,
             [this]() { dispatch(&CommandDispatcher::handleDeviceDescriptionPatch); });
  server_.on("/api/bridge/sensors", HTTP_GET, [this]() { dispatch(&CommandDispatcher::handleSensors); });
  server_.on("/api/bridge/events/watch", HTTP_POST, [this]() { dispatch(&CommandDispatcher::handleEventsWatchCreate); });
  server_.on("/api/bridge/events/watch", HTTP_DELETE,
             [this]() { dispatch(&CommandDispatcher::handleEventsWatchDelete); });
  server_.on("/api/bridge/events", HTTP_GET, [this]() { dispatch(&CommandDispatcher::handleEventsPoll); });
  server_.onNotFound([this]() { dispatch(&CommandDispatcher::handleNotFound); });
}

void BridgeServer::dispatch(HandlerFn handler) {
  const uint32_t startedAt = millis();
  const int statusCode = (dispatcher_.*handler)(server_);
  const uint32_t elapsed = millis() - startedAt;

  NEKOPAW_LOGF("%s %s -> %d (%lu ms)", methodName(server_.method()), server_.uri().c_str(), statusCode,
               static_cast<unsigned long>(elapsed));
}

const char* BridgeServer::methodName(HTTPMethod method) {
  switch (method) {
    case HTTP_GET:
      return "GET";
    case HTTP_POST:
      return "POST";
    case HTTP_PUT:
      return "PUT";
    case HTTP_PATCH:
      return "PATCH";
    case HTTP_DELETE:
      return "DELETE";
    case HTTP_HEAD:
      return "HEAD";
    case HTTP_OPTIONS:
      return "OPTIONS";
    default:
      return "HTTP";
  }
}

} // namespace nekopaw
