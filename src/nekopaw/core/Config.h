#pragma once

#include <Arduino.h>
#include <stddef.h>
#include <stdint.h>

namespace nekopaw::core {

constexpr char kProtocolVersion[] = "1.0";
constexpr char kFirmwareVersion[] = "NekoPaw/0.1.0";
constexpr size_t kBitmapBufferLimit = 16384;
constexpr size_t kConfirmBitmapPackBufferLimit = 65536;
constexpr char kPreferencesNamespace[] = "nekopaw";
constexpr char kDescriptionKey[] = "description";

} // namespace nekopaw::core

#if defined(NEKOPAW_ENABLE_LOG) && NEKOPAW_ENABLE_LOG
#define NEKOPAW_LOG(message)                                                                                       \
  do {                                                                                                             \
    Serial.print("[NekoPaw] ");                                                                                    \
    Serial.println(message);                                                                                       \
  } while (0)
#define NEKOPAW_LOGF(fmt, ...)                                                                                     \
  do {                                                                                                             \
    Serial.printf("[NekoPaw] " fmt "\n", ##__VA_ARGS__);                                                           \
  } while (0)
#else
#define NEKOPAW_LOG(message)                                                                                       \
  do {                                                                                                             \
    (void)sizeof(message);                                                                                         \
  } while (0)
#define NEKOPAW_LOGF(...)                                                                                          \
  do {                                                                                                             \
  } while (0)
#endif
