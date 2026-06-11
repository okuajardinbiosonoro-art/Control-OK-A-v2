/********************************************************************************************
 * OKUA Node WiFi + UDP v1
 * ------------------------------------------------------------------
 * Base unificada para:
 *   - MODO PRUEBA
 *   - MODO CAMPO
 *   - PERFIL PLANTA
 *   - PERFIL FRUTA
 *   - LEDS activados / desactivados
 *
 * CONTRATO IMPLEMENTADO
 *   - OKUA_HDR  (8 bytes)
 *   - OKUA_EVT  (20 bytes) -> UDP OKUA_EVT_PORT=5005
 *   - OKUA_STAT (28 bytes) -> UDP OKUA_STAT_PORT=5006
 *   - OKUA_CMD  (28 bytes) -> modelo definido, parser pendiente
 *   - OKUA_ACK  (28 bytes) -> modelo definido, emision pendiente
 *
 * NOTAS IMPORTANTES
 *   1) Este sketch YA NO usa ESP-NOW ni concentrador.
 *   2) Habla UDP OKUA v1 nativo (ver=1), compatible con CKv2.
 *   3) Para FRUTA se puede configurar fanout a multiples canales/notas.
 *   4) Para PLANTA se hace traduccion a NoteOn/NoteOff real.
 *   5) Ticket 13.1 solo alinea control-plane (puertos/modelos/constantes).
 *
 * REQUIERE
 *   - ESP32
 *   - Arduino-ESP32
 *   - Adafruit_NeoPixel (solo si LED_PROFILE != LED_DISABLED)
 ********************************************************************************************/

/*============================================================================================
  ZONA 1 — SELECCION DE PERFIL GENERAL
============================================================================================*/

//-------------------- Modo de operacion -----------------------------------------------------
#define MODE_TEST   1
#define MODE_FIELD  2
#ifndef OKUA_DEFAULT_ACTIVE_MODE
#define OKUA_DEFAULT_ACTIVE_MODE MODE_TEST
#endif

//-------------------- Tipo de nodo ----------------------------------------------------------
#define SENSOR_PLANT 1
#define SENSOR_FRUIT 2
#ifndef OKUA_DEFAULT_ACTIVE_SENSOR
#define OKUA_DEFAULT_ACTIVE_SENSOR SENSOR_PLANT
#endif

//-------------------- LEDs ------------------------------------------------------------------
#define LED_DISABLED 0
#define LED_SIMPLE   1
#ifndef LED_PROFILE
#define LED_PROFILE  LED_DISABLED
#endif

//-------------------- Variante de fruta -----------------------------------------------------
#define FRUIT_VARIANT_V1 1
#define FRUIT_VARIANT_V2 2
#define FRUIT_VARIANT_V4 4
#define FRUIT_VARIANT_V3 3
#define FRUIT_VARIANT_V5 5
#define FRUIT_VARIANT_V6 6
#define FRUIT_VARIANT_V7 7
#define FRUIT_VARIANT_V8 8
#define FRUIT_VARIANT_V9 9
#define FRUIT_VARIANT_V10 10
#define FRUIT_VARIANT_V11 11
#define FRUIT_VARIANT_V12 12
#define FRUIT_VARIANT_V13 13
#define FRUIT_VARIANT_V14 14
#define FRUIT_VARIANT_V15 15
#ifndef OKUA_DEFAULT_ACTIVE_FRUIT_VARIANT
#define OKUA_DEFAULT_ACTIVE_FRUIT_VARIANT FRUIT_VARIANT_V2
#endif


/*============================================================================================
  ZONA 2 — IDENTIDAD DEL NODO / RED
============================================================================================*/

// Local overrides can be provided in a non-tracked file:
//   firmware/okua_node_udp_v1/okua_node_secrets.h
#if defined(__has_include)
#if __has_include("okua_node_secrets.h")
#include "okua_node_secrets.h"
#endif
#endif

#ifndef ACTIVE_MODE
#define ACTIVE_MODE OKUA_DEFAULT_ACTIVE_MODE
#endif

#ifndef ACTIVE_SENSOR
#define ACTIVE_SENSOR OKUA_DEFAULT_ACTIVE_SENSOR
#endif

#ifndef ACTIVE_FRUIT_VARIANT
#define ACTIVE_FRUIT_VARIANT OKUA_DEFAULT_ACTIVE_FRUIT_VARIANT
#endif

#ifdef OKUA_BUILD_NODE_LABEL
#ifdef NODE_LABEL
#undef NODE_LABEL
#endif
#define NODE_LABEL OKUA_BUILD_NODE_LABEL
#endif

#ifdef OKUA_BUILD_NODE_ID
#ifdef NODE_ID
#undef NODE_ID
#endif
#define NODE_ID OKUA_BUILD_NODE_ID
#endif

#ifdef OKUA_BUILD_WIFI_SSID
#ifdef WIFI_SSID
#undef WIFI_SSID
#endif
#define WIFI_SSID OKUA_BUILD_WIFI_SSID
#endif

#ifdef OKUA_BUILD_WIFI_PASS
#ifdef WIFI_PASS
#undef WIFI_PASS
#endif
#define WIFI_PASS OKUA_BUILD_WIFI_PASS
#endif

#ifdef OKUA_BUILD_CONTROL_SECRET
#ifdef OKUA_CONTROL_SECRET
#undef OKUA_CONTROL_SECRET
#endif
#define OKUA_CONTROL_SECRET OKUA_BUILD_CONTROL_SECRET
#endif

#ifdef OKUA_BUILD_WIFI_CHANNEL
#ifdef WIFI_CHANNEL
#undef WIFI_CHANNEL
#endif
#define WIFI_CHANNEL OKUA_BUILD_WIFI_CHANNEL
#endif

#ifdef OKUA_BUILD_PC_IP_A
#ifdef PC_IP_A
#undef PC_IP_A
#endif
#define PC_IP_A OKUA_BUILD_PC_IP_A
#endif

#ifdef OKUA_BUILD_PC_IP_B
#ifdef PC_IP_B
#undef PC_IP_B
#endif
#define PC_IP_B OKUA_BUILD_PC_IP_B
#endif

#ifdef OKUA_BUILD_PC_IP_C
#ifdef PC_IP_C
#undef PC_IP_C
#endif
#define PC_IP_C OKUA_BUILD_PC_IP_C
#endif

#ifdef OKUA_BUILD_PC_IP_D
#ifdef PC_IP_D
#undef PC_IP_D
#endif
#define PC_IP_D OKUA_BUILD_PC_IP_D
#endif

#ifdef OKUA_BUILD_DIAG_PC_IP_A
#ifdef DIAG_PC_IP_A
#undef DIAG_PC_IP_A
#endif
#define DIAG_PC_IP_A OKUA_BUILD_DIAG_PC_IP_A
#endif

#ifdef OKUA_BUILD_DIAG_PC_IP_B
#ifdef DIAG_PC_IP_B
#undef DIAG_PC_IP_B
#endif
#define DIAG_PC_IP_B OKUA_BUILD_DIAG_PC_IP_B
#endif

#ifdef OKUA_BUILD_DIAG_PC_IP_C
#ifdef DIAG_PC_IP_C
#undef DIAG_PC_IP_C
#endif
#define DIAG_PC_IP_C OKUA_BUILD_DIAG_PC_IP_C
#endif

#ifdef OKUA_BUILD_DIAG_PC_IP_D
#ifdef DIAG_PC_IP_D
#undef DIAG_PC_IP_D
#endif
#define DIAG_PC_IP_D OKUA_BUILD_DIAG_PC_IP_D
#endif

// Etiqueta visible para debug
#ifndef NODE_LABEL
#define NODE_LABEL "EB1"
#endif

// node_id segun la regla canonica del proyecto:
// Caja 1: EB1=1, EC1=2, ED1=3, EE1=4, EF1=5
// Caja 2: EB2=6, EC2=7, ED2=8, EE2=9, EF2=10
// Caja 3: EB3=11, EC3=12, ED3=13, EE3=14, EF3=15
// Caja 4: EB4=16, EC4=17, ED4=18, EE4=19, EF4=20
// Caja 5: EB5=21, EC5=22, ED5=23, EE5=24, EF5=25
#ifndef NODE_ID
#define NODE_ID 1
#endif

#ifndef WIFI_SSID
#define WIFI_SSID    "OKUA_CORE"
#endif

#ifndef WIFI_PASS
#define WIFI_PASS    "CHANGE_ME"
#endif

#ifndef OKUA_CONTROL_SECRET
#define OKUA_CONTROL_SECRET "CHANGE_ME_CONTROL_SECRET"
#endif

#ifndef WIFI_CHANNEL
#define WIFI_CHANNEL 13
#endif

#ifndef PC_IP_A
#define PC_IP_A 192
#endif

#ifndef PC_IP_B
#define PC_IP_B 168
#endif

#ifndef PC_IP_C
#define PC_IP_C 88
#endif

#ifndef PC_IP_D
#define PC_IP_D 251
#endif

#ifndef DIAG_PC_IP_A
#define DIAG_PC_IP_A PC_IP_A
#endif
#ifndef DIAG_PC_IP_B
#define DIAG_PC_IP_B PC_IP_B
#endif
#ifndef DIAG_PC_IP_C
#define DIAG_PC_IP_C PC_IP_C
#endif
#ifndef DIAG_PC_IP_D
#define DIAG_PC_IP_D PC_IP_D
#endif

#define OKUA_STR_INNER(x) #x
#define OKUA_STR(x) OKUA_STR_INNER(x)

// PC destino para EVT/STAT en la LAN OKUA
IPAddress PC_IP(PC_IP_A, PC_IP_B, PC_IP_C, PC_IP_D);
IPAddress DIAG_PC_IP(DIAG_PC_IP_A, DIAG_PC_IP_B, DIAG_PC_IP_C, DIAG_PC_IP_D);

// Firmware version
#ifndef FW_MAJOR
#define FW_MAJOR 1
#endif
#ifndef FW_MINOR
#define FW_MINOR 0
#endif
#ifndef FW_PATCH
#define FW_PATCH 0
#endif
#ifndef OKUA_FW_VERSION_STR
#define OKUA_FW_VERSION_STR "1.0.0-dev"
#endif
#ifndef OKUA_FW_VERSION_CODE
#define OKUA_FW_VERSION_CODE ((uint32_t)(FW_MAJOR) * 10000UL + (uint32_t)(FW_MINOR) * 100UL + (uint32_t)(FW_PATCH))
#endif
#ifndef OKUA_OTA_PORT
#define OKUA_OTA_PORT 18080
#endif
#ifndef OKUA_OTA_BASE_URL
#define OKUA_OTA_BASE_URL "http://" OKUA_STR(PC_IP_A) "." OKUA_STR(PC_IP_B) "." OKUA_STR(PC_IP_C) "." OKUA_STR(PC_IP_D) ":" OKUA_STR(OKUA_OTA_PORT)
#endif
#ifndef OKUA_TEST_PROBE_ENABLED
#define OKUA_TEST_PROBE_ENABLED 0
#endif
#ifndef OKUA_TEST_PROBE_LED_PIN
#define OKUA_TEST_PROBE_LED_PIN 2
#endif
#ifndef OKUA_TEST_PROBE_INTERVAL_MS
#define OKUA_TEST_PROBE_INTERVAL_MS 1000UL
#endif
#ifndef OKUA_TEST_PROBE_NOTE_START
#define OKUA_TEST_PROBE_NOTE_START 0
#endif
#ifndef OKUA_TEST_PROBE_NOTE_MAX
#define OKUA_TEST_PROBE_NOTE_MAX 80
#endif


/*============================================================================================
  ZONA 3 — HARDWARE
============================================================================================*/

#ifndef PIN_SIGNAL
#define PIN_SIGNAL 32
#endif

#ifndef FRUIT_ADC_SCAN_SERIAL
#define FRUIT_ADC_SCAN_SERIAL 0
#endif

#ifndef FRUIT_ADC_SCAN_INTERVAL_MS
#define FRUIT_ADC_SCAN_INTERVAL_MS 200UL
#endif

#if LED_PROFILE == LED_SIMPLE
  #include <Adafruit_NeoPixel.h>
  #define DATA_PIN      22
  #define LEDS_FISICOS  300
  #define LEDS_POR_PIXEL 3
  #define NUM_PIXELS    (LEDS_FISICOS / LEDS_POR_PIXEL)
  #define LED_BRIGHT    100
  Adafruit_NeoPixel strip(NUM_PIXELS, DATA_PIN, NEO_GRB + NEO_KHZ800);
#endif


/*============================================================================================
  ZONA 4 — MAPEOS MIDI
============================================================================================*/

// Ruteo sugerido del proyecto:
// bus 0 = frutas caja 1
// bus 1 = plantas grupo A
// bus 2 = plantas grupo B

//-------------------- Planta (un unico destino) ---------------------------------------------
#define PLANT_MIDI_BUS        1
#define PLANT_MIDI_CHANNEL_1B 2    // humano 1..16
#define PLANT_NOTE_LOW        32
#define PLANT_NOTE_HIGH       84

//-------------------- Fruta (fanout configurable) -------------------------------------------
struct MidiRoute {
  uint8_t midi_bus;
  uint8_t midi_channel_1b;   // 1..16 para edicion humana
  uint8_t note;
};

// Presets de ruteo para fruta (sin editar el core del sketch).
#define FRUIT_ROUTE_PRESET_EB_FANOUT 1
#define FRUIT_ROUTE_PRESET_EC_FANOUT 2
#define FRUIT_ROUTE_PRESET_CUSTOM    3

#ifndef FRUIT_ROUTE_PRESET
#define FRUIT_ROUTE_PRESET FRUIT_ROUTE_PRESET_EB_FANOUT
#endif

#ifndef FRUIT_ROUTE_NOTE
#define FRUIT_ROUTE_NOTE 57
#endif

#if FRUIT_ROUTE_PRESET == FRUIT_ROUTE_PRESET_EB_FANOUT
// EB1 -> activa EB1, ED1 y EF1
static const MidiRoute FRUIT_ROUTES[] = {
  {0, 1, FRUIT_ROUTE_NOTE},
  {0, 3, FRUIT_ROUTE_NOTE},
  {0, 5, FRUIT_ROUTE_NOTE},
};
#elif FRUIT_ROUTE_PRESET == FRUIT_ROUTE_PRESET_EC_FANOUT
// EC1 -> activa EC1 y EE1
static const MidiRoute FRUIT_ROUTES[] = {
  {0, 2, FRUIT_ROUTE_NOTE},
  {0, 4, FRUIT_ROUTE_NOTE},
};
#else
// CUSTOM -> permite override desde okua_node_secrets.h
#ifndef FRUIT_ROUTE_1_CHANNEL_1B
#define FRUIT_ROUTE_1_CHANNEL_1B 1
#endif
#ifndef FRUIT_ROUTE_1_NOTE
#define FRUIT_ROUTE_1_NOTE FRUIT_ROUTE_NOTE
#endif
#ifndef FRUIT_ROUTE_2_CHANNEL_1B
#define FRUIT_ROUTE_2_CHANNEL_1B 3
#endif
#ifndef FRUIT_ROUTE_2_NOTE
#define FRUIT_ROUTE_2_NOTE FRUIT_ROUTE_NOTE
#endif
#ifndef FRUIT_ROUTE_3_CHANNEL_1B
#define FRUIT_ROUTE_3_CHANNEL_1B 5
#endif
#ifndef FRUIT_ROUTE_3_NOTE
#define FRUIT_ROUTE_3_NOTE FRUIT_ROUTE_NOTE
#endif
static const MidiRoute FRUIT_ROUTES[] = {
  {0, FRUIT_ROUTE_1_CHANNEL_1B, FRUIT_ROUTE_1_NOTE},
  {0, FRUIT_ROUTE_2_CHANNEL_1B, FRUIT_ROUTE_2_NOTE},
  {0, FRUIT_ROUTE_3_CHANNEL_1B, FRUIT_ROUTE_3_NOTE},
};
#endif

static const uint8_t FRUIT_ROUTE_COUNT = sizeof(FRUIT_ROUTES) / sizeof(FRUIT_ROUTES[0]);

// Keepalive de fruta: por defecto desactivado para no retriggerar
#define FRUIT_KEEPALIVE_ENABLE 0
#define FRUIT_KEEPALIVE_MS     2000


/*============================================================================================
  ZONA 5 — TEMPORIZACIONES
============================================================================================*/

#define WIFI_CONNECT_TIMEOUT_MS 15000
#define WIFI_RETRY_DELAY_MS       300

#define STAT_INTERVAL_MS         1000
#ifndef SET_STAT_RATE_ALLOW_1_MS
#define SET_STAT_RATE_ALLOW_1_MS STAT_INTERVAL_MS
#endif
#ifndef SET_STAT_RATE_ALLOW_2_MS
#define SET_STAT_RATE_ALLOW_2_MS 2000
#endif
#ifndef SET_STAT_RATE_ALLOW_3_MS
#define SET_STAT_RATE_ALLOW_3_MS 5000
#endif
#ifndef SET_THROTTLE_ALLOW_1_PERCENT
#define SET_THROTTLE_ALLOW_1_PERCENT 25
#endif
#ifndef SET_THROTTLE_ALLOW_2_PERCENT
#define SET_THROTTLE_ALLOW_2_PERCENT 50
#endif
#ifndef SET_THROTTLE_ALLOW_3_PERCENT
#define SET_THROTTLE_ALLOW_3_PERCENT 100
#endif
#define TEST_PLANT_EVENT_MS       220
#define TEST_FRUIT_TOUCH_EVERY_MS 2000
#define TEST_FRUIT_TOUCH_LEN_MS    450

// Planta
#ifndef PLANT_THROTTLE_MS
#define PLANT_THROTTLE_MS         100
#endif
#define PLANT_AUTOCAL_MS        10000
#define PLANT_NOISE_FLOOR       0.008f
#define PLANT_SMOOTH_A          0.10f
#define PLANT_BASE_A            0.001f
#define PLANT_TOUCH_GAIN        7.0f
#define PLANT_MAX_JUMP_ST       6
#ifndef PLANT_DEBUG_SERIAL
#define PLANT_DEBUG_SERIAL      0
#endif
#ifndef PLANT_DEBUG_UDP
#define PLANT_DEBUG_UDP         1
#endif
#ifndef PLANT_DEBUG_UDP_PORT
#define PLANT_DEBUG_UDP_PORT    5006
#endif
#ifndef PLANT_DEBUG_UDP_INTERVAL_MS
#define PLANT_DEBUG_UDP_INTERVAL_MS 200UL
#endif
#ifndef PLANT_DEBUG_ADC_SCAN_UDP
#define PLANT_DEBUG_ADC_SCAN_UDP 0
#endif
#ifndef PLANT_DEBUG_ADC_SCAN_INTERVAL_MS
#define PLANT_DEBUG_ADC_SCAN_INTERVAL_MS 1000UL
#endif
#ifndef PLANT_EVT_FLAGS
#define PLANT_EVT_FLAGS         0
#endif
#ifndef PLANT_FORCE_NOTE_SEND
#define PLANT_FORCE_NOTE_SEND   1
#endif

