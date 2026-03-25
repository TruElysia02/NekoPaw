#include <Arduino.h>
#include <WiFi.h>
#include <GxEPD2_BW.h>

#include <NekoPaw.h>
#include <nekopaw/adapters/AnalogSensorAdapter.h>
#include <nekopaw/adapters/ButtonInputAdapter.h>
#include <nekopaw/adapters/GxEPD2DisplayAdapter.h>
#include <nekopaw/adapters/RgbLedAdapter.h>
#include <nekopaw/adapters/SimpleBuzzerAdapter.h>

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
constexpr int kButton1Pin = 0;
constexpr int kButton2Pin = 1;
constexpr int kBatteryAdcPin = 4;
constexpr int kLedRedPin = 8;
constexpr int kLedGreenPin = 9;
constexpr int kLedBluePin = 13;
constexpr int kBuzzerPin = 12;
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

nekopaw::AnalogSensorAdapter::Config makeBatteryConfig() {
  nekopaw::AnalogSensorAdapter::Config config;
  config.pin = kBatteryAdcPin;
  config.id = "battery";
  config.type = "voltage";
  config.unit = "V";
  config.description = "Battery voltage";
  config.adcResolutionBits = 12;
  config.sampleCount = 9;
  config.sampleDelayMs = 5;
  config.multiplier = 2.0f;
  return config;
}

nekopaw::ButtonInputAdapter::Config makeButtonConfig(int pin, const char* id) {
  nekopaw::ButtonInputAdapter::Config config;
  config.pin = pin;
  config.id = id;
  return config;
}

nekopaw::RgbLedAdapter::Config makeLedConfig() {
  nekopaw::RgbLedAdapter::Config config;
  config.redPin = kLedRedPin;
  config.greenPin = kLedGreenPin;
  config.bluePin = kLedBluePin;
  config.id = "led_rgb";
  config.type = "led";
  config.activeLow = true;
  return config;
}

nekopaw::SimpleBuzzerAdapter::Config makeBuzzerConfig() {
  nekopaw::SimpleBuzzerAdapter::Config config;
  config.pin = kBuzzerPin;
  config.id = "buzzer";
  config.type = "buzzer";
  config.defaultFrequency = 1000;
  config.defaultDurationMs = 180;
  config.defaultCount = 1;
  config.gapMs = 120;
  return config;
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
const nekopaw::AnalogSensorAdapter::Config kBatteryConfig = makeBatteryConfig();
nekopaw::AnalogSensorAdapter battery(kBatteryConfig);
const nekopaw::ButtonInputAdapter::Config kButton1Config = makeButtonConfig(kButton1Pin, "button1");
const nekopaw::ButtonInputAdapter::Config kButton2Config = makeButtonConfig(kButton2Pin, "button2");
nekopaw::ButtonInputAdapter button1(kButton1Config);
nekopaw::ButtonInputAdapter button2(kButton2Config);
const nekopaw::RgbLedAdapter::Config kLedConfig = makeLedConfig();
nekopaw::RgbLedAdapter statusLed(kLedConfig);
const nekopaw::SimpleBuzzerAdapter::Config kBuzzerConfig = makeBuzzerConfig();
nekopaw::SimpleBuzzerAdapter buzzer(kBuzzerConfig);
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
  paw.addSensor(&battery);
  paw.addInput(&button1);
  paw.addInput(&button2);
  paw.addOutput(&statusLed);
  paw.addOutput(&buzzer);

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
  Serial.print("Sensors: http://");
  Serial.print(ip);
  Serial.println("/api/bridge/sensors");
  Serial.print("Events: http://");
  Serial.print(ip);
  Serial.println("/api/bridge/events");
  Serial.print("Confirm: http://");
  Serial.print(ip);
  Serial.println("/api/bridge/display/confirm");
  Serial.print("Outputs: http://");
  Serial.print(ip);
  Serial.println("/api/bridge/outputs?id=led_rgb");
}

void loop() {
  paw.loop();
  delay(10);
}
