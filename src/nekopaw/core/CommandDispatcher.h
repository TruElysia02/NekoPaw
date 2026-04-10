#pragma once

#include <stddef.h>
#include <stdint.h>

class WebServer;

namespace nekopaw {

class NekoPaw;

class CommandDispatcher {
public:
  explicit CommandDispatcher(NekoPaw& paw);

  int handleDevice(WebServer& server);
  int handleDisplayText(WebServer& server);
  void handleDisplayBitmapRaw(WebServer& server);
  int handleDisplayBitmap(WebServer& server);
  int handleDisplayState(WebServer& server);
  void handleDisplayConfirmCreateRaw(WebServer& server);
  int handleDisplayConfirmCreate(WebServer& server);
  int handleDisplayConfirmGet(WebServer& server);
  int handleDisplayConfirmDelete(WebServer& server);
  int handleDeviceDescriptionPatch(WebServer& server);
  int handleSensors(WebServer& server);
  int handleEventsWatchCreate(WebServer& server);
  int handleEventsWatchDelete(WebServer& server);
  int handleEventsPoll(WebServer& server);
  int handleOutputs(WebServer& server);
  int handleNotFound(WebServer& server);

private:
  NekoPaw& paw_;
  uint8_t* bitmapBuffer_ = nullptr;
  size_t bitmapBufferCapacity_ = 0;
  size_t bitmapLength_ = 0;
  bool bitmapOverflow_ = false;
  size_t confirmBitmapLength_ = 0;
  bool confirmBitmapOverflow_ = false;
  bool confirmBitmapUnavailable_ = false;
  bool confirmBitmapCaptureActive_ = false;

  size_t expectedBitmapBytes() const;
  int sendDisplayUnavailable(WebServer& server);
};

} // namespace nekopaw