// Fruta
#define FRUIT_FILTER_ALPHA      0.10f
#define FRUIT_VAR_ALPHA         0.05f
#define FRUIT_BASE_A            0.001f
#define FRUIT_BASE_CLAMP_MIN    0.05f
#define FRUIT_AUTOCAL_FAST_MS   1500
#define FRUIT_AUTOCAL_REFINE_MS 8000
#define FRUIT_HARD_TIMEOUT_MS  60000
#define FRUIT_BOOT_STUCK_REBOOT_MS 180000UL
#define FRUIT_MORNING_ARM_START_MS      20UL * 60UL * 1000UL
#define FRUIT_MORNING_ARM_END_MS        90UL * 60UL * 1000UL
#define FRUIT_MORNING_ARM_IDLE_MS       2500UL
#define FRUIT_MORNING_ARM_SIGMA_MAX     0.015f
#define FRUIT_MORNING_ARM_MIN_SCALE     0.72f
#define FRUIT_MORNING_ARM_HOLD_SCALE    0.80f
#define FRUIT_MORNING_ARM_HOLD_MIN_MS    90UL
#define FRUIT_RECOVERY_MS        650
#define FRUIT_POST_RELEASE_LOCKOUT_MS 250
#define FRUIT_RELEASE_CLEANUP_MS      250
#define FRUIT_RELEASE_CLEANUP_INTERVAL_MS 60UL
#define FRUIT_MIN_CONTACT_MS      260
#define FRUIT_STUCK_CONTACT_MS  30000UL
#define FRUIT_IDLE_STABLE_MS      2500UL
#define FRUIT_BASE_A_STABLE       0.004f
#define FRUIT_BASE_A_RECENTER     0.008f
#define FRUIT_REARM_AFTER_STUCK_MS 5000UL
#define FRUIT_REL_BASE_CAP_V    0.35f
#define FRUIT_BOOT_CAL_VALID_MIN_V 0.15f
#define FRUIT_BOOT_CAL_VALID_MAX_V 3.05f
#define FRUIT_BOOT_CAL_MAX_SPAN_V  1.00f
#define FRUIT_FSM_ENTRY_SOFT_ABS        0.050f
#define FRUIT_FSM_ENTRY_STRONG_ABS      0.130f
#define FRUIT_FSM_ENTRY_RAW_ABS         0.200f
#define FRUIT_FSM_RELEASE_BAND_ABS      0.110f
#define FRUIT_FSM_RELEASE_RAW_BAND_ABS  0.180f
#define FRUIT_FSM_RELEASE_DERIV_BAND    0.240f
#define FRUIT_FSM_SOFT_HOLD_MS         110UL
#define FRUIT_FSM_STRONG_HOLD_MS        70UL
#define FRUIT_FSM_RELEASE_HOLD_MS       220UL
#define FRUIT_FSM_LOCKOUT_MS            350UL
#define FRUIT_FSM_TIMEOUT_MS            20000UL
#define FRUIT_FSM_RELEASE_PEAK_FRAC     0.55f
#define FRUIT_FSM_RETOUCH_PEAK_FRAC     0.72f
#define FRUIT_FSM_RESCUE_RAW_ABS        0.350f
#define FRUIT_FSM_RESCUE_DV_ABS         0.180f
#define FRUIT_FSM_RESCUE_SLOPE_ABS      8.000f
#define FRUIT_FSM_RESCUE_HOLD_MS        140UL
#define FRUIT_FSM_RESCUE_MOTION_RAW_ABS 0.550f
#define FRUIT_FSM_RESCUE_MOTION_DV_ABS  0.075f
#define FRUIT_FSM_RESCUE_MOTION_SLOPE_ABS 18.000f
#define FRUIT_FSM_RESCUE_MOTION_HOLD_MS 110UL
#define FRUIT_POST_RELEASE_REARM_MS       2500UL
#define FRUIT_POST_RELEASE_REARM_DV_ABS   0.220f
#define FRUIT_POST_RELEASE_REARM_SLOPE_ABS 12.000f
#define FRUIT_V7_RELEASE_DERIV_HOLD_MS     70UL
#define FRUIT_V7_RELEASE_COLLAPSE_FRAC     0.28f
#define FRUIT_V7_RELEASE_NOENERGY_FRAC     0.55f
#define FRUIT_V7_RELEASE_DERIV_FRAC        0.72f
#define FRUIT_V7_SUSTAIN_PEAK_FRAC         0.48f
#define FRUIT_V7_RETOUCH_PEAK_FRAC         0.78f
#define FRUIT_V7_FAST_REARM_MIN_MS         260UL
#define FRUIT_V7_FAST_REARM_HOLD_MS         75UL
#define FRUIT_V7_FAST_REARM_DV_ABS          0.160f
#define FRUIT_V7_FAST_REARM_SLOPE_ABS       8.000f
#define FRUIT_V7_FAST_REARM_RAW_ABS         0.340f
#define FRUIT_V7_FAST_REARM_TH_SCALE        1.85f
#ifndef FRUIT_DEBUG_SERIAL
#define FRUIT_DEBUG_SERIAL      0
#endif
#ifndef FRUIT_DEBUG_UDP
#define FRUIT_DEBUG_UDP         0
#endif
#ifndef FRUIT_DEBUG_UDP_PORT
#define FRUIT_DEBUG_UDP_PORT    5010
#endif
#ifndef FRUIT_DEBUG_UDP_INTERVAL_MS
#define FRUIT_DEBUG_UDP_INTERVAL_MS 200UL
#endif
#ifndef FRUIT_FIXED_OFFSET_V
#define FRUIT_FIXED_OFFSET_V    (-1.0f)
#endif
#ifndef FRUIT_FIXED_OFFSET_WINDOW_V
#define FRUIT_FIXED_OFFSET_WINDOW_V 0.35f
#endif


/*============================================================================================
  ZONA 6 — INCLUDES BASE
============================================================================================*/

#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include <WiFi.h>
#include <WiFiUdp.h>
#include <esp_wifi.h>
#include <math.h>
#include <string.h>
#include <mbedtls/md.h>

#include "okua_control_plane.h"
#include "okua_build_info.h"
#include "okua_ota.h"


/*============================================================================================
  ZONA 7 — CONTROL-PLANE (TICKET 13.4)
============================================================================================*/

// Todos los modelos binarios, enums y tamanos de protocolo quedaron centralizados en:
//   - okua_control_plane.h
//
// En este ticket se implementa parser RX + ACK + seguridad minima operativa.
// Aun NO se implementan handlers ni ejecucion real de comandos.

// Forward declarations to keep Arduino auto-prototypes compatible with
// user-defined types declared later in this sketch.
enum CmdParseResult : uint8_t;
enum ReplayDecision : uint8_t;
struct ParsedCmdFrame;
struct ControlSourceState;
struct CachedCmdAck;


/*============================================================================================
  ZONA 8 — HELPERS GENERALES
============================================================================================*/

static inline float clampf(float x, float lo, float hi) {
  return (x < lo) ? lo : ((x > hi) ? hi : x);
}

static inline uint8_t clamp_u8(int v, int lo, int hi) {
  if (v < lo) return (uint8_t)lo;
  if (v > hi) return (uint8_t)hi;
  return (uint8_t)v;
}

static inline int8_t currentRssiDbm() {
  if (WiFi.status() != WL_CONNECTED) return 127; // N/A segun spec
  long r = WiFi.RSSI();
  if (r < -127) r = -127;
  if (r > 0) r = 0;
  return (int8_t)r;
}

static inline uint8_t toMidiCh0(uint8_t ch1b) {
  if (ch1b < 1) return 0;
  if (ch1b > 16) return 15;
  return (uint8_t)(ch1b - 1);
}

float readV() {
  return analogRead(PIN_SIGNAL) * (3.3f / 4095.0f);
}

static inline float readVPin(uint8_t pin) {
  return analogRead(pin) * (3.3f / 4095.0f);
}

float readVmed3() {
  float a = readV();
  float b = readV();
  float c = readV();
  if ((a <= b && b <= c) || (c <= b && b <= a)) return b;
  if ((b <= a && a <= c) || (c <= a && a <= b)) return a;
  return c;
}

#if FRUIT_ADC_SCAN_SERIAL || PLANT_DEBUG_ADC_SCAN_UDP
static const uint8_t kFruitAdcScanPins[] = {32, 33, 34, 35, 36, 39};
static unsigned long g_fruitAdcScanLastMs = 0;

void serviceFruitAdcScan() {
  if (ACTIVE_SENSOR != SENSOR_FRUIT) return;

  const unsigned long now = millis();
  if ((now - g_fruitAdcScanLastMs) < FRUIT_ADC_SCAN_INTERVAL_MS) return;
  g_fruitAdcScanLastMs = now;

  Serial.print("[ADC_SCAN] sel=");
  Serial.print(PIN_SIGNAL);

  for (size_t i = 0; i < (sizeof(kFruitAdcScanPins) / sizeof(kFruitAdcScanPins[0])); ++i) {
    const uint8_t pin = kFruitAdcScanPins[i];
    const int raw = analogRead(pin);
    const float v = raw * (3.3f / 4095.0f);
    Serial.print(" p");
    Serial.print(pin);
    Serial.print("=");
    Serial.print(v, 3);
    Serial.print("(");
    Serial.print(raw);
    Serial.print(")");
    if (pin == PIN_SIGNAL) Serial.print("*");
  }
  Serial.println();
}
#else
void serviceFruitAdcScan() {}
#endif


/*============================================================================================
  ZONA 9 — LEDS SIMPLES (OPCIONAL)
============================================================================================*/

#if LED_PROFILE == LED_SIMPLE
uint32_t noteToColor(uint8_t note) {
  if (note <= 40) return strip.Color(0, 255, 0);
  if (note <= 50) return strip.Color(255, 180, 0);
  if (note <= 60) return strip.Color(255, 0, 255);
  if (note <= 80) return strip.Color(120, 180, 255);
  return strip.Color(255, 255, 255);
}

void ledInit() {
  strip.begin();
  strip.clear();
  strip.setBrightness(LED_BRIGHT);
  strip.show();
}

void ledOff() {
  strip.clear();
  strip.show();
}

void ledShowNote(uint8_t note) {
  uint32_t c = noteToColor(note);
  strip.fill(c);
  strip.show();
}
#else
void ledInit() {}
void ledOff() {}
void ledShowNote(uint8_t note) { (void)note; }
#endif


/*============================================================================================
  ZONA 10 — ESTADO GLOBAL DE RED / UDP
============================================================================================*/

WiFiUDP g_udp;
bool g_udpBegun = false;
bool g_wifiWasConnected = false;

uint16_t g_seqEvt = 0;
uint16_t g_seqStat = 0;

uint32_t g_lastStatMs = 0;
uint32_t g_statIntervalMs = STAT_INTERVAL_MS;
uint16_t g_plantThrottlePercent = (uint16_t)SET_THROTTLE_ALLOW_3_PERCENT;
uint32_t g_plantThrottleMs = (uint32_t)PLANT_THROTTLE_MS;
uint32_t g_evtCountSinceLastStat = 0;
uint32_t g_lastEvtCounterResetMs = 0;

uint8_t g_lastStateFlags = 0;
RTC_DATA_ATTR uint32_t g_bootCounter = 0;
uint8_t g_bootMarker4 = 0;
static const uint32_t CONTROL_REBOOT_DELAY_MS = 150UL;
bool g_rebootPending = false;
uint32_t g_rebootAtMs = 0;
bool g_loopInitialized = false;

static const OkuaBuildInfoConfig kOkuaBuildInfoConfig = {
  (uint8_t)FW_MAJOR,
  (uint8_t)FW_MINOR,
  (uint8_t)FW_PATCH,
  OKUA_FW_VERSION_STR,
  (uint32_t)OKUA_FW_VERSION_CODE,
  (ACTIVE_SENSOR == SENSOR_PLANT) ? "plant" : "fruit",
  NODE_LABEL,
  (ACTIVE_MODE == MODE_FIELD) ? "field" : "test",
  "okua_v1",
  "okua_node_udp_v1",
  "esp32dev",
};

static const OkuaOtaConfig kOkuaOtaConfig = {
  OKUA_OTA_BASE_URL,
  45000UL,
  8000UL,
};

enum CmdParseResult : uint8_t {
  CMD_PARSE_NONE = 0,
  CMD_PARSE_OK_UNICAST,
  CMD_PARSE_OK_BROADCAST,
  CMD_PARSE_BROADCAST_NOT_ALLOWED,
  CMD_PARSE_DROP_NOT_FOR_ME,
  CMD_PARSE_INVALID_SIZE,
  CMD_PARSE_INVALID_MAGIC,
  CMD_PARSE_INVALID_VERSION,
  CMD_PARSE_INVALID_TYPE,
  CMD_PARSE_UNSUPPORTED_CMD,
};

struct ParsedCmdFrame {
  OkuaCmdPacket packet;
  IPAddress src_ip;
  uint16_t src_port;
  uint16_t packet_size;
  CmdParseResult result;
  bool is_broadcast;
  bool is_for_this_node;
};

// Last parsed frame/result kept for control-plane traceability.
CmdParseResult g_lastCmdParseResult = CMD_PARSE_NONE;
ParsedCmdFrame g_lastParsedCmdFrame = {};

static const uint8_t CONTROL_SOURCE_STATE_CAP = 8;
static const uint16_t CONTROL_ACK_CACHE_CAP = 128;
static const uint32_t CONTROL_ACK_CACHE_TTL_MS = 120000UL;
static const uint8_t CONTROL_REPLAY_WINDOW_NONCES = 128;
static const float CONTROL_RATE_LIMIT_CAPACITY = 10.0f;
static const float CONTROL_RATE_LIMIT_REFILL_PER_SEC = 1.0f;
static const uint8_t ACK_FLAG_DUPLICATE = 0x01;
static const uint8_t ACK_FLAG_BROADCAST_RESPONSE = 0x02;

enum ReplayDecision : uint8_t {
  REPLAY_ACCEPT = 0,
  REPLAY_REUSED,
  REPLAY_OUT_OF_WINDOW,
};

struct ControlSourceState {
  bool used;
  IPAddress src_ip;
  uint32_t last_seen_ms;
  bool replay_initialized;
  uint64_t replay_max_nonce;
  uint64_t replay_seen_lo;
  uint64_t replay_seen_hi;
  float rl_tokens;
  uint32_t rl_last_refill_ms;
};

struct CachedCmdAck {
  bool used;
  IPAddress src_ip;
  uint16_t cmd_seq;
  uint64_t nonce;
  uint8_t cmd_id;
  uint16_t arg0;
  uint16_t arg1;
  uint32_t expires_at_ms;
  OkuaAckPacket ack_packet;
};

ControlSourceState g_control_sources[CONTROL_SOURCE_STATE_CAP] = {};
CachedCmdAck g_cmd_ack_cache[CONTROL_ACK_CACHE_CAP] = {};

static inline bool ipAddressEquals(const IPAddress& a, const IPAddress& b) {
  return a == b;
}

static inline bool millisReached(uint32_t now_ms, uint32_t when_ms) {
  return (int32_t)(now_ms - when_ms) >= 0;
}

static inline uint32_t u32FromLeBytes(const uint8_t* b) {
  return (uint32_t)b[0] |
         ((uint32_t)b[1] << 8) |
         ((uint32_t)b[2] << 16) |
         ((uint32_t)b[3] << 24);
}

static inline bool constantTimeEqU32(uint32_t a, uint32_t b) {
  uint8_t diff = 0;
  diff |= (uint8_t)((a >> 0) & 0xFF) ^ (uint8_t)((b >> 0) & 0xFF);
  diff |= (uint8_t)((a >> 8) & 0xFF) ^ (uint8_t)((b >> 8) & 0xFF);
  diff |= (uint8_t)((a >> 16) & 0xFF) ^ (uint8_t)((b >> 16) & 0xFF);
  diff |= (uint8_t)((a >> 24) & 0xFF) ^ (uint8_t)((b >> 24) & 0xFF);
  return diff == 0;
}

bool computeHmacSha256(const uint8_t* msg, size_t msg_len, uint8_t out_digest[32]) {
  const mbedtls_md_info_t* md_info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (md_info == nullptr) return false;

  const uint8_t* key = (const uint8_t*)OKUA_CONTROL_SECRET;
  const size_t key_len = strlen(OKUA_CONTROL_SECRET);
  int rc = mbedtls_md_hmac(md_info, key, key_len, msg, msg_len, out_digest);
  return rc == 0;
}

bool computeCmdAuthTag32(const OkuaCmdPacket& cmd, uint32_t* out_tag32) {
  if (out_tag32 == nullptr) return false;
  uint8_t digest[32] = {};
  if (!computeHmacSha256((const uint8_t*)&cmd, 24, digest)) return false;
  *out_tag32 = u32FromLeBytes(digest);
  return true;
}

bool computeAckAuthTag32(const OkuaAckPacket& ack, uint32_t* out_tag32) {
  if (out_tag32 == nullptr) return false;
  uint8_t digest[32] = {};
  if (!computeHmacSha256((const uint8_t*)&ack, 24, digest)) return false;
  *out_tag32 = u32FromLeBytes(digest);
  return true;
}

bool isCmdAuthTagValid(const OkuaCmdPacket& cmd) {
  uint32_t expected = 0;
  if (!computeCmdAuthTag32(cmd, &expected)) return false;
  return constantTimeEqU32(expected, cmd.auth_tag32);
}

bool setAckAuthTag32(OkuaAckPacket* ack) {
  if (ack == nullptr) return false;
  uint32_t tag = 0;
  if (!computeAckAuthTag32(*ack, &tag)) return false;
  ack->auth_tag32 = tag;
  return true;
}

ControlSourceState* getOrCreateControlSourceState(const IPAddress& src_ip, uint32_t now_ms) {
  ControlSourceState* free_slot = nullptr;
  ControlSourceState* oldest_slot = nullptr;

  for (uint8_t i = 0; i < CONTROL_SOURCE_STATE_CAP; ++i) {
    ControlSourceState* s = &g_control_sources[i];
    if (s->used) {
      if (ipAddressEquals(s->src_ip, src_ip)) {
        s->last_seen_ms = now_ms;
        return s;
      }
      if ((oldest_slot == nullptr) || millisReached(oldest_slot->last_seen_ms, s->last_seen_ms)) {
        oldest_slot = s;
      }
    } else if (free_slot == nullptr) {
      free_slot = s;
    }
  }

  ControlSourceState* chosen = (free_slot != nullptr) ? free_slot : oldest_slot;
  if (chosen == nullptr) return nullptr;

  *chosen = {};
  chosen->used = true;
  chosen->src_ip = src_ip;
  chosen->last_seen_ms = now_ms;
  chosen->replay_initialized = false;
  chosen->replay_max_nonce = 0;
  chosen->replay_seen_lo = 0;
  chosen->replay_seen_hi = 0;
  chosen->rl_tokens = CONTROL_RATE_LIMIT_CAPACITY;
  chosen->rl_last_refill_ms = now_ms;
  return chosen;
}

static inline void replayShiftWindow(ControlSourceState* state, uint64_t shift_bits) {
  if (state == nullptr) return;
  if (shift_bits >= CONTROL_REPLAY_WINDOW_NONCES) {
    state->replay_seen_lo = 0;
    state->replay_seen_hi = 0;
    return;
  }

  if (shift_bits >= 64) {
    const uint64_t k = shift_bits - 64;
    state->replay_seen_hi = (k == 0) ? state->replay_seen_lo : (state->replay_seen_lo << k);
    state->replay_seen_lo = 0;
    return;
  }

  if (shift_bits > 0) {
    state->replay_seen_hi = (state->replay_seen_hi << shift_bits) | (state->replay_seen_lo >> (64 - shift_bits));
    state->replay_seen_lo <<= shift_bits;
  }
}

static inline bool replayIsSeen(const ControlSourceState* state, uint8_t delta) {
  if (state == nullptr) return false;
  if (delta < 64) {
    return ((state->replay_seen_lo >> delta) & 1ULL) != 0ULL;
  }
  return ((state->replay_seen_hi >> (delta - 64)) & 1ULL) != 0ULL;
}

static inline void replayMarkSeen(ControlSourceState* state, uint8_t delta) {
  if (state == nullptr) return;
  if (delta < 64) {
    state->replay_seen_lo |= (1ULL << delta);
    return;
  }
  state->replay_seen_hi |= (1ULL << (delta - 64));
}

ReplayDecision evaluateAndRecordNonce(ControlSourceState* state, uint64_t nonce) {
  if (state == nullptr) return REPLAY_OUT_OF_WINDOW;

  if (!state->replay_initialized) {
    state->replay_initialized = true;
    state->replay_max_nonce = nonce;
    state->replay_seen_lo = 1ULL;
    state->replay_seen_hi = 0ULL;
    return REPLAY_ACCEPT;
  }

  if (nonce > state->replay_max_nonce) {
    const uint64_t diff = nonce - state->replay_max_nonce;
    replayShiftWindow(state, diff);
    state->replay_max_nonce = nonce;
    replayMarkSeen(state, 0);
    return REPLAY_ACCEPT;
  }

  const uint64_t delta64 = state->replay_max_nonce - nonce;
  if (delta64 >= CONTROL_REPLAY_WINDOW_NONCES) {
    return REPLAY_OUT_OF_WINDOW;
  }

  const uint8_t delta = (uint8_t)delta64;
  if (replayIsSeen(state, delta)) {
    return REPLAY_REUSED;
  }

  replayMarkSeen(state, delta);
  return REPLAY_ACCEPT;
}

