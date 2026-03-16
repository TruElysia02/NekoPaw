#include <Arduino.h>
#include <WiFi.h>
#include <GxEPD2_BW.h>

#include <NekoPaw.h>
#include <nekopaw/adapters/GxEPD2DisplayAdapter.h>

#ifndef NEKOPAW_WIFI_SSID
#define NEKOPAW_WIFI_SSID ""
#endif

#ifndef NEKOPAW_WIFI_PASSWORD
#define NEKOPAW_WIFI_PASSWORD ""
#endif

static const bool kHasWiFiCredentials = sizeof(NEKOPAW_WIFI_SSID) > 1 && sizeof(NEKOPAW_WIFI_PASSWORD) > 1;

namespace {

constexpr int kEpdSclk = 6;
constexpr int kEpdMiso = -1;
constexpr int kEpdMosi = 7;
constexpr int kEpdCs = 10;
constexpr int kEpdDc = 3;
constexpr int kEpdRst = 2;
constexpr int kEpdBusy = 5;
constexpr uint16_t kScreenWidth = 296;
constexpr uint16_t kScreenHeight = 128;
constexpr uint8_t kScreenRotation = 3;

#if defined(NEKOPAW_EPD_DRIVER_GDEY029T94)
#include <gdey/GxEPD2_290_GDEY029T94.h>
using ExampleEpdDriver = GxEPD2_290_GDEY029T94;
#elif defined(NEKOPAW_EPD_DRIVER_T94_V2)
#include <epd/GxEPD2_290_T94_V2.h>
using ExampleEpdDriver = GxEPD2_290_T94_V2;
#elif defined(NEKOPAW_EPD_DRIVER_T94)
#include <epd/GxEPD2_290_T94.h>
using ExampleEpdDriver = GxEPD2_290_T94;
#else
#if __has_include(<gdey/GxEPD2_290_GDEY029T94.h>)
#include <gdey/GxEPD2_290_GDEY029T94.h>
using ExampleEpdDriver = GxEPD2_290_GDEY029T94;
#elif __has_include(<epd/GxEPD2_290_T94_V2.h>)
#include <epd/GxEPD2_290_T94_V2.h>
using ExampleEpdDriver = GxEPD2_290_T94_V2;
#elif __has_include(<epd/GxEPD2_290_T94.h>)
#include <epd/GxEPD2_290_T94.h>
using ExampleEpdDriver = GxEPD2_290_T94;
#else
#error "No supported 2.9-inch BW EPD driver header found for BasicDisplay."
#endif
#endif

using ExampleDisplay = GxEPD2_BW<ExampleEpdDriver, ExampleEpdDriver::HEIGHT>;

nekopaw::GxEPD2DisplayAdapter<ExampleDisplay>::Layout makeDisplayLayout() {
  nekopaw::GxEPD2DisplayAdapter<ExampleDisplay>::Layout layout;
  layout.width = kScreenWidth;
  layout.height = kScreenHeight;
  layout.rotation = kScreenRotation;
  layout.supportsPartial = true;
  return layout;
}

nekopaw::NekoPaw::Config makePawConfig() {
  nekopaw::NekoPaw::Config config;
  config.httpPort = 80;
  config.deviceId = nullptr;
  config.description = "BasicDisplay e-ink bridge";
  return config;
}

ExampleDisplay epd(ExampleEpdDriver(kEpdCs, kEpdDc, kEpdRst, kEpdBusy));
const nekopaw::GxEPD2DisplayAdapter<ExampleDisplay>::Pins kDisplayPins = {kEpdSclk, kEpdMiso, kEpdMosi, kEpdCs,
                                                                           kEpdDc,   kEpdRst,  kEpdBusy};
const nekopaw::GxEPD2DisplayAdapter<ExampleDisplay>::Layout kDisplayLayout = makeDisplayLayout();
nekopaw::GxEPD2DisplayAdapter<ExampleDisplay> display(epd, kDisplayPins, kDisplayLayout);
const nekopaw::NekoPaw::Config kPawConfig = makePawConfig();
nekopaw::NekoPaw paw(kPawConfig);

void showScreen(const char* title, const String& body, const char* footer = nullptr, const char* style = "default",
                bool fullRefresh = true) {
  nekopaw::DisplayProvider::TextContent content;
  content.title = title;
  content.body = body.c_str();
  content.footer = footer;
  content.style = style;
  (void)display.showText(content, fullRefresh);
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(NEKOPAW_WIFI_SSID, NEKOPAW_WIFI_PASSWORD);

  Serial.printf("Connecting to %s", NEKOPAW_WIFI_SSID);
  const uint32_t startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 30000UL) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
}

void showMissingCredentialsScreen() {
  showScreen("NekoPaw", "WiFi credentials missing.\nEdit platformio_override.ini", "Need SSID + PASSWORD", "alert");
}

void showConnectingScreen() {
  String body = "Connecting to WiFi...\nSSID: ";
  body += NEKOPAW_WIFI_SSID;
  showScreen("NekoPaw", body, "Waiting for network", "default");
}

void showWiFiFailureScreen() {
  showScreen("NekoPaw", "WiFi connection failed.\nCheck SSID/password", "Bridge offline", "alert");
}

void showWelcomeScreen(const String& ip) {
  String body = "WiFi connected.\nIP: ";
  body += ip;
  body += "\nGET /api/bridge/device";
  showScreen("NekoPaw Ready", body, "POST /api/bridge/display/text", "success");
}

} // namespace

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("NekoPaw BasicDisplay");

  paw.setDisplay(&display);

  if (!kHasWiFiCredentials) {
    showMissingCredentialsScreen();
    Serial.println("WiFi credentials are not configured.");
    Serial.println("Create examples/BasicDisplay/platformio_override.ini with:");
    Serial.println("  [env:airm2m_core_esp32c3]");
    Serial.println("  build_flags =");
    Serial.println("    ${env.build_flags}");
    Serial.println("    -DNEKOPAW_WIFI_SSID=\\\"your-wifi-ssid\\\"");
    Serial.println("    -DNEKOPAW_WIFI_PASSWORD=\\\"your-wifi-password\\\"");
    return;
  }

  showConnectingScreen();
  connectWiFi();
  if (WiFi.status() != WL_CONNECTED) {
    showWiFiFailureScreen();
    Serial.println("WiFi connection failed; bridge server not started.");
    return;
  }

  const String ip = WiFi.localIP().toString();
  Serial.print("WiFi connected, IP: ");
  Serial.println(ip);
  showWelcomeScreen(ip);

  if (!paw.begin()) {
    Serial.println("NekoPaw begin failed.");
    return;
  }

  Serial.print("Device info: http://");
  Serial.print(ip);
  Serial.println("/api/bridge/device");
}

void loop() {
  paw.loop();
  delay(10);
}
