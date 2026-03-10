#pragma once

#include <WebServer.h>

#include <stdint.h>

namespace nekopaw {

class CommandDispatcher;

class BridgeServer {
public:
  BridgeServer(uint16_t port, CommandDispatcher& dispatcher);

  void begin();
  void poll();

private:
  using HandlerFn = int (CommandDispatcher::*)(WebServer&);

  void attachRoutes();
  void dispatch(HandlerFn handler);
  static const char* methodName(HTTPMethod method);

  uint16_t port_;
  WebServer server_;
  CommandDispatcher& dispatcher_;
  bool started_ = false;
};

} // namespace nekopaw