void refillRateLimitTokens(ControlSourceState* state, uint32_t now_ms) {
  if (state == nullptr) return;
  const uint32_t elapsed_ms = now_ms - state->rl_last_refill_ms;
  if (elapsed_ms == 0) return;

  const float refill = ((float)elapsed_ms / 1000.0f) * CONTROL_RATE_LIMIT_REFILL_PER_SEC;
  state->rl_tokens += refill;
  if (state->rl_tokens > CONTROL_RATE_LIMIT_CAPACITY) {
    state->rl_tokens = CONTROL_RATE_LIMIT_CAPACITY;
  }
  state->rl_last_refill_ms = now_ms;
}

bool consumeRateLimitToken(ControlSourceState* state, uint32_t now_ms, uint16_t* out_retry_after_ms) {
  if (state == nullptr) return false;
  if (out_retry_after_ms != nullptr) *out_retry_after_ms = 0;

  refillRateLimitTokens(state, now_ms);

  if (state->rl_tokens >= 1.0f) {
    state->rl_tokens -= 1.0f;
    return true;
  }

  const float deficit = 1.0f - state->rl_tokens;
  uint32_t retry_after_ms = (uint32_t)ceilf((deficit / CONTROL_RATE_LIMIT_REFILL_PER_SEC) * 1000.0f);
  if (retry_after_ms == 0) retry_after_ms = 1;
  if (retry_after_ms > 65535UL) retry_after_ms = 65535UL;
  if (out_retry_after_ms != nullptr) {
    *out_retry_after_ms = (uint16_t)retry_after_ms;
  }
  return false;
}

void applyAckFlagsForFrame(const ParsedCmdFrame& frame, OkuaAckPacket* ack) {
  if (ack == nullptr) return;
  if (frame.is_broadcast) {
    ack->ack_flags |= ACK_FLAG_BROADCAST_RESPONSE;
  } else {
    ack->ack_flags &= (uint8_t)~ACK_FLAG_BROADCAST_RESPONSE;
  }
}

void cleanupExpiredAckCache(uint32_t now_ms) {
  for (uint16_t i = 0; i < CONTROL_ACK_CACHE_CAP; ++i) {
    CachedCmdAck* e = &g_cmd_ack_cache[i];
    if (!e->used) continue;
    if (millisReached(now_ms, e->expires_at_ms)) {
      e->used = false;
    }
  }
}

static inline bool cacheKeyEquals(const CachedCmdAck& e, const ParsedCmdFrame& frame) {
  return ipAddressEquals(e.src_ip, frame.src_ip) &&
         e.cmd_seq == frame.packet.hdr.seq &&
         e.nonce == frame.packet.nonce &&
         e.cmd_id == frame.packet.cmd_id &&
         e.arg0 == frame.packet.arg0 &&
         e.arg1 == frame.packet.arg1;
}

CachedCmdAck* findExactAckCacheEntry(const ParsedCmdFrame& frame, uint32_t now_ms) {
  cleanupExpiredAckCache(now_ms);
  for (uint16_t i = 0; i < CONTROL_ACK_CACHE_CAP; ++i) {
    CachedCmdAck* e = &g_cmd_ack_cache[i];
    if (!e->used) continue;
    if (cacheKeyEquals(*e, frame)) return e;
  }
  return nullptr;
}

bool hasNonceSeqConflictInCache(const ParsedCmdFrame& frame, uint32_t now_ms) {
  cleanupExpiredAckCache(now_ms);
  for (uint16_t i = 0; i < CONTROL_ACK_CACHE_CAP; ++i) {
    const CachedCmdAck& e = g_cmd_ack_cache[i];
    if (!e.used) continue;
    if (!ipAddressEquals(e.src_ip, frame.src_ip)) continue;
    if (e.cmd_seq != frame.packet.hdr.seq) continue;
    if (e.nonce != frame.packet.nonce) continue;
    if (e.cmd_id == frame.packet.cmd_id &&
        e.arg0 == frame.packet.arg0 &&
        e.arg1 == frame.packet.arg1) {
      continue;
    }
    return true;
  }
  return false;
}

void storeAckCacheEntry(const ParsedCmdFrame& frame, const OkuaAckPacket& ack, uint32_t now_ms) {
  cleanupExpiredAckCache(now_ms);

  CachedCmdAck* target = findExactAckCacheEntry(frame, now_ms);
  if (target == nullptr) {
    for (uint16_t i = 0; i < CONTROL_ACK_CACHE_CAP; ++i) {
      if (!g_cmd_ack_cache[i].used) {
        target = &g_cmd_ack_cache[i];
        break;
      }
    }
  }

  if (target == nullptr) {
    target = &g_cmd_ack_cache[0];
    for (uint16_t i = 1; i < CONTROL_ACK_CACHE_CAP; ++i) {
      if (millisReached(target->expires_at_ms, g_cmd_ack_cache[i].expires_at_ms)) {
        target = &g_cmd_ack_cache[i];
      }
    }
  }

  target->used = true;
  target->src_ip = frame.src_ip;
  target->cmd_seq = frame.packet.hdr.seq;
  target->nonce = frame.packet.nonce;
  target->cmd_id = frame.packet.cmd_id;
  target->arg0 = frame.packet.arg0;
  target->arg1 = frame.packet.arg1;
  target->expires_at_ms = now_ms + CONTROL_ACK_CACHE_TTL_MS;
  target->ack_packet = ack;
}

static inline bool okuaIsKnownCmdId(uint8_t cmd_id) {
  switch (cmd_id) {
    case OKUA_CMD_PING:
    case OKUA_CMD_REBOOT_SOFT:
    case OKUA_CMD_SET_PROFILE:
    case OKUA_CMD_SET_THROTTLE:
    case OKUA_CMD_SET_STAT_RATE:
    case OKUA_CMD_SET_DEBUG:
    case OKUA_CMD_REQUEST_STAT_NOW:
    case OKUA_CMD_OTA_CHECK_NOW:
      return true;
    default:
      return false;
  }
}

// Distinct from protocol-known IDs:
// only these commands are functionally implemented in current firmware.
static inline bool okuaIsImplementedCmdId(uint8_t cmd_id) {
  switch (cmd_id) {
    case OKUA_CMD_PING:
    case OKUA_CMD_REQUEST_STAT_NOW:
    case OKUA_CMD_REBOOT_SOFT:
    case OKUA_CMD_SET_THROTTLE:
    case OKUA_CMD_SET_STAT_RATE:
    case OKUA_CMD_OTA_CHECK_NOW:
      return true;
    default:
      return false;
  }
}

static inline bool isAllowedSetThrottlePercent(uint16_t throttle_percent) {
  return (throttle_percent == (uint16_t)SET_THROTTLE_ALLOW_1_PERCENT) ||
         (throttle_percent == (uint16_t)SET_THROTTLE_ALLOW_2_PERCENT) ||
         (throttle_percent == (uint16_t)SET_THROTTLE_ALLOW_3_PERCENT);
}

static inline uint32_t setThrottlePercentToMs(uint16_t throttle_percent) {
  if (throttle_percent == 0) return (uint32_t)PLANT_THROTTLE_MS;
  const uint32_t numerator = ((uint32_t)PLANT_THROTTLE_MS) * 100UL;
  uint32_t throttle_ms = (numerator + (uint32_t)throttle_percent - 1UL) / (uint32_t)throttle_percent;
  if (throttle_ms == 0) throttle_ms = 1;
  return throttle_ms;
}

static inline bool isAllowedSetStatRateMs(uint16_t rate_ms) {
  return (rate_ms == (uint16_t)SET_STAT_RATE_ALLOW_1_MS) ||
         (rate_ms == (uint16_t)SET_STAT_RATE_ALLOW_2_MS) ||
         (rate_ms == (uint16_t)SET_STAT_RATE_ALLOW_3_MS);
}

void applyCommandSpecificAckPolicy(const ParsedCmdFrame& frame, OkuaAckPacket* ack) {
  if (ack == nullptr) return;
  if (ack->ack_stage != OKUA_ACK_STAGE_ACCEPTED || ack->status_code != OKUA_STATUS_OK) return;

  switch (frame.packet.cmd_id) {
    case OKUA_CMD_SET_THROTTLE: {
      if (frame.packet.arg1 != 0) {
        ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
        ack->status_code = OKUA_STATUS_INVALID_ARG;
        ack->err_detail = OKUA_ERR_ARG1_OUT_OF_RANGE;
        break;
      }
      if (!isAllowedSetThrottlePercent(frame.packet.arg0)) {
        ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
        ack->status_code = OKUA_STATUS_INVALID_ARG;
        ack->err_detail = OKUA_ERR_THROTTLE_INVALID;
        break;
      }
      // Valid SET_THROTTLE remains ACCEPTED + OK (no EXECUTED stage in this flow).
      ack->ack_stage = OKUA_ACK_STAGE_ACCEPTED;
      ack->status_code = OKUA_STATUS_OK;
      ack->err_detail = OKUA_ERR_NONE;
      break;
    }

    case OKUA_CMD_SET_STAT_RATE: {
      if (frame.packet.arg1 != 0) {
        ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
        ack->status_code = OKUA_STATUS_INVALID_ARG;
        ack->err_detail = OKUA_ERR_ARG1_OUT_OF_RANGE;
        break;
      }
      if (!isAllowedSetStatRateMs(frame.packet.arg0)) {
        ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
        ack->status_code = OKUA_STATUS_INVALID_ARG;
        ack->err_detail = OKUA_ERR_STAT_RATE_INVALID;
        break;
      }
      // Valid SET_STAT_RATE remains ACCEPTED + OK (no EXECUTED stage in this flow).
      ack->ack_stage = OKUA_ACK_STAGE_ACCEPTED;
      ack->status_code = OKUA_STATUS_OK;
      ack->err_detail = OKUA_ERR_NONE;
      break;
    }

    case OKUA_CMD_OTA_CHECK_NOW: {
      if (frame.packet.arg0 == 0 && frame.packet.arg1 == 0) {
        ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
        ack->status_code = OKUA_STATUS_INVALID_ARG;
        ack->err_detail = OKUA_ERR_ARG0_OUT_OF_RANGE;
        break;
      }
      const OkuaOtaTelemetry ota = okuaOtaGetTelemetry();
      if ((ota.flags & OKUA_OTA_FLAG_CHECK_PENDING) != 0 ||
          (ota.flags & OKUA_OTA_FLAG_PENDING_VERIFY) != 0 ||
          ota.state_code == OKUA_OTA_STATE_DOWNLOADING) {
        ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
        ack->status_code = OKUA_STATUS_BUSY;
        ack->err_detail = OKUA_ERR_CMD_IN_PROGRESS;
        break;
      }
      ack->ack_stage = OKUA_ACK_STAGE_ACCEPTED;
      ack->status_code = OKUA_STATUS_OK;
      ack->err_detail = OKUA_ERR_NONE;
      break;
    }

    default:
      break;
  }
}

static inline bool okuaIsBroadcastAllowedCmdId(uint8_t cmd_id) {
  return (cmd_id == OKUA_CMD_PING) || (cmd_id == OKUA_CMD_REQUEST_STAT_NOW);
}

static inline void initParsedCmdFrame(ParsedCmdFrame* frame) {
  if (frame == nullptr) return;
  *frame = {};
  frame->result = CMD_PARSE_NONE;
}

// Reads exactly one UDP datagram when available and always drains any remainder.
// Returns read bytes copied to buffer (0 when no datagram is available).
int readIncomingCmdDatagram(
    uint8_t* buffer,
    size_t buffer_len,
    IPAddress* src_ip,
    uint16_t* src_port,
    uint16_t* packet_size) {
  int parsedSize = g_udp.parsePacket();
  if (parsedSize <= 0) return 0;

  if (src_ip != nullptr) *src_ip = g_udp.remoteIP();
  if (src_port != nullptr) *src_port = g_udp.remotePort();
  if (packet_size != nullptr) {
    *packet_size = (parsedSize > 65535) ? 65535 : (uint16_t)parsedSize;
  }

  int toRead = parsedSize;
  if (toRead > (int)buffer_len) toRead = (int)buffer_len;

  int readBytes = g_udp.read(buffer, (size_t)toRead);
  while (g_udp.available() > 0) {
    g_udp.read();
  }
  return readBytes;
}

CmdParseResult parseIncomingCmdFrame(ParsedCmdFrame* frame) {
  if (frame == nullptr) return CMD_PARSE_NONE;
  initParsedCmdFrame(frame);
  if (!g_udpBegun) return frame->result;

  uint8_t rawCmd[OKUA_CMD_SIZE];
  int readBytes = readIncomingCmdDatagram(
      rawCmd,
      sizeof(rawCmd),
      &frame->src_ip,
      &frame->src_port,
      &frame->packet_size);

  if (readBytes <= 0) {
    return frame->result;
  }

  if (!okuaIsCmdPacketSizeValid((size_t)frame->packet_size) ||
      readBytes != (int)OKUA_CMD_SIZE) {
    frame->result = CMD_PARSE_INVALID_SIZE;
    return frame->result;
  }

  memcpy(&frame->packet, rawCmd, sizeof(OkuaCmdPacket));

  if (frame->packet.hdr.magic != OKUA_MAGIC) {
    frame->result = CMD_PARSE_INVALID_MAGIC;
    return frame->result;
  }

  if (frame->packet.hdr.ver != OKUA_PROTOCOL_VERSION) {
    frame->result = CMD_PARSE_INVALID_VERSION;
    return frame->result;
  }

  if (frame->packet.hdr.type != OKUA_TYPE_CMD) {
    frame->result = CMD_PARSE_INVALID_TYPE;
    return frame->result;
  }

  frame->is_broadcast = (frame->packet.hdr.node_id == 0);
  frame->is_for_this_node = (frame->packet.hdr.node_id == NODE_ID);

  if (!frame->is_broadcast && !frame->is_for_this_node) {
    frame->result = CMD_PARSE_DROP_NOT_FOR_ME;
    return frame->result;
  }

  if (!okuaIsKnownCmdId(frame->packet.cmd_id)) {
    frame->result = CMD_PARSE_UNSUPPORTED_CMD;
    return frame->result;
  }

  if (frame->is_broadcast && !okuaIsBroadcastAllowedCmdId(frame->packet.cmd_id)) {
    frame->result = CMD_PARSE_BROADCAST_NOT_ALLOWED;
    return frame->result;
  }

  frame->result = frame->is_broadcast ? CMD_PARSE_OK_BROADCAST : CMD_PARSE_OK_UNICAST;
  return frame->result;
}

static inline bool shouldEmitAckForParseResult(CmdParseResult result) {
  switch (result) {
    case CMD_PARSE_OK_UNICAST:
    case CMD_PARSE_OK_BROADCAST:
    case CMD_PARSE_UNSUPPORTED_CMD:
    case CMD_PARSE_BROADCAST_NOT_ALLOWED:
      return true;
    default:
      return false;
  }
}

void fillAckForParseResult(const ParsedCmdFrame& frame, OkuaAckPacket* ack) {
  if (ack == nullptr) return;

  okuaInitAckSkeleton(
      ack,
      NODE_ID,
      frame.packet.hdr.seq,  // cmd_seq echo
      frame.packet.cmd_id,   // cmd_id echo
      frame.packet.nonce);   // nonce echo

  ack->auth_tag32 = 0;
  ack->retry_after_ms = 0;
  applyAckFlagsForFrame(frame, ack);

  switch (frame.result) {
    case CMD_PARSE_OK_UNICAST:
    case CMD_PARSE_OK_BROADCAST:
      if (okuaIsImplementedCmdId(frame.packet.cmd_id)) {
        ack->ack_stage = OKUA_ACK_STAGE_ACCEPTED;
        ack->status_code = OKUA_STATUS_OK;
        ack->err_detail = OKUA_ERR_NONE;
      } else {
        ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
        ack->status_code = OKUA_STATUS_UNSUPPORTED_CMD;
        ack->err_detail = OKUA_ERR_NONE;
      }
      break;

    case CMD_PARSE_UNSUPPORTED_CMD:
      ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
      ack->status_code = OKUA_STATUS_UNSUPPORTED_CMD;
      ack->err_detail = OKUA_ERR_NONE;
      break;

    case CMD_PARSE_BROADCAST_NOT_ALLOWED:
      ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
      ack->status_code = OKUA_STATUS_INVALID_ARG;
      ack->err_detail = OKUA_ERR_BROADCAST_NOT_ALLOWED;
      break;

    default:
      // Should never be emitted, but keep deterministic fallback.
      ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
      ack->status_code = OKUA_STATUS_INTERNAL_ERROR;
      ack->err_detail = OKUA_ERR_MALFORMED_PACKET;
      break;
  }
}

void fillSecurityRejectionAck(
    const ParsedCmdFrame& frame,
    uint8_t status_code,
    uint16_t err_detail,
    uint16_t retry_after_ms,
    OkuaAckPacket* ack) {
  if (ack == nullptr) return;

  okuaInitAckSkeleton(
      ack,
      NODE_ID,
      frame.packet.hdr.seq,  // cmd_seq echo
      frame.packet.cmd_id,   // cmd_id echo
      frame.packet.nonce);   // nonce echo

  ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
  ack->status_code = status_code;
  ack->err_detail = err_detail;
  ack->retry_after_ms = retry_after_ms;
  ack->auth_tag32 = 0;
  applyAckFlagsForFrame(frame, ack);
}

bool buildAckForFrameWithSecurity(const ParsedCmdFrame& frame, OkuaAckPacket* ack) {
  if (ack == nullptr) return false;

  const uint32_t now_ms = millis();

  if (!isCmdAuthTagValid(frame.packet)) {
    fillSecurityRejectionAck(
        frame,
        OKUA_STATUS_INVALID_AUTH,
        OKUA_ERR_AUTH_TAG_MISMATCH,
        0,
        ack);
    return setAckAuthTag32(ack);
  }

  ControlSourceState* src_state = getOrCreateControlSourceState(frame.src_ip, now_ms);
  if (src_state == nullptr) {
    fillSecurityRejectionAck(
        frame,
        OKUA_STATUS_INTERNAL_ERROR,
        OKUA_ERR_MALFORMED_PACKET,
        0,
        ack);
    return setAckAuthTag32(ack);
  }

  CachedCmdAck* exact_dup = findExactAckCacheEntry(frame, now_ms);
  if (exact_dup != nullptr) {
    *ack = exact_dup->ack_packet;
    applyAckFlagsForFrame(frame, ack);
    ack->ack_flags |= ACK_FLAG_DUPLICATE;
    return setAckAuthTag32(ack);
  }

  if (hasNonceSeqConflictInCache(frame, now_ms)) {
    fillSecurityRejectionAck(
        frame,
        OKUA_STATUS_REPLAY_REJECTED,
        OKUA_ERR_NONCE_REUSED,
        0,
        ack);
    if (!setAckAuthTag32(ack)) return false;
    storeAckCacheEntry(frame, *ack, now_ms);
    return true;
  }

  ReplayDecision replay = evaluateAndRecordNonce(src_state, frame.packet.nonce);
  if (replay == REPLAY_REUSED) {
    fillSecurityRejectionAck(
        frame,
        OKUA_STATUS_REPLAY_REJECTED,
        OKUA_ERR_NONCE_REUSED,
        0,
        ack);
    if (!setAckAuthTag32(ack)) return false;
    storeAckCacheEntry(frame, *ack, now_ms);
    return true;
  }
  if (replay == REPLAY_OUT_OF_WINDOW) {
    fillSecurityRejectionAck(
        frame,
        OKUA_STATUS_REPLAY_REJECTED,
        OKUA_ERR_NONCE_OUT_OF_WINDOW,
        0,
        ack);
    if (!setAckAuthTag32(ack)) return false;
    storeAckCacheEntry(frame, *ack, now_ms);
    return true;
  }

  uint16_t retry_after_ms = 0;
  if (!consumeRateLimitToken(src_state, now_ms, &retry_after_ms)) {
    fillSecurityRejectionAck(
        frame,
        OKUA_STATUS_RATE_LIMITED,
        OKUA_ERR_RATE_LIMIT_EXCEEDED,
        retry_after_ms,
        ack);
    if (!setAckAuthTag32(ack)) return false;
    storeAckCacheEntry(frame, *ack, now_ms);
    return true;
  }

  fillAckForParseResult(frame, ack);
  applyCommandSpecificAckPolicy(frame, ack);
  if (!setAckAuthTag32(ack)) return false;
  storeAckCacheEntry(frame, *ack, now_ms);
  return true;
}

bool openUdpSocket() {
  g_udp.stop();
  delay(10);

  // Control-plane alignment:
  // local bind now listens on CMD port (5007), while ACK destination remains 5008.
  if (g_udp.begin(OKUA_NODE_BIND_PORT)) {
    g_udpBegun = true;
    return true;
  }
  g_udpBegun = false;
  return false;
}

void connectWiFiBlocking() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);

  wifi_country_t co = {"CO", 1, 13, 0};
  esp_wifi_set_country(&co);
#if (WIFI_CHANNEL >= 1) && (WIFI_CHANNEL <= 13)
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);
#endif
  esp_wifi_set_ps(WIFI_PS_NONE);

  if (WiFi.status() == WL_CONNECTED) {
    if (!g_udpBegun) openUdpSocket();
    return;
  }

  WiFi.begin(WIFI_SSID, WIFI_PASS);

  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    if (okuaOtaShouldAbortWiFiConnect(millis())) {
      okuaOtaHandleWiFiConnectTimeout();
      return;
    }
    if (millis() - t0 >= WIFI_CONNECT_TIMEOUT_MS) {
      WiFi.disconnect(true, true);
      delay(WIFI_RETRY_DELAY_MS);
      WiFi.begin(WIFI_SSID, WIFI_PASS);
      t0 = millis();
    }
  }

  okuaOtaNotifyWiFiConnected(millis());
  g_udpBegun = false;
  openUdpSocket();
  g_wifiWasConnected = true;
}

void ensureLink() {
  bool nowConnected = (WiFi.status() == WL_CONNECTED);

  if (!nowConnected) {
    g_lastStateFlags |= STATF_WIFI_REASSOC;
    g_udp.stop();
    g_udpBegun = false;
    connectWiFiBlocking();
    return;
  }

  if (!g_udpBegun) {
    openUdpSocket();
  }

  g_wifiWasConnected = true;
}

bool sendUdpRawTo(const IPAddress& dst_ip, const uint8_t* data, size_t len, uint16_t port) {
  ensureLink();
  if (WiFi.status() != WL_CONNECTED || !g_udpBegun) return false;
  if (!g_udp.beginPacket(dst_ip, port)) return false;
  size_t written = g_udp.write(data, len);
  int ok = g_udp.endPacket();
  return (written == len && ok == 1);
}

bool sendUdpRaw(const uint8_t* data, size_t len, uint16_t port) {
  return sendUdpRawTo(PC_IP, data, len, port);
}

bool sendOkuaAckTo(const IPAddress& dst_ip, const OkuaAckPacket& ack) {
  if (!okuaIsAckPacketSizeValid(sizeof(OkuaAckPacket))) return false;
  return sendUdpRawTo(dst_ip, (const uint8_t*)&ack, sizeof(ack), OKUA_ACK_PORT);
}

bool sendOkuaStat(uint8_t state_flags);

void scheduleSoftReboot() {
  if (g_rebootPending) return;
  g_rebootPending = true;
  g_rebootAtMs = millis() + CONTROL_REBOOT_DELAY_MS;
}

void servicePendingControlActions() {
  if (okuaOtaConsumePendingReboot()) {
    sendOkuaStat(g_lastStateFlags);
    scheduleSoftReboot();
  }
  if (!g_rebootPending) return;
  if (!millisReached(millis(), g_rebootAtMs)) return;
  g_rebootPending = false;
  ESP.restart();
}

static inline bool shouldDispatchAcceptedCommand(
    const ParsedCmdFrame& frame,
    const OkuaAckPacket& ack) {
  if (ack.ack_stage != OKUA_ACK_STAGE_ACCEPTED) return false;
  if (ack.status_code != OKUA_STATUS_OK) return false;
  if ((ack.ack_flags & ACK_FLAG_DUPLICATE) != 0) return false;
  return okuaIsImplementedCmdId(frame.packet.cmd_id);
}

void dispatchAcceptedCommandMinimal(const ParsedCmdFrame& frame) {
  switch (frame.packet.cmd_id) {
    case OKUA_CMD_PING:
      // PING is a control-plane roundtrip only; ACK already confirms health.
      return;

    case OKUA_CMD_REQUEST_STAT_NOW:
      // Force immediate STAT outside normal cadence for accepted fresh commands.
      sendOkuaStat(g_lastStateFlags);
      return;

    case OKUA_CMD_REBOOT_SOFT:
      // ACK is emitted before dispatch, reboot is deferred in loop.
      scheduleSoftReboot();
      return;

    case OKUA_CMD_SET_THROTTLE:
      // Runtime-only (RAM): adjusts plant note-on throttle.
      // Lower percentage -> larger inter-event spacing.
      g_plantThrottlePercent = frame.packet.arg0;
      g_plantThrottleMs = setThrottlePercentToMs(frame.packet.arg0);
      Serial.printf(
          "[F3] SET_THROTTLE accepted: percent=%u cadence_ms=%lu\r\n",
          (unsigned)g_plantThrottlePercent,
          (unsigned long)g_plantThrottleMs);
      return;

    case OKUA_CMD_SET_STAT_RATE:
      // Runtime-only (RAM) policy: applies to periodic STAT cadence and
      // naturally resets to compile-time default after reboot.
      g_statIntervalMs = frame.packet.arg0;
      return;

    case OKUA_CMD_OTA_CHECK_NOW: {
      const uint32_t rollout_token =
          ((uint32_t)frame.packet.arg1 << 16) | (uint32_t)frame.packet.arg0;
      if (okuaOtaQueueCheck(rollout_token)) {
        Serial.printf("[F3] OTA_CHECK_NOW accepted: rollout_token=0x%08lx\r\n", (unsigned long)rollout_token);
        sendOkuaStat(g_lastStateFlags);
      }
      return;
    }

    default:
      return;
  }
}

// Control-plane ingress:
// parse + security + ACK + minimal command dispatch
// (PING/REQUEST_STAT_NOW/REBOOT_SOFT/SET_THROTTLE/SET_STAT_RATE).
void serviceControlPlaneIngress() {
  ParsedCmdFrame frame;
  CmdParseResult result = parseIncomingCmdFrame(&frame);
  if (result == CMD_PARSE_NONE) return;

  g_lastParsedCmdFrame = frame;
  g_lastCmdParseResult = result;

  if (!shouldEmitAckForParseResult(result)) return;

  OkuaAckPacket ack = {};
  if (!buildAckForFrameWithSecurity(frame, &ack)) return;

  // ACK destination for F3 is source_ip + fixed ACK port (not source port).
  sendOkuaAckTo(frame.src_ip, ack);

  if (shouldDispatchAcceptedCommand(frame, ack)) {
    dispatchAcceptedCommandMinimal(frame);
  }
}


/*============================================================================================
  ZONA 11 — ENVIO OKUA
============================================================================================*/

bool sendOkuaEvt(uint8_t midi_bus, uint8_t midi_ch0, uint8_t note, uint8_t vel, uint8_t flags) {
  OkuaEvtPacket p = {};
  p.hdr.magic   = OKUA_MAGIC;
  p.hdr.ver     = OKUA_PROTOCOL_VERSION;
  p.hdr.type    = OKUA_TYPE_EVT;
  p.hdr.node_id = NODE_ID;
  p.hdr.seq     = g_seqEvt++;

  p.midi_bus    = midi_bus;
  p.midi_ch     = clamp_u8(midi_ch0, 0, 15);
  p.note        = clamp_u8(note, 0, 127);
  p.vel         = clamp_u8(vel, 0, 127);
  p.ts_ms       = millis();
  p.rssi_dbm    = currentRssiDbm();
  p.flags       = flags;
  p.rsv[0]      = 0;
  p.rsv[1]      = 0;

  bool ok = sendUdpRaw((const uint8_t*)&p, sizeof(p), OKUA_EVT_PORT);
  if (ok) g_evtCountSinceLastStat++;
  return ok;
}

bool sendOkuaStat(uint8_t state_flags) {
  uint32_t nowMs = millis();
  uint32_t elapsedMs = nowMs - g_lastEvtCounterResetMs;
  if (elapsedMs == 0) elapsedMs = 1;

  // pps_x10 = eventos/segundo * 10
  uint32_t pps_x10_u32 = (g_evtCountSinceLastStat * 10000UL) / elapsedMs;
  if (pps_x10_u32 > 65535UL) pps_x10_u32 = 65535UL;

  OkuaStatPacket p = {};
  p.hdr.magic      = OKUA_MAGIC;
  p.hdr.ver        = OKUA_PROTOCOL_VERSION;
  p.hdr.type       = OKUA_TYPE_STAT;
  p.hdr.node_id    = NODE_ID;
  p.hdr.seq        = g_seqStat++;

  p.uptime_s       = millis() / 1000UL;
  p.rssi_dbm       = currentRssiDbm();
  // Low nibble keeps legacy state flags; high nibble exposes a boot marker
  // (mod-16) that changes on every reboot and helps app-side confirmation.
  p.state_flags    = (uint8_t)((state_flags & 0x0F) | ((g_bootMarker4 & 0x0F) << 4));
  p.pps_x10        = (uint16_t)pps_x10_u32;
  p.vbat_mv        = 0;
  p.free_heap      = ESP.getFreeHeap();
  p.fw_major       = FW_MAJOR;
  p.fw_minor       = FW_MINOR;
  p.reset_reason   = (uint8_t)esp_reset_reason();
  const OkuaOtaTelemetry ota = okuaOtaGetTelemetry();
  p.rsv[0] = ota.state_code;
  p.rsv[1] = ota.error_code;
  p.rsv[2] = ota.flags;

  bool ok = sendUdpRaw((const uint8_t*)&p, sizeof(p), OKUA_STAT_PORT);
  if (ok) {
    g_lastStatMs = nowMs;
    g_lastEvtCounterResetMs = nowMs;
    g_evtCountSinceLastStat = 0;
    okuaOtaNotifyStatSent();
  }
  return ok;
}


/*============================================================================================
  ZONA 12 — PERFIL PLANTA (CAMPO)
============================================================================================*/

enum PlantState {
  PLANT_IDLE,
  PLANT_ACTIVE,
  PLANT_DECAY
};

PlantState g_plantState = PLANT_IDLE;

bool  g_plantCalDone = false;
float g_plantVMin = 3.3f;
float g_plantVMax = 0.0f;
float g_plantBaselineV = 1.10f;
float g_plantSmoothV = 0.0f;
float g_plantLastRawV = 0.0f;
uint8_t g_plantCurrentNote = 60;
bool g_plantNoteActive = false;
uint8_t g_plantLastPlayedNote = 60;
bool g_plantLastOutputRequested = false;
bool g_plantLastOutputNoteOn = false;
bool g_plantLastOutputOk = false;
uint8_t g_plantLastOutputFailures = 0;
uint32_t g_plantLastOutputMs = 0;

uint32_t g_plantLastAnyActivity = 0;
uint32_t g_plantLastSentMs = 0;
uint32_t g_plantDebugLastMs = 0;
uint32_t g_plantDiagLastMs = 0;
uint32_t g_plantAdcScanLastMs = 0;

const char* plantStateLabel(uint8_t state) {
  switch (state) {
    case PLANT_IDLE: return "idle";
    case PLANT_ACTIVE: return "active";
    case PLANT_DECAY: return "decay";
    default: return "unknown";
  }
}

uint8_t plantMapNote(float v) {
  float den = (g_plantVMax - g_plantVMin);
  if (den < 0.05f) den = 0.05f;
  float f = (v - g_plantVMin) / den;
  f = clampf(f, 0.0f, 1.0f);
  return (uint8_t)(PLANT_NOTE_LOW + f * (PLANT_NOTE_HIGH - PLANT_NOTE_LOW) + 0.5f);
}

uint8_t plantMapVel(float activity) {
  activity = clampf(activity, 0.0f, 1.0f);
  return (uint8_t)(30 + activity * (127 - 30) + 0.5f);
}

uint8_t plantLimitJump(uint8_t n) {
  int delta = (int)n - (int)g_plantCurrentNote;
  if (delta > PLANT_MAX_JUMP_ST) return (uint8_t)(g_plantCurrentNote + PLANT_MAX_JUMP_ST);
  if (delta < -PLANT_MAX_JUMP_ST) return (uint8_t)(g_plantCurrentNote - PLANT_MAX_JUMP_ST);
  return n;
}

bool plantSendNoteOn(uint8_t note, uint8_t vel, bool force = false) {
  uint32_t now = millis();
  const uint32_t throttle_ms = (g_plantThrottleMs > 0) ? g_plantThrottleMs : (uint32_t)PLANT_THROTTLE_MS;
  if (!force && (now - g_plantLastSentMs < throttle_ms)) {
#if PLANT_DEBUG_SERIAL
    Serial.printf("[PLANT_EVT] note_on throttled note=%u vel=%u wait_ms=%lu throttle_ms=%lu\n",
                  note,
                  vel,
                  (unsigned long)(now - g_plantLastSentMs),
                  (unsigned long)throttle_ms);
#endif
    return false;
  }
  bool ok = sendOkuaEvt(PLANT_MIDI_BUS, toMidiCh0(PLANT_MIDI_CHANNEL_1B), note, vel, PLANT_EVT_FLAGS);
  g_plantLastOutputRequested = true;
  g_plantLastOutputNoteOn = true;
  g_plantLastOutputOk = ok;
  g_plantLastOutputFailures = ok ? 0 : 1;
  g_plantLastOutputMs = now;
  if (ok) {
    g_plantLastSentMs = now;
    g_plantNoteActive = true;
    g_plantLastPlayedNote = note;
    ledShowNote(note);
  }
#if PLANT_DEBUG_SERIAL
  if (!ok) {
    Serial.printf("[PLANT_EVT] note_on failed note=%u vel=%u flags=0x%02X\n",
                  note, vel, (unsigned)PLANT_EVT_FLAGS);
  }
#endif
  return ok;
}

bool plantSendNoteOff(uint8_t note) {
  uint32_t now = millis();
  bool ok = sendOkuaEvt(PLANT_MIDI_BUS, toMidiCh0(PLANT_MIDI_CHANNEL_1B), note, 0, PLANT_EVT_FLAGS);
  g_plantLastOutputRequested = true;
  g_plantLastOutputNoteOn = false;
  g_plantLastOutputOk = ok;
  g_plantLastOutputFailures = ok ? 0 : 1;
  g_plantLastOutputMs = now;
  if (ok) {
    g_plantNoteActive = false;
    ledOff();
  }
#if PLANT_DEBUG_SERIAL
  if (!ok) {
    Serial.printf("[PLANT_EVT] note_off failed note=%u flags=0x%02X\n",
                  note, (unsigned)PLANT_EVT_FLAGS);
  }
#endif
  return ok;
}

#if PLANT_DEBUG_UDP
void plantSendDiagUdp(unsigned long now, float vRaw, float dv, float slope, bool alive, bool force_now = false) {
  if (!force_now && (now - g_plantDiagLastMs) < (unsigned long)PLANT_DEBUG_UDP_INTERVAL_MS) return;
  g_plantDiagLastMs = now;

  if (WiFi.status() != WL_CONNECTED || !g_udpBegun) return;

  float rawDelta = vRaw - g_plantBaselineV;
  float absRawDelta = fabsf(rawDelta);
  float rawRail = (vRaw <= 0.050f || vRaw >= 3.250f) ? 1.0f : 0.0f;
  const char* phase = g_plantCalDone ? "track" : "cal";
  const char* state = g_plantNoteActive ? "contact" : "idle";
  const char* fsm = plantStateLabel((uint8_t)g_plantState);
  const char* entryReason = !g_plantCalDone ? "cal" : (alive ? "alive" : "quiet");
  const char* exitReason = g_plantNoteActive ? "note_on" : "quiet";
  const char* blockReason = !g_plantCalDone ? "cal" : (alive ? "none" : "noise_floor");
  const unsigned long contact_age_ms = g_plantNoteActive ? (now - g_plantLastSentMs) : 0UL;
  const unsigned long release_age_ms = (!g_plantNoteActive && g_plantLastOutputMs > 0) ? (now - g_plantLastOutputMs) : 0UL;
  const unsigned long output_age_ms = (g_plantLastOutputMs > 0) ? (now - g_plantLastOutputMs) : 0UL;
  const unsigned long idle_stable_ms = (!g_plantNoteActive && !alive) ? (now - g_plantLastAnyActivity) : 0UL;
  const unsigned long fsm_age_ms = (g_plantLastAnyActivity > 0) ? (now - g_plantLastAnyActivity) : 0UL;

  char line[1536];
  int written = snprintf(
      line,
      sizeof(line),
      "FRUITDIAG node=%s id=%u fw=%s variant=%u mode=%s phase=%s state=%s fsm=%s entry_reason=%s exit_reason=%s block_reason=%s t_ms=%lu raw=%.4f filt=%.4f base=%.4f prev=%.4f dv=%.4f raw_delta=%.4f slope=%.4f sigma=%.4f th_up=%.4f th_down=%.4f cand=%d ref=%d exit=%d raw_rail=%d quiet_idle=%d entry_armed=%d entry_relaxed=%d entry_rescue=%d touch_sign=%d pending_sign=%d cal_fast=%d cal_refine=%d vmin=%.4f vmax=%.4f hold_up_ms=%lu hold_down_ms=%lu recovery_ms=%lu energy_age_ms=%lu contact_age_ms=%lu release_age_ms=%lu idle_stable_ms=%lu fsm_age_ms=%lu poss_touch_ms=%lu poss_release_ms=%lu peak_dv=%.4f peak_raw=%.4f out_req=%d out_on=%d out_ok=%d out_fail=%u out_age_ms=%lu alive=%d note=%u plant_active=%d plant_state=%s plant_delta=%.4f plant_abs_delta=%.4f selected_pin=%u adc32=%.4f adc33=%.4f adc34=%.4f adc35=%.4f adc36=%.4f adc39=%.4f",
      NODE_LABEL,
      (unsigned)NODE_ID,
      OKUA_FW_VERSION_STR,
      (unsigned)ACTIVE_FRUIT_VARIANT,
      "plant",
      phase,
      state,
      fsm,
      entryReason,
      exitReason,
      blockReason,
      now,
      vRaw,
      g_plantSmoothV,
      g_plantBaselineV,
      g_plantLastRawV,
      dv,
      rawDelta,
      slope,
      0.0f,
      (float)PLANT_NOISE_FLOOR,
      (float)(PLANT_NOISE_FLOOR * 0.75f),
      alive ? 1 : 0,
      g_plantCalDone ? 1 : 0,
      g_plantNoteActive ? 1 : 0,
      rawRail ? 1 : 0,
      (!g_plantNoteActive && !alive) ? 1 : 0,
      g_plantCalDone ? 1 : 0,
      0,
      0,
      1,
      1,
      g_plantCalDone ? 1 : 0,
      g_plantCalDone ? 1 : 0,
      g_plantVMin,
      g_plantVMax,
      0UL,
      0UL,
      0UL,
      0UL,
      contact_age_ms,
      release_age_ms,
      idle_stable_ms,
      fsm_age_ms,
      0UL,
      0UL,
      abs(dv),
      absRawDelta,
      g_plantLastOutputRequested ? 1 : 0,
      g_plantLastOutputNoteOn ? 1 : 0,
      g_plantLastOutputOk ? 1 : 0,
      (unsigned)g_plantLastOutputFailures,
      output_age_ms,
      alive ? 1 : 0,
      (unsigned)g_plantCurrentNote,
      g_plantNoteActive ? 1 : 0,
      fsm,
      rawDelta,
      absRawDelta,
      (unsigned)PIN_SIGNAL,
      readVPin(32),
      readVPin(33),
      readVPin(34),
      readVPin(35),
      readVPin(36),
      readVPin(39));

  if (written <= 0) return;
  if (written >= (int)sizeof(line)) {
    line[sizeof(line) - 1] = '\0';
  }

  sendUdpRawTo(DIAG_PC_IP, (const uint8_t*)line, strlen(line), PLANT_DEBUG_UDP_PORT);
}
#endif

#if PLANT_DEBUG_ADC_SCAN_UDP
void plantSendAdcScanUdp(unsigned long now) {
  if ((now - g_plantAdcScanLastMs) < (unsigned long)PLANT_DEBUG_ADC_SCAN_INTERVAL_MS) return;
  g_plantAdcScanLastMs = now;

  if (WiFi.status() != WL_CONNECTED || !g_udpBegun) return;

  char line[512];
  int written = snprintf(
      line,
      sizeof(line),
      "FRUITDIAG node=%s id=%u fw=%s variant=%u mode=plant_scan phase=scan state=scan fsm=scan t_ms=%lu selected_pin=%u adc32=%.4f adc33=%.4f adc34=%.4f adc35=%.4f adc36=%.4f adc39=%.4f",
      NODE_LABEL,
      (unsigned)NODE_ID,
      OKUA_FW_VERSION_STR,
      (unsigned)ACTIVE_FRUIT_VARIANT,
      now,
      (unsigned)PIN_SIGNAL,
      readVPin(32),
      readVPin(33),
      readVPin(34),
      readVPin(35),
      readVPin(36),
      readVPin(39));

  if (written <= 0) return;
  if (written >= (int)sizeof(line)) {
    line[sizeof(line) - 1] = '\0';
  }

  sendUdpRawTo(DIAG_PC_IP, (const uint8_t*)line, strlen(line), PLANT_DEBUG_UDP_PORT);
}
#endif

void servicePlantField() {
  float vRaw = readVmed3();
  float dv = fabsf(vRaw - g_plantLastRawV);
  float slope = dv;

  if (!g_plantCalDone) {
    g_plantVMin = min(g_plantVMin, vRaw);
    g_plantVMax = max(g_plantVMax, vRaw);

    if (millis() > PLANT_AUTOCAL_MS) {
      if ((g_plantVMax - g_plantVMin) < 0.4f) {
        g_plantVMin -= 0.2f;
        g_plantVMax += 0.2f;
      }
      g_plantCalDone = true;
    }
    g_lastStateFlags |= STATF_CALIBRATING;
#if PLANT_DEBUG_UDP
    plantSendDiagUdp(millis(), vRaw, dv, slope, false, true);
#endif
    return;
  } else {
    g_lastStateFlags &= (uint8_t)~STATF_CALIBRATING;
  }

  g_plantBaselineV += PLANT_BASE_A * (vRaw - g_plantBaselineV);
  g_plantSmoothV   += PLANT_SMOOTH_A * (vRaw - g_plantSmoothV);

  g_plantLastRawV = vRaw;
  bool alive = dv > PLANT_NOISE_FLOOR;

  switch (g_plantState) {
      case PLANT_IDLE:
        if (alive) {
          g_plantState = PLANT_ACTIVE;
          g_plantLastAnyActivity = millis();
          g_plantCurrentNote = plantMapNote(g_plantSmoothV);
          plantSendNoteOn(g_plantCurrentNote, plantMapVel(dv * PLANT_TOUCH_GAIN), true);
        }
        break;

      case PLANT_ACTIVE:
        if (alive) {
          g_plantLastAnyActivity = millis();
          uint8_t nextNote = plantLimitJump(plantMapNote(g_plantSmoothV));
          const uint32_t throttle_ms = (g_plantThrottleMs > 0) ? g_plantThrottleMs : (uint32_t)PLANT_THROTTLE_MS;
          const bool canAdvanceNote = (millis() - g_plantLastSentMs >= throttle_ms);
          if (nextNote != g_plantCurrentNote && canAdvanceNote) {
            if (g_plantNoteActive) plantSendNoteOff(g_plantCurrentNote);
            g_plantCurrentNote = nextNote;
            plantSendNoteOn(g_plantCurrentNote, plantMapVel(dv * PLANT_TOUCH_GAIN), false);
          }
        } else if (millis() - g_plantLastAnyActivity > 120) {
        g_plantState = PLANT_DECAY;
      }
      break;

    case PLANT_DECAY:
      if (alive) {
        g_plantState = PLANT_ACTIVE;
        g_plantLastAnyActivity = millis();
      } else if (millis() - g_plantLastAnyActivity > 400) {
        if (g_plantNoteActive) {
          plantSendNoteOff(g_plantCurrentNote);
        }
        g_plantState = PLANT_IDLE;
      }
      break;
  }

#if PLANT_DEBUG_SERIAL
  if (millis() - g_plantDebugLastMs >= 200UL) {
    g_plantDebugLastMs = millis();
    Serial.printf(
      "[PLANT] v=%.4f base=%.4f smooth=%.4f prev=%.4f dv=%.4f min=%.4f max=%.4f cal=%d state=%d alive=%d note=%u active=%d\n",
      vRaw,
      g_plantBaselineV,
      g_plantSmoothV,
      g_plantLastRawV,
      dv,
      g_plantVMin,
      g_plantVMax,
      (int)g_plantCalDone,
      (int)g_plantState,
      (int)alive,
      (unsigned)g_plantCurrentNote,
      (int)g_plantNoteActive);
  }
#endif
#if PLANT_DEBUG_UDP
  plantSendDiagUdp(millis(), vRaw, dv, slope, alive, false);
#endif
}


/*============================================================================================
  ZONA 13 — PERFIL FRUTA (CAMPO)
============================================================================================*/

struct FruitDetectParams {
  float v_rel_min;
  float rel_up;
  float rel_down_f;
  float abs_min_up;
  float abs_min_down;
  float k_sigma_up;
  float k_sigma_down;
  float abs_strong_up;
  float slope_min_strong;
  float slope_release;
  unsigned long on_hold_ms;
  unsigned long off_hold_ms;
  unsigned long refract_ms;
  unsigned long noenergy_ms;
  unsigned long contact_max_ms;
  float energy_frac;
};

const FruitDetectParams FRUIT_V1 = {
  0.05f, 0.18f, 0.65f,
  0.020f, 0.010f,
  6.0f, 3.5f,
  0.080f,
  0.25f, 0.22f,
  35, 90, 120,
  1200, 15000,
  0.35f
};

const FruitDetectParams FRUIT_V2 = {
  0.05f, 0.20f, 0.60f,
  0.030f, 0.015f,
  5.0f, 3.0f,
  0.070f,
  0.12f, 0.25f,
  30, 80, 120,
  800, 12000,
  0.35f
};

const FruitDetectParams FRUIT_V3 = {
  0.06f, 0.22f, 0.68f,
  0.040f, 0.020f,
  5.5f, 3.0f,
  0.110f,
  0.20f, 0.24f,
  80, 140, 180,
  1800, 15000,
  0.25f
};

const FruitDetectParams FRUIT_V4 = {
  0.05f, 0.11f, 0.60f,
  0.018f, 0.010f,
  0.70f, 0.45f,
  0.035f,
  0.08f, 0.16f,
  18, 70, 120,
  1500, 10000,
  0.20f
};

const FruitDetectParams FRUIT_V5 = {
  0.06f, 0.13f, 0.62f,
  0.020f, 0.010f,
  1.80f, 1.10f,
  0.120f,
  0.22f, 0.18f,
  90, 180, 200,
  2200, 12000,
  0.22f
};

const FruitDetectParams FRUIT_V6 = {
  0.05f, 0.14f, 0.60f,
  0.018f, 0.009f,
  1.40f, 0.90f,
  0.050f,
  0.12f, 0.15f,
  140, 240, 220,
  2000, 14000,
  0.24f
};

const FruitDetectParams FRUIT_V7 = {
  0.05f, 0.13f, 0.60f,
  0.016f, 0.008f,
  1.20f, 0.85f,
  0.045f,
  0.11f, 0.14f,
  120, 240, 250,
  1800, 15000,
  0.18f
};

const FruitDetectParams FRUIT_V8 = {
  0.05f, 0.12f, 0.60f,
  0.016f, 0.008f,
  1.10f, 0.75f,
  0.040f,
  0.10f, 0.13f,
  110, 200, 220,
  1700, 14000,
  0.20f
};

const FruitDetectParams FRUIT_V9 = {
  0.05f, 0.12f, 0.60f,
  0.016f, 0.008f,
  1.10f, 0.75f,
  0.040f,
  0.10f, 0.13f,
  130, 260, 260,
  1800, 16000,
  0.20f
};

const FruitDetectParams FRUIT_V10 = {
  0.05f, 0.12f, 0.60f,
  0.016f, 0.008f,
  1.10f, 0.75f,
  0.040f,
  0.10f, 0.13f,
  130, 240, 240,
  1800, 16000,
  0.20f
};

const FruitDetectParams FRUIT_V11 = {
    0.05f, 0.12f, 0.60f,
    0.016f, 0.008f,
    1.10f, 0.75f,
    0.040f,
    0.10f, 0.13f,
    110, 220, 240,
    1600, 16000,
    0.20f
  };

  const FruitDetectParams FRUIT_V12 = {
    0.05f, 0.12f, 0.60f,
    0.016f, 0.008f,
    1.10f, 0.75f,
    0.040f,
    0.10f, 0.13f,
    110, 220, 240,
    1600, 16000,
    0.20f
  };

  const FruitDetectParams FRUIT_V13 = {
    0.05f, 0.12f, 0.60f,
    0.016f, 0.008f,
    1.10f, 0.75f,
    0.040f,
    0.10f, 0.13f,
    110, 220, 240,
    1600, 9000,
    0.20f
  };

  const FruitDetectParams FRUIT_V14 = {
    0.05f, 0.12f, 0.60f,
    0.016f, 0.008f,
    1.10f, 0.75f,
    0.040f,
    0.10f, 0.13f,
    110, 120, 240,
    1600, 12000,
    0.20f
  };

  const FruitDetectParams FRUIT_V15 = {
    0.05f, 0.12f, 0.60f,
    0.016f, 0.008f,
    1.05f, 0.72f,
    0.040f,
    0.08f, 0.12f,
    70, 160, 350,
    1400, FRUIT_FSM_TIMEOUT_MS,
    0.18f
  };

const FruitDetectParams& FD =
  (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V1) ? FRUIT_V1 :
  (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V3) ? FRUIT_V3 :
  (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V4) ? FRUIT_V4 :
  (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V5) ? FRUIT_V5 :
  (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V6) ? FRUIT_V6 :
  (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V7) ? FRUIT_V7 :
    (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V8) ? FRUIT_V8 :
    (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V9) ? FRUIT_V9 :
    (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V10) ? FRUIT_V10 :
    (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V11) ? FRUIT_V11 :
    (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V12) ? FRUIT_V12 :
    (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V13) ? FRUIT_V13 :
    (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V14) ? FRUIT_V14 :
    (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V15) ? FRUIT_V15 :
    FRUIT_V2;

#define FRUIT_FSM_IDLE              0
#define FRUIT_FSM_POSSIBLE_TOUCH    1
#define FRUIT_FSM_TOUCH_ACTIVE      2
#define FRUIT_FSM_POSSIBLE_RELEASE  3
#define FRUIT_FSM_LOCKOUT           4

bool  g_fruitCalFastDone = false;
bool  g_fruitCalRefineDone = false;
unsigned long g_fruitBootMs = 0;
unsigned long g_fruitRefineStartMs = 0;

float g_fruitBaselineV = 0.0f;
float g_fruitFilteredV = 0.0f;
float g_fruitPrevV = 0.0f;
float g_fruitVarDv = 0.0f;
float g_fruitSigma = 0.0f;
float g_fruitVMin = 3.3f;
float g_fruitVMax = 0.0f;

bool  g_fruitContactActive = false;
int8_t g_fruitTouchSign = +1;
int8_t g_fruitPendingSign = +1;
unsigned long g_fruitContactStartMs = 0;
unsigned long g_fruitLastReleaseMs = 0;
unsigned long g_fruitUpHoldStartMs = 0;
unsigned long g_fruitDownHoldStartMs = 0;
unsigned long g_fruitLastEnergyOkMs = 0;
unsigned long g_fruitRecoveryUntilMs = 0;
unsigned long g_fruitLastKeepaliveMs = 0;
unsigned long g_fruitReleaseCleanupUntilMs = 0;
unsigned long g_fruitReleaseCleanupLastMs = 0;
unsigned long g_fruitIdleStableStartMs = 0;
unsigned long g_fruitForceRearmUntilMs = 0;
uint8_t g_fruitFsm = FRUIT_FSM_IDLE;
unsigned long g_fruitFsmStateStartMs = 0;
unsigned long g_fruitPossibleTouchStartMs = 0;
unsigned long g_fruitPossibleReleaseStartMs = 0;
float g_fruitContactPeakAbsDv = 0.0f;
float g_fruitContactPeakRawDelta = 0.0f;
const char* g_fruitLastEntryReason = "none";
const char* g_fruitLastExitReason = "none";
bool g_fruitDiagRawRail = false;
bool g_fruitDiagQuietIdle = false;
bool g_fruitDiagEntryArmed = false;
bool g_fruitDiagEntryRelaxed = false;
bool g_fruitDiagEntryRescue = false;
float g_fruitDiagRawDelta = 0.0f;
const char* g_fruitDiagBlockReason = "none";
bool g_fruitLastOutputRequested = false;
bool g_fruitLastOutputNoteOn = false;
bool g_fruitLastOutputOk = false;
uint8_t g_fruitLastOutputFailures = 0;
unsigned long g_fruitLastOutputMs = 0;

#define FRUIT_HARMONY_ENABLED ((FRUIT_ROUTE_PRESET == FRUIT_ROUTE_PRESET_EB_FANOUT) || (FRUIT_ROUTE_PRESET == FRUIT_ROUTE_PRESET_EC_FANOUT))

#if FRUIT_ROUTE_PRESET == FRUIT_ROUTE_PRESET_EB_FANOUT
static const uint8_t FRUIT_HARMONY_NOTES[] = {
  45, 49, 52, 54, 57, 61, 64, 66, 69, 73, 76, 78
};
#elif FRUIT_ROUTE_PRESET == FRUIT_ROUTE_PRESET_EC_FANOUT
static const uint8_t FRUIT_HARMONY_NOTES[] = {
  49, 52, 54, 56, 59, 61, 64, 66, 68, 71, 73, 76, 78
};
#endif

#if FRUIT_HARMONY_ENABLED
static const uint8_t FRUIT_HARMONY_STEPS[] = {2, 3, 5, 6, 8, 10};
static uint8_t g_fruitHarmonyIndex = 0;
static uint8_t g_fruitHarmonyNote = FRUIT_ROUTE_NOTE;
static uint8_t g_fruitHarmonyRecent[4] = {0xFF, 0xFF, 0xFF, 0xFF};
static uint32_t g_fruitHarmonyRng = 0;
static bool g_fruitHarmonySeeded = false;

static uint32_t fruitHarmonyRand() {
  if (!g_fruitHarmonySeeded) {
    g_fruitHarmonyRng = esp_random() ^ ((uint32_t)millis() << 16) ^ (uint32_t)analogRead(PIN_SIGNAL);
    if (g_fruitHarmonyRng == 0) g_fruitHarmonyRng = 0x6D2B79F5UL;
    g_fruitHarmonySeeded = true;
  }
  g_fruitHarmonyRng ^= (g_fruitHarmonyRng << 13);
  g_fruitHarmonyRng ^= (g_fruitHarmonyRng >> 17);
  g_fruitHarmonyRng ^= (g_fruitHarmonyRng << 5);
  return g_fruitHarmonyRng;
}

static bool fruitHarmonyRecentlyUsed(uint8_t index) {
  for (uint8_t i = 0; i < (uint8_t)(sizeof(g_fruitHarmonyRecent) / sizeof(g_fruitHarmonyRecent[0])); ++i) {
    if (g_fruitHarmonyRecent[i] == index) return true;
  }
  return false;
}

static void fruitHarmonyRemember(uint8_t index) {
  for (int i = (int)(sizeof(g_fruitHarmonyRecent) / sizeof(g_fruitHarmonyRecent[0])) - 1; i > 0; --i) {
    g_fruitHarmonyRecent[i] = g_fruitHarmonyRecent[i - 1];
  }
  g_fruitHarmonyRecent[0] = index;
}

static uint8_t fruitNextHarmonyNote() {
  const uint8_t deckCount = (uint8_t)(sizeof(FRUIT_HARMONY_NOTES) / sizeof(FRUIT_HARMONY_NOTES[0]));
  const uint8_t stepCount = (uint8_t)(sizeof(FRUIT_HARMONY_STEPS) / sizeof(FRUIT_HARMONY_STEPS[0]));
  if (deckCount == 0) {
    g_fruitHarmonyNote = FRUIT_ROUTE_NOTE;
    return g_fruitHarmonyNote;
  }

  if (g_fruitHarmonyRecent[0] == 0xFF) {
    g_fruitHarmonyIndex = (uint8_t)(fruitHarmonyRand() % deckCount);
  } else if (stepCount > 0) {
    uint8_t candidate = g_fruitHarmonyIndex;
    for (uint8_t attempt = 0; attempt < 12; ++attempt) {
      uint32_t r = fruitHarmonyRand();
      uint8_t step = FRUIT_HARMONY_STEPS[r % stepCount];
      int direction = (r & 0x10UL) ? +1 : -1;
      int next = (int)g_fruitHarmonyIndex + (direction * (int)step);
      while (next < 0) next += deckCount;
      candidate = (uint8_t)(next % deckCount);
      if (!fruitHarmonyRecentlyUsed(candidate)) break;
    }
    g_fruitHarmonyIndex = candidate;
  }

  fruitHarmonyRemember(g_fruitHarmonyIndex);
  g_fruitHarmonyNote = FRUIT_HARMONY_NOTES[g_fruitHarmonyIndex];
  return g_fruitHarmonyNote;
}

static uint8_t fruitCurrentHarmonyNote() {
  return (g_fruitHarmonyNote > 0) ? g_fruitHarmonyNote : FRUIT_ROUTE_NOTE;
}
#else
static inline uint8_t fruitNextHarmonyNote() {
  return FRUIT_ROUTE_NOTE;
}

static inline uint8_t fruitCurrentHarmonyNote() {
  return FRUIT_ROUTE_NOTE;
}
#endif
#if FRUIT_DEBUG_SERIAL
unsigned long g_fruitDebugLastMs = 0;
#endif
#if FRUIT_DEBUG_UDP
unsigned long g_fruitDebugUdpLastMs = 0;
#endif

void fruitSendAll(bool noteOn, uint8_t vel, uint8_t flags) {
  bool allOk = (FRUIT_ROUTE_COUNT > 0);
  uint8_t failures = 0;
  uint8_t note = FRUIT_ROUTE_NOTE;

  if (FRUIT_HARMONY_ENABLED) {
    if (noteOn) {
      if (!g_fruitLastOutputNoteOn) {
        note = fruitNextHarmonyNote();
      } else {
        note = fruitCurrentHarmonyNote();
      }
    } else {
      note = fruitCurrentHarmonyNote();
    }
  }

  for (uint8_t i = 0; i < FRUIT_ROUTE_COUNT; ++i) {
    const MidiRoute& r = FRUIT_ROUTES[i];
    bool ok = sendOkuaEvt(r.midi_bus, toMidiCh0(r.midi_channel_1b), note, noteOn ? vel : 0, flags);
    if (!ok) {
      allOk = false;
      failures++;
    }
  }

  g_fruitLastOutputRequested = true;
  g_fruitLastOutputNoteOn = noteOn;
  g_fruitLastOutputOk = allOk;
  g_fruitLastOutputFailures = failures;
  g_fruitLastOutputMs = millis();

  if (noteOn && FRUIT_ROUTE_COUNT > 0) {
    ledShowNote(note);
  } else {
    ledOff();
  }
}

#if FRUIT_DEBUG_UDP
const char* fruitFsmName(uint8_t state) {
  switch (state) {
    case FRUIT_FSM_IDLE: return "idle";
    case FRUIT_FSM_POSSIBLE_TOUCH: return "possible_touch";
    case FRUIT_FSM_TOUCH_ACTIVE: return "touch_active";
    case FRUIT_FSM_POSSIBLE_RELEASE: return "possible_release";
    case FRUIT_FSM_LOCKOUT: return "lockout";
    default: return "unknown";
  }
}

void fruitSendDiagUdp(
    unsigned long now,
    float vRaw,
    float dv_proj,
    float slope_proj,
    float th_up,
    float th_down,
    bool enterCand,
    bool refractory,
    bool exitNow,
    bool force_now = false) {
  if (!force_now && (now - g_fruitDebugUdpLastMs) < FRUIT_DEBUG_UDP_INTERVAL_MS) return;
  g_fruitDebugUdpLastMs = now;

  if (WiFi.status() != WL_CONNECTED || !g_udpBegun) return;

  const unsigned long contact_age_ms = g_fruitContactActive ? (now - g_fruitContactStartMs) : 0UL;
  const unsigned long release_age_ms = (g_fruitLastReleaseMs > 0) ? (now - g_fruitLastReleaseMs) : 0UL;
  const unsigned long energy_age_ms = (g_fruitLastEnergyOkMs > 0) ? (now - g_fruitLastEnergyOkMs) : 0UL;
  const unsigned long up_hold_ms = (g_fruitUpHoldStartMs > 0) ? (now - g_fruitUpHoldStartMs) : 0UL;
  const unsigned long down_hold_ms = (g_fruitDownHoldStartMs > 0) ? (now - g_fruitDownHoldStartMs) : 0UL;
  const unsigned long recovery_ms = (g_fruitRecoveryUntilMs > now) ? (g_fruitRecoveryUntilMs - now) : 0UL;
  const unsigned long idle_stable_ms = (g_fruitIdleStableStartMs > 0) ? (now - g_fruitIdleStableStartMs) : 0UL;
  const unsigned long fsm_age_ms = (g_fruitFsmStateStartMs > 0) ? (now - g_fruitFsmStateStartMs) : 0UL;
  const unsigned long possible_touch_ms = (g_fruitPossibleTouchStartMs > 0) ? (now - g_fruitPossibleTouchStartMs) : 0UL;
  const unsigned long possible_release_ms = (g_fruitPossibleReleaseStartMs > 0) ? (now - g_fruitPossibleReleaseStartMs) : 0UL;
  const unsigned long output_age_ms = (g_fruitLastOutputMs > 0) ? (now - g_fruitLastOutputMs) : 0UL;
  const char* phase = !g_fruitCalFastDone ? "cal_fast" : (!g_fruitCalRefineDone ? "cal_refine" : "track");
  const char* state = g_fruitContactActive ? "contact" : "idle";

  char line[1024];
  int written = snprintf(
      line,
      sizeof(line),
      "FRUITDIAG node=%s id=%u fw=%s variant=%u mode=%s phase=%s state=%s fsm=%s entry_reason=%s exit_reason=%s block_reason=%s t_ms=%lu raw=%.4f filt=%.4f base=%.4f prev=%.4f dv=%.4f raw_delta=%.4f slope=%.4f sigma=%.4f th_up=%.4f th_down=%.4f cand=%d ref=%d exit=%d raw_rail=%d quiet_idle=%d entry_armed=%d entry_relaxed=%d entry_rescue=%d touch_sign=%d pending_sign=%d cal_fast=%d cal_refine=%d vmin=%.4f vmax=%.4f hold_up_ms=%lu hold_down_ms=%lu recovery_ms=%lu energy_age_ms=%lu contact_age_ms=%lu release_age_ms=%lu idle_stable_ms=%lu fsm_age_ms=%lu poss_touch_ms=%lu poss_release_ms=%lu peak_dv=%.4f peak_raw=%.4f note=%u out_req=%d out_on=%d out_ok=%d out_fail=%u out_age_ms=%lu",
      NODE_LABEL,
      (unsigned)NODE_ID,
      OKUA_FW_VERSION_STR,
      (unsigned)ACTIVE_FRUIT_VARIANT,
      (ACTIVE_SENSOR == SENSOR_FRUIT) ? "fruit" : "plant",
      phase,
      state,
      fruitFsmName(g_fruitFsm),
      g_fruitLastEntryReason,
      g_fruitLastExitReason,
      g_fruitDiagBlockReason,
      now,
      vRaw,
      g_fruitFilteredV,
      g_fruitBaselineV,
      g_fruitPrevV,
      dv_proj,
      g_fruitDiagRawDelta,
      slope_proj,
      g_fruitSigma,
      th_up,
      th_down,
      enterCand ? 1 : 0,
      refractory ? 1 : 0,
      exitNow ? 1 : 0,
      g_fruitDiagRawRail ? 1 : 0,
      g_fruitDiagQuietIdle ? 1 : 0,
      g_fruitDiagEntryArmed ? 1 : 0,
      g_fruitDiagEntryRelaxed ? 1 : 0,
      g_fruitDiagEntryRescue ? 1 : 0,
      (int)g_fruitTouchSign,
      (int)g_fruitPendingSign,
      g_fruitCalFastDone ? 1 : 0,
      g_fruitCalRefineDone ? 1 : 0,
      g_fruitVMin,
      g_fruitVMax,
      up_hold_ms,
      down_hold_ms,
      recovery_ms,
      energy_age_ms,
      contact_age_ms,
      release_age_ms,
      idle_stable_ms,
      fsm_age_ms,
      possible_touch_ms,
      possible_release_ms,
      g_fruitContactPeakAbsDv,
      g_fruitContactPeakRawDelta,
      (unsigned)fruitCurrentHarmonyNote(),
      g_fruitLastOutputRequested ? 1 : 0,
      g_fruitLastOutputNoteOn ? 1 : 0,
      g_fruitLastOutputOk ? 1 : 0,
      (unsigned)g_fruitLastOutputFailures,
      output_age_ms);

  if (written <= 0) return;
  if (written >= (int)sizeof(line)) {
    line[sizeof(line) - 1] = '\0';
  }

  sendUdpRawTo(DIAG_PC_IP, (const uint8_t*)line, strlen(line), FRUIT_DEBUG_UDP_PORT);
}
#endif

void calibrateFruit2Phases(float vNow) {
  const int WIN = 121;
  static float win[WIN];
  static int wi = 0;
  static int filled = 0;

  unsigned long now = millis();

  if (vNow <= FRUIT_BOOT_CAL_VALID_MIN_V || vNow >= FRUIT_BOOT_CAL_VALID_MAX_V) {
    wi = 0;
    filled = 0;
    return;
  }

  win[wi++] = vNow;
  if (wi >= WIN) wi = 0;
  if (filled < WIN) filled++;

  if (!g_fruitCalFastDone && FRUIT_FIXED_OFFSET_V >= 0.0f) {
    // Optional manual seed for sensors that need a fixed ADC anchor.
    g_fruitBaselineV = FRUIT_FIXED_OFFSET_V;
    if (g_fruitBaselineV < FRUIT_BASE_CLAMP_MIN) g_fruitBaselineV = FRUIT_BASE_CLAMP_MIN;
    g_fruitCalFastDone = true;
    g_fruitRefineStartMs = now;
  }

  if (!g_fruitCalFastDone) {
    if ((now - g_fruitBootMs) >= FRUIT_AUTOCAL_FAST_MS && filled >= WIN) {
      // mediana simple
      float tmp[WIN];
      for (int i = 0; i < WIN; ++i) tmp[i] = win[i];

      for (int i = 1; i < WIN; ++i) {
        float key = tmp[i];
        int j = i - 1;
        while (j >= 0 && tmp[j] > key) {
          tmp[j + 1] = tmp[j];
          j--;
        }
        tmp[j + 1] = key;
      }

      g_fruitBaselineV = tmp[WIN / 2];
      if (g_fruitBaselineV < FRUIT_BASE_CLAMP_MIN) g_fruitBaselineV = FRUIT_BASE_CLAMP_MIN;
      float span = tmp[WIN - 1] - tmp[0];
      if (span > FRUIT_BOOT_CAL_MAX_SPAN_V) {
        wi = 0;
        filled = 0;
        return;
      }

      g_fruitCalFastDone = true;
      g_fruitRefineStartMs = now;
    }
    return;
  }

  if (!g_fruitCalRefineDone) {
    if (FRUIT_FIXED_OFFSET_V >= 0.0f) {
      float window = FRUIT_FIXED_OFFSET_WINDOW_V;
      if (window < 0.02f) window = 0.02f;
      if (fabsf(vNow - FRUIT_FIXED_OFFSET_V) <= window) {
        float target = (0.85f * FRUIT_FIXED_OFFSET_V) + (0.15f * vNow);
        float dv = target - g_fruitBaselineV;
        g_fruitBaselineV += 0.02f * dv;
      } else {
        g_fruitBaselineV += 0.002f * (FRUIT_FIXED_OFFSET_V - g_fruitBaselineV);
      }
      if (g_fruitBaselineV < FRUIT_BASE_CLAMP_MIN) g_fruitBaselineV = FRUIT_BASE_CLAMP_MIN;
    } else {
      float dv = vNow - g_fruitBaselineV;
      if (fabsf(dv) < 0.12f) {
        g_fruitBaselineV += 0.01f * dv;
        if (g_fruitBaselineV < FRUIT_BASE_CLAMP_MIN) g_fruitBaselineV = FRUIT_BASE_CLAMP_MIN;
      }
    }

    if ((now - g_fruitRefineStartMs) >= FRUIT_AUTOCAL_REFINE_MS) {
      g_fruitCalRefineDone = true;
    }
  }

  if ((now - g_fruitBootMs) >= FRUIT_HARD_TIMEOUT_MS) {
    g_fruitCalFastDone = true;
    g_fruitCalRefineDone = true;
  }
}

float fruitMorningEntryScale(unsigned long now) {
  const unsigned long ageMs = now - g_fruitBootMs;
  if (ageMs <= FRUIT_MORNING_ARM_START_MS) return 1.0f;
  if (ageMs >= FRUIT_MORNING_ARM_END_MS) return FRUIT_MORNING_ARM_MIN_SCALE;

  const float span = (float)(FRUIT_MORNING_ARM_END_MS - FRUIT_MORNING_ARM_START_MS);
  const float t = (float)(ageMs - FRUIT_MORNING_ARM_START_MS) / span;
  return 1.0f - t * (1.0f - FRUIT_MORNING_ARM_MIN_SCALE);
}

void fruitSetFsm(uint8_t next, unsigned long now) {
  if (g_fruitFsm != next) {
    g_fruitFsm = next;
    g_fruitFsmStateStartMs = now;
  }
}

void fruitUpdateIdleBaseline(unsigned long now) {
  if (g_fruitContactActive || now < g_fruitRecoveryUntilMs) return;

  float baseA = FRUIT_BASE_A;
  float idleGap = fabsf(g_fruitFilteredV - g_fruitBaselineV);
  if (g_fruitIdleStableStartMs != 0 && (now - g_fruitIdleStableStartMs) >= FRUIT_IDLE_STABLE_MS) {
    baseA = FRUIT_BASE_A_STABLE;
  } else if (idleGap >= 0.25f) {
    // When the baseline is far from the current idle signal, recenter faster so
    // we do not keep re-entering contact on a stale offset.
    baseA = FRUIT_BASE_A_RECENTER;
  }

  if (FRUIT_FIXED_OFFSET_V >= 0.0f) {
    float window = FRUIT_FIXED_OFFSET_WINDOW_V;
    if (window < 0.02f) window = 0.02f;
    if (fabsf(g_fruitFilteredV - FRUIT_FIXED_OFFSET_V) <= window) {
      g_fruitBaselineV += baseA * (g_fruitFilteredV - g_fruitBaselineV);
    } else {
      g_fruitBaselineV += (baseA * 0.25f) * (FRUIT_FIXED_OFFSET_V - g_fruitBaselineV);
    }
  } else {
    g_fruitBaselineV += baseA * (g_fruitFilteredV - g_fruitBaselineV);
  }
  if (g_fruitBaselineV < FRUIT_BASE_CLAMP_MIN) g_fruitBaselineV = FRUIT_BASE_CLAMP_MIN;
}

void fruitFinishTouchV20(
    unsigned long now,
    const char* reason,
    float vRaw,
    float dv_proj,
    float slope_proj,
    float th_up,
    float th_down,
    bool enterCand,
    bool refractory) {
  g_fruitContactActive = false;
  g_fruitLastReleaseMs = now;
  g_fruitLastExitReason = reason;
  // Reset polarity after release so the next touch re-derives the sign from
  // the current motion instead of inheriting a stale contact state.
  g_fruitPendingSign = +1;
  g_fruitUpHoldStartMs = 0;
  g_fruitDownHoldStartMs = 0;
  g_fruitPossibleTouchStartMs = 0;
  g_fruitPossibleReleaseStartMs = 0;
  g_fruitRecoveryUntilMs = now + FRUIT_RECOVERY_MS;
  g_fruitReleaseCleanupUntilMs = now + FRUIT_RELEASE_CLEANUP_MS;
  g_fruitReleaseCleanupLastMs = 0;
  g_fruitIdleStableStartMs = 0;
  fruitSetFsm(FRUIT_FSM_LOCKOUT, now);

  fruitSendAll(false, 0, 0);
#if FRUIT_DEBUG_SERIAL
  Serial.printf("[FRUIT] FSM EXIT reason=%s dv=%.4f th_down=%.4f slope=%.4f\n", reason, dv_proj, th_down, slope_proj);
#endif
#if FRUIT_DEBUG_UDP
  fruitSendDiagUdp(now, vRaw, dv_proj, slope_proj, th_up, th_down, enterCand, refractory, true, true);
#endif
}

void serviceFruitFieldV20(
    unsigned long now,
    float vRaw,
    float dv,
    float dv_dt,
    float abs_dv,
    float abs_slope,
    int8_t dvSign,
    float th_up,
    float th_down,
    bool refractory) {
  const float rawDelta = vRaw - g_fruitBaselineV;
  const float absRawDelta = fabsf(rawDelta);
  const bool rawRail = (vRaw <= 0.050f) || (vRaw >= 3.250f);
  const int8_t rawSign = (rawDelta >= 0.0f) ? +1 : -1;
  const int8_t signalSign = (absRawDelta > (abs_dv * 1.35f)) ? rawSign : dvSign;
  const int8_t activeSign = g_fruitContactActive ? g_fruitTouchSign : signalSign;
  const float dv_proj = dv * (float)activeSign;
  const float slope_proj = dv_dt * (float)activeSign;

  const float softEntryTh = fmaxf(th_up, FRUIT_FSM_ENTRY_SOFT_ABS);
  const float strongEntryTh = fmaxf(FRUIT_FSM_ENTRY_STRONG_ABS, th_up * 1.80f);
  const float rawEntryTh = fmaxf(FRUIT_FSM_ENTRY_RAW_ABS, th_up * 3.00f);
  const unsigned long idleStableMs = (g_fruitIdleStableStartMs > 0) ? (now - g_fruitIdleStableStartMs) : 0UL;
  const bool entryArmed = (g_fruitIdleStableStartMs != 0) && (idleStableMs >= 250UL);
  const bool entryRelaxedReady = entryArmed && (idleStableMs >= FRUIT_MORNING_ARM_IDLE_MS);

  // The relaxed route only opens after a genuinely quiet idle window. This keeps
  // stale baseline offsets from repeatedly re-entering contact.
  bool entrySoft = entryRelaxedReady &&
                   (abs_dv >= softEntryTh) &&
                   ((abs_slope >= 0.035f) || (absRawDelta >= rawEntryTh * 0.55f));
  bool entryStrongArmed = entryArmed &&
                          ((abs_dv >= strongEntryTh) || (absRawDelta >= rawEntryTh) || rawRail);
  bool entryRescueRail = (!entryArmed) &&
                         rawRail &&
                         (absRawDelta >= FRUIT_FSM_RESCUE_RAW_ABS) &&
                         (abs_dv >= FRUIT_FSM_RESCUE_DV_ABS) &&
                         (abs_slope >= FRUIT_FSM_RESCUE_SLOPE_ABS);
  bool entryRescueMotion = (!entryArmed) &&
                           !rawRail &&
                           (absRawDelta >= FRUIT_FSM_RESCUE_MOTION_RAW_ABS) &&
                           (abs_dv >= FRUIT_FSM_RESCUE_MOTION_DV_ABS) &&
                           (abs_slope >= FRUIT_FSM_RESCUE_MOTION_SLOPE_ABS);
  bool entryRescue = entryRescueRail || entryRescueMotion;
  bool entryStrong = entryStrongArmed || entryRescue;
  bool entryCandidate = entrySoft || entryStrong;
  const char* entryReason = entryRescueRail ? "rescue_rail" :
                           (entryRescueMotion ? "rescue_motion" :
                           (entryStrongArmed ? (rawRail ? "rail_strong" : "strong_delta") :
                           (entrySoft ? "soft_delta" : "none")));
  unsigned long entryHoldMs = entryRescueRail ? FRUIT_FSM_RESCUE_HOLD_MS :
                              (entryRescueMotion ? FRUIT_FSM_RESCUE_MOTION_HOLD_MS :
                              (entryStrong ? FRUIT_FSM_STRONG_HOLD_MS : FRUIT_FSM_SOFT_HOLD_MS));
  if (rawRail && entryHoldMs < 70UL) entryHoldMs = 70UL;

  bool quietIdle = (!g_fruitContactActive &&
                    (abs_dv <= fmaxf(th_down * 1.75f, 0.060f)) &&
                    (absRawDelta <= fmaxf(th_up * 4.00f, 0.200f)));
  const char* blockReason = "none";
  if (refractory) {
    blockReason = "refractory";
  } else if (now < g_fruitForceRearmUntilMs) {
    blockReason = "force_rearm";
  } else if (!entryCandidate) {
    const bool visibleMove = rawRail ||
                             (abs_dv >= softEntryTh) ||
                             (absRawDelta >= rawEntryTh) ||
                             (abs_slope >= FRUIT_FSM_RESCUE_SLOPE_ABS);
    if (!entryArmed && visibleMove) {
      blockReason = "not_armed";
    } else if (!entryRelaxedReady && (abs_dv >= softEntryTh)) {
      blockReason = "relaxed_not_ready";
    } else {
      blockReason = "below_entry";
    }
  }
  g_fruitDiagRawRail = rawRail;
  g_fruitDiagQuietIdle = quietIdle;
  g_fruitDiagEntryArmed = entryArmed;
  g_fruitDiagEntryRelaxed = entryRelaxedReady;
  g_fruitDiagEntryRescue = entryRescue;
  g_fruitDiagRawDelta = rawDelta;
  g_fruitDiagBlockReason = blockReason;
  if (quietIdle && g_fruitFsm == FRUIT_FSM_IDLE) {
    if (g_fruitIdleStableStartMs == 0) g_fruitIdleStableStartMs = now;
  } else if (g_fruitFsm != FRUIT_FSM_LOCKOUT && g_fruitFsm != FRUIT_FSM_POSSIBLE_TOUCH) {
    g_fruitIdleStableStartMs = 0;
  }

  if (!g_fruitContactActive && g_fruitReleaseCleanupUntilMs > now) {
    if (g_fruitReleaseCleanupLastMs == 0 ||
        (now - g_fruitReleaseCleanupLastMs) >= FRUIT_RELEASE_CLEANUP_INTERVAL_MS) {
      g_fruitReleaseCleanupLastMs = now;
      fruitSendAll(false, 0, 0);
    }
  }

  switch (g_fruitFsm) {
    case FRUIT_FSM_IDLE:
      g_fruitContactActive = false;
      if (!refractory && now >= g_fruitForceRearmUntilMs && entryCandidate) {
        g_fruitPendingSign = signalSign;
        g_fruitLastEntryReason = entryReason;
        g_fruitPossibleTouchStartMs = now;
        fruitSetFsm(FRUIT_FSM_POSSIBLE_TOUCH, now);
      }
      break;

    case FRUIT_FSM_POSSIBLE_TOUCH:
      if (!entryCandidate) {
        g_fruitPossibleTouchStartMs = 0;
        fruitSetFsm(FRUIT_FSM_IDLE, now);
      } else if (signalSign != g_fruitPendingSign && !entryStrong) {
        g_fruitPendingSign = signalSign;
        g_fruitPossibleTouchStartMs = now;
        g_fruitLastEntryReason = "sign_reset";
      } else if (now - g_fruitPossibleTouchStartMs >= entryHoldMs) {
        g_fruitContactActive = true;
        g_fruitTouchSign = g_fruitPendingSign;
        g_fruitContactStartMs = now;
        g_fruitLastEnergyOkMs = now;
        g_fruitDownHoldStartMs = 0;
        g_fruitLastKeepaliveMs = 0;
        g_fruitReleaseCleanupUntilMs = 0;
        g_fruitReleaseCleanupLastMs = 0;
        g_fruitContactPeakAbsDv = abs_dv;
        g_fruitContactPeakRawDelta = absRawDelta;
        g_fruitPossibleReleaseStartMs = 0;
        fruitSetFsm(FRUIT_FSM_TOUCH_ACTIVE, now);
        fruitSendAll(true, 100, EVT_FLAG_TOUCH);
#if FRUIT_DEBUG_SERIAL
        Serial.printf("[FRUIT] FSM ENTER reason=%s dv=%.4f rawDelta=%.4f th_up=%.4f slope=%.4f\n",
                      g_fruitLastEntryReason, dv_proj, absRawDelta, th_up, slope_proj);
#endif
#if FRUIT_DEBUG_UDP
        fruitSendDiagUdp(now, vRaw, dv_proj, slope_proj, th_up, th_down, true, refractory, false, true);
#endif
      }
      break;

    case FRUIT_FSM_TOUCH_ACTIVE:
    case FRUIT_FSM_POSSIBLE_RELEASE: {
      g_fruitContactActive = true;
      if (abs_dv > g_fruitContactPeakAbsDv) g_fruitContactPeakAbsDv = abs_dv;
      if (absRawDelta > g_fruitContactPeakRawDelta) g_fruitContactPeakRawDelta = absRawDelta;
      if (abs_dv >= FD.energy_frac * th_up || absRawDelta >= rawEntryTh * 0.50f) {
        g_fruitLastEnergyOkMs = now;
      }
      g_fruitIdleStableStartMs = 0;

#if FRUIT_KEEPALIVE_ENABLE
      if ((now - g_fruitLastKeepaliveMs) >= FRUIT_KEEPALIVE_MS) {
        g_fruitLastKeepaliveMs = now;
        fruitSendAll(true, 60, EVT_FLAG_TOUCH);
      }
#endif

      bool contactStable = (now - g_fruitContactStartMs >= FRUIT_MIN_CONTACT_MS);
      float releaseBand = fmaxf(FRUIT_FSM_RELEASE_BAND_ABS, th_down * 3.20f);
      float releaseRawBand = fmaxf(FRUIT_FSM_RELEASE_RAW_BAND_ABS, th_up * 3.60f);
      float derivBand = fmaxf(FRUIT_FSM_RELEASE_DERIV_BAND,
                              g_fruitContactPeakAbsDv * 0.82f);
      bool releaseLevel = (abs_dv <= releaseBand) && (absRawDelta <= releaseRawBand);
      bool releaseDeriv = (slope_proj <= -FD.slope_release) && (abs_dv <= derivBand);
      bool releaseNoEnergy = (now - g_fruitLastEnergyOkMs >= FD.noenergy_ms) &&
                             (abs_dv <= fmaxf(g_fruitContactPeakAbsDv * 0.65f, releaseBand));
      bool releaseTimeout = (now - g_fruitContactStartMs >= FRUIT_FSM_TIMEOUT_MS);
      bool releaseStuck = (now - g_fruitContactStartMs >= FRUIT_STUCK_CONTACT_MS);
      bool releaseCandidate = contactStable && (releaseLevel || releaseDeriv || releaseNoEnergy || releaseTimeout || releaseStuck);

      if (releaseTimeout || releaseStuck) {
        fruitFinishTouchV20(now, releaseStuck ? "stuck" : "timeout", vRaw, dv_proj, slope_proj, th_up, th_down, entryCandidate, refractory);
        break;
      }

      if (g_fruitFsm == FRUIT_FSM_TOUCH_ACTIVE) {
        if (releaseCandidate) {
          g_fruitPossibleReleaseStartMs = now;
          g_fruitLastExitReason = releaseLevel ? "level" : (releaseDeriv ? "deriv" : "no_energy");
          fruitSetFsm(FRUIT_FSM_POSSIBLE_RELEASE, now);
        }
      } else {
        bool clearRetouch = (dv_proj >= fmaxf(g_fruitContactPeakAbsDv * FRUIT_FSM_RETOUCH_PEAK_FRAC, strongEntryTh)) &&
                            (slope_proj > -0.020f);
        bool releaseHeld = (now - g_fruitPossibleReleaseStartMs >= FRUIT_FSM_RELEASE_HOLD_MS);
        if (clearRetouch) {
          g_fruitPossibleReleaseStartMs = 0;
          fruitSetFsm(FRUIT_FSM_TOUCH_ACTIVE, now);
        } else if (releaseHeld) {
          fruitFinishTouchV20(now, g_fruitLastExitReason, vRaw, dv_proj, slope_proj, th_up, th_down, entryCandidate, refractory);
        }
      }
      break;
    }

    case FRUIT_FSM_LOCKOUT:
      g_fruitContactActive = false;
      if (now - g_fruitFsmStateStartMs >= FRUIT_FSM_LOCKOUT_MS) {
        g_fruitPossibleReleaseStartMs = 0;
        g_fruitPossibleTouchStartMs = 0;
        fruitSetFsm(FRUIT_FSM_IDLE, now);
      }
      break;
  }

  if (g_fruitContactActive) {
    g_lastStateFlags |= STATF_TOUCH_ACTIVE;
  } else {
    g_lastStateFlags &= (uint8_t)~STATF_TOUCH_ACTIVE;
  }

  if (g_fruitFsm == FRUIT_FSM_IDLE) {
    fruitUpdateIdleBaseline(now);
  }

#if FRUIT_DEBUG_SERIAL
  if ((now - g_fruitDebugLastMs) >= 200UL) {
    g_fruitDebugLastMs = now;
    Serial.printf("[FRUIT] fsm=%u v=%.4f b=%.4f dv=%.4f dvt=%.4f sig=%.4f up=%.4f dn=%.4f ec=%d ca=%d\n",
                  (unsigned)g_fruitFsm, g_fruitFilteredV, g_fruitBaselineV, dv, dv_dt,
                  g_fruitSigma, th_up, th_down, (int)entryCandidate, (int)g_fruitContactActive);
  }
#endif
#if FRUIT_DEBUG_UDP
  fruitSendDiagUdp(now, vRaw, dv_proj, slope_proj, th_up, th_down, entryCandidate, refractory, false, false);
#endif
}

void serviceFruitField() {
  unsigned long now = millis();

  float vRaw = readVmed3();
  g_fruitVMin = min(g_fruitVMin, vRaw);
  g_fruitVMax = max(g_fruitVMax, vRaw);
  g_fruitFilteredV = FRUIT_FILTER_ALPHA * vRaw + (1.0f - FRUIT_FILTER_ALPHA) * g_fruitFilteredV;

  if (!g_fruitCalFastDone || !g_fruitCalRefineDone) {
    calibrateFruit2Phases(g_fruitFilteredV);
    g_lastStateFlags |= STATF_CALIBRATING;
#if FRUIT_DEBUG_UDP
    fruitSendDiagUdp(now, vRaw, 0.0f, 0.0f, 0.0f, 0.0f, false, false, false, true);
#endif
    if ((now - g_fruitBootMs) >= FRUIT_BOOT_STUCK_REBOOT_MS) {
      scheduleSoftReboot();
#if FRUIT_DEBUG_SERIAL
      Serial.printf("[FRUIT] boot calibration timeout -> soft reboot\n");
#endif
    }
    return;
  } else {
    g_lastStateFlags &= (uint8_t)~STATF_CALIBRATING;
  }

  unsigned long dtMs = 1;
  static unsigned long prevMs = now;
  dtMs = now - prevMs;
  if (dtMs == 0) dtMs = 1;
  prevMs = now;

  float dv = g_fruitFilteredV - g_fruitBaselineV;
  float dv_dt = (g_fruitFilteredV - g_fruitPrevV) / (float(dtMs) / 1000.0f);
  g_fruitPrevV = g_fruitFilteredV;

  float abs_dv = fabsf(dv);
  float abs_slope = fabsf(dv_dt);
  int8_t dvSign = (dv >= 0.0f) ? +1 : -1;
  int8_t signUse = g_fruitContactActive ? g_fruitTouchSign : ((g_fruitUpHoldStartMs != 0) ? g_fruitPendingSign : dvSign);

  float dv_proj = dv * (float)signUse;
  float slope_proj = dv_dt * (float)signUse;

  bool morningRelaxed = (g_fruitIdleStableStartMs != 0) &&
                        ((now - g_fruitIdleStableStartMs) >= FRUIT_MORNING_ARM_IDLE_MS) &&
                        ((now - g_fruitBootMs) >= FRUIT_MORNING_ARM_START_MS) &&
                        (g_fruitSigma <= FRUIT_MORNING_ARM_SIGMA_MAX);
  float morningScale = morningRelaxed ? fruitMorningEntryScale(now) : 1.0f;
  if (morningScale < FRUIT_MORNING_ARM_MIN_SCALE) morningScale = FRUIT_MORNING_ARM_MIN_SCALE;
  unsigned long morningHoldMs = FD.on_hold_ms;
  if (morningRelaxed) {
    float holdScaled = (float)FD.on_hold_ms * FRUIT_MORNING_ARM_HOLD_SCALE;
    if (holdScaled < (float)FRUIT_MORNING_ARM_HOLD_MIN_MS) holdScaled = (float)FRUIT_MORNING_ARM_HOLD_MIN_MS;
    morningHoldMs = (unsigned long)holdScaled;
  }
  bool entryArmed = (g_fruitIdleStableStartMs != 0) &&
                    ((now - g_fruitIdleStableStartMs) >= 250UL);
  bool postReleaseRearmWindow = (g_fruitLastReleaseMs != 0) &&
                                ((now - g_fruitLastReleaseMs) < FRUIT_POST_RELEASE_REARM_MS);
  bool veryStrongReentry = (abs_dv >= fmaxf(FD.abs_strong_up * 1.55f, FRUIT_POST_RELEASE_REARM_DV_ABS)) &&
                           (abs_slope >= FRUIT_POST_RELEASE_REARM_SLOPE_ABS);

  float th_rel_up = 0.0f;
  float relBase = g_fruitBaselineV;
  if (relBase > FRUIT_REL_BASE_CAP_V) relBase = FRUIT_REL_BASE_CAP_V;
  if (relBase >= FD.v_rel_min) th_rel_up = FD.rel_up * relBase;

  float th_up   = fmaxf(FD.abs_min_up * morningScale,   fmaxf(th_rel_up * morningScale, FD.k_sigma_up * g_fruitSigma * morningScale));
  float th_down = fmaxf(FD.abs_min_down * morningScale, fmaxf(FD.rel_down_f * th_up, FD.k_sigma_down * g_fruitSigma * morningScale));

  if (!g_fruitContactActive && now >= g_fruitRecoveryUntilMs) {
    bool sigmaQuiet = (abs_dv <= fmaxf(th_up * 0.85f, 0.025f)) &&
                      (abs_slope <= fmaxf(FD.slope_min_strong * 1.2f, 0.18f));
    float sigmaDv = dv;
    if (!sigmaQuiet) {
      float sigmaClip = fmaxf(th_up * 0.90f, 0.030f);
      if (sigmaDv > sigmaClip) sigmaDv = sigmaClip;
      else if (sigmaDv < -sigmaClip) sigmaDv = -sigmaClip;
    }
    float sigmaAlpha = sigmaQuiet ? 0.05f : 0.012f;
    g_fruitVarDv = (1.0f - sigmaAlpha) * g_fruitVarDv + sigmaAlpha * (sigmaDv * sigmaDv);
    g_fruitSigma = sqrtf(fmaxf(g_fruitVarDv, 0.0f));
  }

  if (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V15) {
    bool refractory = (now - g_fruitLastReleaseMs < FD.refract_ms);
    serviceFruitFieldV20(now, vRaw, dv, dv_dt, abs_dv, abs_slope, dvSign, th_up, th_down, refractory);
    return;
  }

  const unsigned long releaseAgeMs = (g_fruitLastReleaseMs > 0) ? (now - g_fruitLastReleaseMs) : 0UL;
  const bool rawRail = (vRaw <= 0.050f) || (vRaw >= 3.250f);
  const float entryRawDelta = fabsf(vRaw - g_fruitBaselineV);
  bool ampStrongRaw = (abs_dv >= FD.abs_strong_up * morningScale);
  bool fastRearmReady = postReleaseRearmWindow &&
                        (releaseAgeMs >= FRUIT_V7_FAST_REARM_MIN_MS) &&
                        (abs_dv >= fmaxf(FRUIT_V7_FAST_REARM_DV_ABS, th_up * FRUIT_V7_FAST_REARM_TH_SCALE)) &&
                        ((abs_slope >= FRUIT_V7_FAST_REARM_SLOPE_ABS) ||
                         (entryRawDelta >= FRUIT_V7_FAST_REARM_RAW_ABS) ||
                         rawRail);
  bool ampStrong = ampStrongRaw && (!postReleaseRearmWindow || entryArmed || veryStrongReentry || fastRearmReady);
  bool ampGate   = (abs_dv >= th_up);
  bool slopeGate = (abs_slope >= FD.slope_min_strong * morningScale);
  bool enterCand = ampStrong || fastRearmReady || (entryArmed && ampGate && slopeGate);
  bool entrySpike = (abs_slope >= 15.0f) || (abs_dv >= 0.14f);
  unsigned long entryHoldMs = morningHoldMs;
  if (fastRearmReady && entryHoldMs > FRUIT_V7_FAST_REARM_HOLD_MS) {
    entryHoldMs = FRUIT_V7_FAST_REARM_HOLD_MS;
  }
  if (entrySpike) {
    unsigned long spikeHoldMs = morningHoldMs + 120UL;
    if (!fastRearmReady && spikeHoldMs > entryHoldMs) entryHoldMs = spikeHoldMs;
  }

  bool refractory = (now - g_fruitLastReleaseMs < FD.refract_ms);
  const char* blockReason = "none";
  if (g_fruitContactActive) {
    blockReason = "contact";
  } else if (refractory) {
    blockReason = "refractory";
  } else if (now < g_fruitForceRearmUntilMs) {
    blockReason = "force_rearm";
  } else if (fastRearmReady) {
    blockReason = "none";
  } else if (postReleaseRearmWindow && ampStrongRaw && !ampStrong) {
    blockReason = "post_release_rearm";
  } else if (!enterCand && !entryArmed && (ampGate || ampStrongRaw || entrySpike)) {
    blockReason = "not_armed";
  } else if (!enterCand) {
    blockReason = "below_entry";
  }
  g_fruitDiagRawRail = rawRail;
  g_fruitDiagQuietIdle = false;
  g_fruitDiagEntryArmed = entryArmed;
  g_fruitDiagEntryRelaxed = morningRelaxed;
  g_fruitDiagEntryRescue = fastRearmReady || (postReleaseRearmWindow && veryStrongReentry);
  g_fruitDiagRawDelta = vRaw - g_fruitBaselineV;
  g_fruitDiagBlockReason = blockReason;

  if (enterCand) {
    if (g_fruitUpHoldStartMs == 0) {
      // Lock candidate polarity during hold to avoid bidirectional noise retriggers.
      g_fruitPendingSign = dvSign;
      g_fruitUpHoldStartMs = now;
    }
  } else {
    g_fruitUpHoldStartMs = 0;
  }

  bool postReleaseReady = (g_fruitLastReleaseMs == 0) ||
                          (now - g_fruitLastReleaseMs >= FRUIT_POST_RELEASE_LOCKOUT_MS);
  bool rearmReady = (now >= g_fruitForceRearmUntilMs);
  bool enterNow = (!refractory && !g_fruitContactActive &&
                   rearmReady &&
                   postReleaseReady &&
                   g_fruitUpHoldStartMs &&
                   (now - g_fruitUpHoldStartMs >= entryHoldMs));

  if (enterNow) {
    g_fruitContactActive = true;
    g_fruitTouchSign = g_fruitPendingSign;
    g_fruitLastEntryReason = fastRearmReady ? "fast_rearm" :
                             (ampStrong ? "strong_delta" :
                             ((entryArmed && ampGate && slopeGate) ? "armed_delta" :
                             (entrySpike ? "spike" : "entry")));
    g_fruitContactStartMs = now;
    g_fruitLastEnergyOkMs = now;
    g_fruitDownHoldStartMs = 0;
    g_fruitLastKeepaliveMs = 0;
    g_fruitReleaseCleanupUntilMs = 0;
    g_fruitReleaseCleanupLastMs = 0;
    g_fruitContactPeakAbsDv = abs_dv;
    g_fruitContactPeakRawDelta = fabsf(g_fruitFilteredV - g_fruitBaselineV);

    fruitSendAll(true, 100, EVT_FLAG_TOUCH);
#if FRUIT_DEBUG_SERIAL
    Serial.printf(
      "[FRUIT] ENTER dv=%.4f th_up=%.4f slope=%.4f sign=%d base=%.4f filt=%.4f\n",
      dv_proj, th_up, slope_proj, (int)g_fruitTouchSign, g_fruitBaselineV, g_fruitFilteredV);
#endif
#if FRUIT_DEBUG_UDP
    fruitSendDiagUdp(now, vRaw, dv_proj, slope_proj, th_up, th_down, enterCand, refractory, false, true);
#endif
  }

  if (g_fruitContactActive) {
    g_lastStateFlags |= STATF_TOUCH_ACTIVE;
  } else {
    g_lastStateFlags &= (uint8_t)~STATF_TOUCH_ACTIVE;
  }

  float contactPeakBeforeUpdate = g_fruitContactPeakAbsDv;
  float contactRawPeakBeforeUpdate = g_fruitContactPeakRawDelta;

  if (g_fruitContactActive) {
    if (abs_dv > g_fruitContactPeakAbsDv) g_fruitContactPeakAbsDv = abs_dv;
    float activeRawDelta = fabsf(g_fruitFilteredV - g_fruitBaselineV);
    if (activeRawDelta > g_fruitContactPeakRawDelta) g_fruitContactPeakRawDelta = activeRawDelta;

    // 1.0.36 was keeping contacts alive because almost any residual dv refreshed
    // "energy". Require a meaningful fraction of the touch peak so no-energy can
    // become a real release path after the physical touch is gone.
    float sustainEnergyTh = fmaxf(th_up * 1.50f, g_fruitContactPeakAbsDv * FRUIT_V7_SUSTAIN_PEAK_FRAC);
    if (abs_dv >= sustainEnergyTh) {
      g_fruitLastEnergyOkMs = now;
    }
    g_fruitIdleStableStartMs = 0;

#if FRUIT_KEEPALIVE_ENABLE
    if ((now - g_fruitLastKeepaliveMs) >= FRUIT_KEEPALIVE_MS) {
      g_fruitLastKeepaliveMs = now;
      fruitSendAll(true, 60, EVT_FLAG_TOUCH);
    }
#endif
  }

  bool contactStable = (now - g_fruitContactStartMs >= FRUIT_MIN_CONTACT_MS);
  bool levelLow = (abs_dv <= th_down);
  if (levelLow) {
    if (g_fruitDownHoldStartMs == 0) g_fruitDownHoldStartMs = now;
  } else {
    g_fruitDownHoldStartMs = 0;
  }

  bool quietIdle = (!g_fruitContactActive &&
                    (abs_dv <= fmaxf(th_down * 1.75f, 0.060f)) &&
                    (fabsf(g_fruitFilteredV - g_fruitBaselineV) <= fmaxf(th_up * 2.25f, 0.100f)));
  g_fruitDiagQuietIdle = quietIdle;
  if (quietIdle) {
    if (g_fruitIdleStableStartMs == 0) g_fruitIdleStableStartMs = now;
  } else {
    g_fruitIdleStableStartMs = 0;
  }

  // Release must not depend only on returning perfectly to baseline. Field logs
  // from 1.0.36 showed real releases where baseline lag kept dv/raw_delta high
  // until the timeout. Restore the 1.0.28 discipline: accept a confirmed return
  // edge or a sustained collapse of touch energy, while still rejecting retouch.
  float absRawDelta = fabsf(g_fruitFilteredV - g_fruitBaselineV);
  float referencePeakAbsDv = (contactPeakBeforeUpdate > 0.0f) ? contactPeakBeforeUpdate : g_fruitContactPeakAbsDv;
  float referencePeakRawDelta = (contactRawPeakBeforeUpdate > 0.0f) ? contactRawPeakBeforeUpdate : g_fruitContactPeakRawDelta;
  float releaseBand = fmaxf(th_down * 2.40f, fmaxf(0.040f, g_fruitContactPeakAbsDv * FRUIT_V7_RELEASE_COLLAPSE_FRAC));
  float releaseRawBand = fmaxf(th_up * 3.20f, fmaxf(0.080f, g_fruitContactPeakRawDelta * 0.42f));
  float derivBand = fmaxf(releaseBand, g_fruitContactPeakAbsDv * FRUIT_V7_RELEASE_DERIV_FRAC);
  bool releaseQuiet = (abs_dv <= releaseBand) || (absRawDelta <= releaseRawBand);
  bool releaseLevel    = contactStable && (g_fruitDownHoldStartMs &&
                           (now - g_fruitDownHoldStartMs >= FD.off_hold_ms)) &&
                          releaseQuiet;
  bool releaseCollapse = contactStable &&
                         (abs_dv <= fmaxf(th_down * 2.80f, g_fruitContactPeakAbsDv * FRUIT_V7_RELEASE_COLLAPSE_FRAC)) &&
                         (absRawDelta <= releaseRawBand);
  bool releaseNoEnergy = contactStable &&
                          (now - g_fruitLastEnergyOkMs >= FD.noenergy_ms) &&
                          (abs_dv <= fmaxf(releaseBand, g_fruitContactPeakAbsDv * FRUIT_V7_RELEASE_NOENERGY_FRAC));
  bool releaseTimeout  = contactStable && (now - g_fruitContactStartMs >= FD.contact_max_ms);
  bool releaseDeriv    = contactStable &&
                         (slope_proj <= -FD.slope_release) &&
                         (abs_dv <= derivBand);
  bool releaseStuck    = contactStable && (now - g_fruitContactStartMs >= FRUIT_STUCK_CONTACT_MS);

  bool releaseCandidate = releaseLevel || releaseCollapse || releaseDeriv || releaseNoEnergy || releaseTimeout || releaseStuck;
  float strongEntryTh = fmaxf(FD.abs_strong_up * morningScale, th_up * 1.20f);
  bool releaseRetouch = (dv_proj >= fmaxf(referencePeakAbsDv * FRUIT_V7_RETOUCH_PEAK_FRAC, strongEntryTh)) &&
                        (abs_slope >= FD.slope_min_strong * 0.65f);
  bool exitNow = false;

  if (g_fruitContactActive) {
    if (releaseCandidate) {
      if (g_fruitPossibleReleaseStartMs == 0) {
        g_fruitPossibleReleaseStartMs = now;
        g_fruitLastExitReason = releaseLevel ? "level" :
                                (releaseCollapse ? "collapse" :
                                (releaseNoEnergy ? "no_energy" :
                                (releaseTimeout ? "timeout" :
                                (releaseStuck ? "stuck" :
                                (releaseDeriv ? "deriv" : "exit")))));
      } else if (releaseRetouch) {
        g_fruitPossibleReleaseStartMs = 0;
      } else {
        unsigned long requiredReleaseHold = releaseDeriv ? FRUIT_V7_RELEASE_DERIV_HOLD_MS : FRUIT_FSM_RELEASE_HOLD_MS;
        if (releaseCollapse && requiredReleaseHold > 120UL) requiredReleaseHold = 120UL;
        if (now - g_fruitPossibleReleaseStartMs >= requiredReleaseHold) {
          exitNow = true;
        }
      }
    } else if (g_fruitPossibleReleaseStartMs != 0 && !releaseRetouch &&
               (abs_dv <= fmaxf(releaseBand, g_fruitContactPeakAbsDv * FRUIT_V7_RELEASE_NOENERGY_FRAC))) {
      unsigned long requiredReleaseHold = (g_fruitLastExitReason == "deriv") ? FRUIT_V7_RELEASE_DERIV_HOLD_MS : FRUIT_FSM_RELEASE_HOLD_MS;
      if (now - g_fruitPossibleReleaseStartMs >= requiredReleaseHold) {
        exitNow = true;
      }
    } else if (releaseDeriv) {
      // Keep derivative visible in diagnostics, but do not let it close a touch on its own.
    } else {
      g_fruitPossibleReleaseStartMs = 0;
    }
  }

  if (exitNow) {
    bool forcedStuck = releaseStuck && !(releaseLevel || releaseNoEnergy || releaseTimeout);
    g_fruitLastExitReason = releaseLevel ? "level" :
                            (releaseCollapse ? "collapse" :
                            (releaseNoEnergy ? "no_energy" :
                            (releaseTimeout ? "timeout" :
                            (releaseStuck ? "stuck" :
                            (releaseDeriv ? "deriv" : "exit")))));
    g_fruitContactActive = false;
    g_fruitLastReleaseMs = now;
    // Neutralize the pending sign on release so the next entry can re-lock to
    // the current motion rather than carrying the previous touch polarity.
    g_fruitPendingSign = +1;
    g_fruitUpHoldStartMs = 0;
    g_fruitDownHoldStartMs = 0;
    g_fruitPossibleReleaseStartMs = 0;
    g_fruitRecoveryUntilMs = now + (forcedStuck ? (FRUIT_RECOVERY_MS * 4UL) : FRUIT_RECOVERY_MS);
    g_fruitReleaseCleanupUntilMs = now + FRUIT_RELEASE_CLEANUP_MS;
    g_fruitReleaseCleanupLastMs = 0;
    g_fruitIdleStableStartMs = 0;
    if (forcedStuck) {
      g_fruitForceRearmUntilMs = now + FRUIT_REARM_AFTER_STUCK_MS;
    }

    fruitSendAll(false, 0, 0);
#if FRUIT_DEBUG_SERIAL
    Serial.printf(
      "[FRUIT] EXIT dv=%.4f th_down=%.4f slope=%.4f rsn(level=%d,noE=%d,to=%d,der=%d,st=%d)\n",
      dv_proj, th_down, slope_proj,
      (int)releaseLevel, (int)releaseNoEnergy, (int)releaseTimeout, (int)releaseDeriv, (int)releaseStuck);
#endif
#if FRUIT_DEBUG_UDP
    fruitSendDiagUdp(now, vRaw, dv_proj, slope_proj, th_up, th_down, enterCand, refractory, true, true);
#endif
  }

  if (!g_fruitContactActive && g_fruitReleaseCleanupUntilMs > now) {
    if (g_fruitReleaseCleanupLastMs == 0 ||
        (now - g_fruitReleaseCleanupLastMs) >= FRUIT_RELEASE_CLEANUP_INTERVAL_MS) {
      g_fruitReleaseCleanupLastMs = now;
      fruitSendAll(false, 0, 0);
    }
  }

  if (!g_fruitContactActive && now >= g_fruitRecoveryUntilMs) {
    float baseA = FRUIT_BASE_A;
    if (g_fruitIdleStableStartMs != 0 && (now - g_fruitIdleStableStartMs) >= FRUIT_IDLE_STABLE_MS) {
      baseA = FRUIT_BASE_A_STABLE;
    }
    if (postReleaseRearmWindow) {
      baseA = fmaxf(baseA, FRUIT_BASE_A_RECENTER);
    }
    if (FRUIT_FIXED_OFFSET_V >= 0.0f) {
      float window = FRUIT_FIXED_OFFSET_WINDOW_V;
      if (window < 0.02f) window = 0.02f;
      if (fabsf(g_fruitFilteredV - FRUIT_FIXED_OFFSET_V) <= window) {
        g_fruitBaselineV += baseA * (g_fruitFilteredV - g_fruitBaselineV);
      } else {
        g_fruitBaselineV += (baseA * 0.25f) * (FRUIT_FIXED_OFFSET_V - g_fruitBaselineV);
      }
    } else {
      g_fruitBaselineV += baseA * (g_fruitFilteredV - g_fruitBaselineV);
    }
    if (g_fruitBaselineV < FRUIT_BASE_CLAMP_MIN) g_fruitBaselineV = FRUIT_BASE_CLAMP_MIN;
  }

#if FRUIT_DEBUG_SERIAL
  if ((now - g_fruitDebugLastMs) >= 200UL) {
    g_fruitDebugLastMs = now;
    Serial.printf(
      "[FRUIT] v=%.4f b=%.4f dv=%.4f dvt=%.4f sig=%.4f up=%.4f dn=%.4f ec=%d ca=%d us=%d ps=%d\n",
      g_fruitFilteredV, g_fruitBaselineV, dv, dv_dt, g_fruitSigma, th_up, th_down,
      (int)enterCand, (int)g_fruitContactActive, (int)dvSign, (int)g_fruitPendingSign);
  }
#endif
#if FRUIT_DEBUG_UDP
  fruitSendDiagUdp(now, vRaw, dv_proj, slope_proj, th_up, th_down, enterCand, refractory, exitNow, false);
#endif
}


/*============================================================================================
  ZONA 14 — MODO PRUEBA
============================================================================================*/

uint32_t g_testLastPlantEvtMs = 0;
uint32_t g_testLastFruitCycleMs = 0;
bool g_testFruitActive = false;
uint32_t g_testFruitTouchStartMs = 0;
uint8_t g_testPlantNote = 60;
#if OKUA_TEST_PROBE_ENABLED
bool g_testProbeLedOn = false;
uint8_t g_testProbeCurrentNote = (uint8_t)OKUA_TEST_PROBE_NOTE_START;

void testProbeInit() {
  pinMode(OKUA_TEST_PROBE_LED_PIN, OUTPUT);
  digitalWrite(OKUA_TEST_PROBE_LED_PIN, LOW);
  g_testProbeLedOn = false;
  g_testProbeCurrentNote = (uint8_t)OKUA_TEST_PROBE_NOTE_START;
}

void testProbeToggleLed() {
  g_testProbeLedOn = !g_testProbeLedOn;
  digitalWrite(OKUA_TEST_PROBE_LED_PIN, g_testProbeLedOn ? HIGH : LOW);
}

void servicePlantTestProbe() {
  const uint32_t now = millis();
  if (now - g_testLastPlantEvtMs < (uint32_t)OKUA_TEST_PROBE_INTERVAL_MS) return;
  g_testLastPlantEvtMs = now;

  sendOkuaEvt(PLANT_MIDI_BUS, toMidiCh0(PLANT_MIDI_CHANNEL_1B), g_testPlantNote, 0, 0);
  g_testPlantNote = g_testProbeCurrentNote;
  sendOkuaEvt(PLANT_MIDI_BUS, toMidiCh0(PLANT_MIDI_CHANNEL_1B), g_testPlantNote, 100, 0);
  testProbeToggleLed();

  Serial.print("[TEST_PROBE] note=");
  Serial.print(g_testPlantNote);
  Serial.print(" led=");
  Serial.println(g_testProbeLedOn ? "ON" : "OFF");

  if (g_testProbeCurrentNote >= (uint8_t)OKUA_TEST_PROBE_NOTE_MAX) {
    g_testProbeCurrentNote = (uint8_t)OKUA_TEST_PROBE_NOTE_START;
  } else {
    g_testProbeCurrentNote = (uint8_t)(g_testProbeCurrentNote + 1);
  }
}
#else
void testProbeInit() {}
#endif

void servicePlantTest() {
#if OKUA_TEST_PROBE_ENABLED
  servicePlantTestProbe();
  return;
#endif
  uint32_t now = millis();
  // Align test-bench plant auto-notes with runtime throttle semantics.
  // SET_THROTTLE updates g_plantThrottleMs (runtime-only), and this cadence
  // must reflect it so 25/50/100 become observable during validation runs.
  uint32_t cadence_ms = (g_plantThrottleMs > 0) ? g_plantThrottleMs : (uint32_t)PLANT_THROTTLE_MS;
  if (cadence_ms == 0) cadence_ms = (uint32_t)TEST_PLANT_EVENT_MS;
  if (now - g_testLastPlantEvtMs < cadence_ms) return;
  g_testLastPlantEvtMs = now;

  int step = (esp_random() % 7) - 3;
  int nextNote = (int)g_testPlantNote + step;
  if (nextNote < PLANT_NOTE_LOW) nextNote = PLANT_NOTE_LOW;
  if (nextNote > PLANT_NOTE_HIGH) nextNote = PLANT_NOTE_HIGH;

  // note off previo
  sendOkuaEvt(PLANT_MIDI_BUS, toMidiCh0(PLANT_MIDI_CHANNEL_1B), g_testPlantNote, 0, 0);

  g_testPlantNote = (uint8_t)nextNote;
  sendOkuaEvt(PLANT_MIDI_BUS, toMidiCh0(PLANT_MIDI_CHANNEL_1B), g_testPlantNote, 90, 0);
  ledShowNote(g_testPlantNote);
}

void serviceFruitTest() {
  uint32_t now = millis();

  if (!g_testFruitActive) {
    if (now - g_testLastFruitCycleMs >= TEST_FRUIT_TOUCH_EVERY_MS) {
      g_testLastFruitCycleMs = now;
      g_testFruitTouchStartMs = now;
      g_testFruitActive = true;
      fruitSendAll(true, 100, EVT_FLAG_TOUCH);
    }
    return;
  }

  if (now - g_testFruitTouchStartMs >= TEST_FRUIT_TOUCH_LEN_MS) {
    g_testFruitActive = false;
    fruitSendAll(false, 0, 0);
  }
}


/*============================================================================================
  ZONA 15 — SETUP
============================================================================================*/

void setup() {
  Serial.begin(115200);
  delay(200);

  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  pinMode(PIN_SIGNAL, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_SIGNAL, ADC_11db);
#if FRUIT_ADC_SCAN_SERIAL || PLANT_DEBUG_ADC_SCAN_UDP
  for (size_t i = 0; i < (sizeof(kFruitAdcScanPins) / sizeof(kFruitAdcScanPins[0])); ++i) {
    const uint8_t pin = kFruitAdcScanPins[i];
    if (pin != PIN_SIGNAL) {
      pinMode(pin, INPUT);
    }
    analogSetPinAttenuation(pin, ADC_11db);
  }
#endif

  ledInit();

  randomSeed(esp_random());

  g_lastEvtCounterResetMs = millis();
  g_bootCounter += 1;
  g_bootMarker4 = (uint8_t)(g_bootCounter & 0x0F);
  g_fruitBootMs = millis();
  g_fruitFilteredV = readVmed3();
  g_fruitPrevV = g_fruitFilteredV;
  g_plantSmoothV = readVmed3();
  g_plantLastRawV = g_plantSmoothV;
  okuaConfigureBuildInfo(kOkuaBuildInfoConfig);
  okuaOtaConfigure(kOkuaOtaConfig);
  okuaOtaBegin();
  testProbeInit();

  connectWiFiBlocking();

  Serial.println();
  Serial.println("==========================================");
  Serial.println("OKUA Node WiFi + UDP v1");
  Serial.print("NODE_LABEL    : "); Serial.println(NODE_LABEL);
  Serial.print("NODE_ID       : "); Serial.println(NODE_ID);
  Serial.print("LOCAL_IP      : "); Serial.println(WiFi.localIP());
  Serial.print("PC_IP         : "); Serial.println(PC_IP);
  Serial.print("OKUA_EVT_PORT : "); Serial.println(OKUA_EVT_PORT);
  Serial.print("OKUA_STAT_PORT: "); Serial.println(OKUA_STAT_PORT);
  Serial.print("OKUA_CMD_PORT : "); Serial.println(OKUA_CMD_PORT);
  Serial.print("OKUA_ACK_PORT : "); Serial.println(OKUA_ACK_PORT);
  Serial.print("UDP_BIND_PORT : "); Serial.println(OKUA_NODE_BIND_PORT);
  Serial.print("MODE          : "); Serial.println((ACTIVE_MODE == MODE_TEST) ? "TEST" : "FIELD");
  Serial.print("SENSOR        : "); Serial.println((ACTIVE_SENSOR == SENSOR_PLANT) ? "PLANT" : "FRUIT");
  Serial.print("BOOT_MARKER4  : "); Serial.println(g_bootMarker4);
  Serial.print("FW_VERSION    : "); Serial.println(okuaBuildVersionStr());
  Serial.print("FW_VERSION_CD : "); Serial.println((unsigned long)okuaBuildVersionCode());
  Serial.print("FW_TARGET     : "); Serial.print(okuaBuildTargetKind()); Serial.print("/"); Serial.println(okuaBuildTargetVariant());
  Serial.print("FW_PROFILE    : "); Serial.println(okuaBuildProfile());
  Serial.print("FW_PROTOCOL   : "); Serial.println(okuaBuildProtocolVersion());
  Serial.print("FW_ARTIFACT   : "); Serial.println(okuaBuildArtifactId());
  Serial.print("FW_SHA256     : "); Serial.println(okuaBuildArtifactSha256());
  Serial.print("OTA_BASE_URL  : "); Serial.println(OKUA_OTA_BASE_URL);
#if OKUA_TEST_PROBE_ENABLED
  Serial.print("TEST_PROBE    : "); Serial.print("enabled gpio=");
  Serial.print(OKUA_TEST_PROBE_LED_PIN);
  Serial.print(" cadence_ms=");
  Serial.print((unsigned long)OKUA_TEST_PROBE_INTERVAL_MS);
  Serial.print(" note_start=");
  Serial.print(OKUA_TEST_PROBE_NOTE_START);
  Serial.print(" note_max=");
  Serial.println(OKUA_TEST_PROBE_NOTE_MAX);
#endif
  Serial.println("==========================================");

  // Emit a startup STAT so runtime can observe fresh uptime/reset metadata quickly.
  sendOkuaStat(g_lastStateFlags);
}


/*============================================================================================
  ZONA 16 — LOOP
============================================================================================*/

void loop() {
  g_loopInitialized = true;
  ensureLink();

  // Parser CMD + ACK + seguridad minima + dispatch minimo (Ticket 13.6).
  serviceControlPlaneIngress();
  servicePendingControlActions();
  okuaOtaService(millis(), WiFi.status() == WL_CONNECTED, g_loopInitialized);

  // Limpiar flags transitorios de reconnect una vez enlazado
  if (WiFi.status() == WL_CONNECTED) {
    g_lastStateFlags &= (uint8_t)~STATF_WIFI_REASSOC;
  }

  if (ACTIVE_MODE == MODE_TEST) {
    if (ACTIVE_SENSOR == SENSOR_PLANT) {
      servicePlantTest();
    } else {
      serviceFruitTest();
    }
  } else {
    if (ACTIVE_SENSOR == SENSOR_PLANT) {
      servicePlantField();
    } else {
      serviceFruitField();
    }
  }

  serviceFruitAdcScan();

  const uint32_t stat_interval_ms = (g_statIntervalMs > 0) ? g_statIntervalMs : (uint32_t)STAT_INTERVAL_MS;
  if (millis() - g_lastStatMs >= stat_interval_ms) {
    sendOkuaStat(g_lastStateFlags);
  }

  delay(2);
}
