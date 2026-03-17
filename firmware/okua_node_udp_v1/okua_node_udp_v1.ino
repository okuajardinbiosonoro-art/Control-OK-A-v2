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
#define ACTIVE_MODE MODE_TEST

//-------------------- Tipo de nodo ----------------------------------------------------------
#define SENSOR_PLANT 1
#define SENSOR_FRUIT 2
#define ACTIVE_SENSOR SENSOR_PLANT

//-------------------- LEDs ------------------------------------------------------------------
#define LED_DISABLED 0
#define LED_SIMPLE   1
#define LED_PROFILE  LED_DISABLED

//-------------------- Variante de fruta -----------------------------------------------------
#define FRUIT_VARIANT_V1 1
#define FRUIT_VARIANT_V2 2
#define ACTIVE_FRUIT_VARIANT FRUIT_VARIANT_V2


/*============================================================================================
  ZONA 2 — IDENTIDAD DEL NODO / RED
============================================================================================*/

// Etiqueta visible para debug
#define NODE_LABEL "EB4"

// node_id segun la regla del proyecto: caja*10 + posicion(B=1,C=2,D=3,E=4,F=5)
// Ejemplo EB1 = 11, EC1 = 12, EF1 = 15
#define NODE_ID 16

// WiFi (safe defaults for versioned repository).
// Local overrides can be provided in a non-tracked file:
//   firmware/okua_node_udp_v1/okua_node_secrets.h
#if defined(__has_include)
#if __has_include("okua_node_secrets.h")
#include "okua_node_secrets.h"
#endif
#endif

#ifndef WIFI_SSID
#define WIFI_SSID    "OKUA_CORE"
#endif

#ifndef WIFI_PASS
#define WIFI_PASS    "CHANGE_ME"
#endif

#define WIFI_CHANNEL 13

// PC destino para EVT/STAT en la LAN OKUA
IPAddress PC_IP(192, 168, 88, 254);

// Firmware version
#define FW_MAJOR 1
#define FW_MINOR 0


/*============================================================================================
  ZONA 3 — HARDWARE
============================================================================================*/

#define PIN_SIGNAL 32

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

// EJEMPLO EB1:
// activa canales 1, 3, 4 y 5
// Si quieres EC1, deja solo el canal 2.
static const MidiRoute FRUIT_ROUTES[] = {
  {0, 1, 57},
  {0, 3, 57},
  {0, 4, 57},
  {0, 5, 57},
};

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
#define TEST_PLANT_EVENT_MS       220
#define TEST_FRUIT_TOUCH_EVERY_MS 2000
#define TEST_FRUIT_TOUCH_LEN_MS    450

// Planta
#define PLANT_THROTTLE_MS         100
#define PLANT_AUTOCAL_MS        10000
#define PLANT_NOISE_FLOOR       0.008f
#define PLANT_SMOOTH_A          0.10f
#define PLANT_BASE_A            0.001f
#define PLANT_TOUCH_GAIN        7.0f
#define PLANT_MAX_JUMP_ST       6

// Fruta
#define FRUIT_FILTER_ALPHA      0.10f
#define FRUIT_VAR_ALPHA         0.05f
#define FRUIT_BASE_A            0.001f
#define FRUIT_BASE_CLAMP_MIN    0.05f
#define FRUIT_AUTOCAL_FAST_MS   1500
#define FRUIT_AUTOCAL_REFINE_MS 8000
#define FRUIT_HARD_TIMEOUT_MS  60000
#define FRUIT_RECOVERY_MS        250


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

#include "okua_control_plane.h"


/*============================================================================================
  ZONA 7 — CONTROL-PLANE (TICKET 13.3)
============================================================================================*/

// Todos los modelos binarios, enums y tamanos de protocolo quedaron centralizados en:
//   - okua_control_plane.h
//
// En este ticket se implementa parser RX + emision inicial de ACK.
// Aun NO se implementan auth, nonce validation, anti-replay/rate-limit ni handlers.


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

float readVmed3() {
  float a = readV();
  float b = readV();
  float c = readV();
  if ((a <= b && b <= c) || (c <= b && b <= a)) return b;
  if ((b <= a && a <= c) || (c <= a && a <= b)) return a;
  return c;
}


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
uint32_t g_evtCountSinceLastStat = 0;
uint32_t g_lastEvtCounterResetMs = 0;

uint8_t g_lastStateFlags = 0;

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

// Last parsed frame/result kept for future ACK pipeline (Ticket 13.3).
CmdParseResult g_lastCmdParseResult = CMD_PARSE_NONE;
ParsedCmdFrame g_lastParsedCmdFrame = {};

static inline bool okuaIsKnownCmdId(uint8_t cmd_id) {
  switch (cmd_id) {
    case OKUA_CMD_PING:
    case OKUA_CMD_REBOOT_SOFT:
    case OKUA_CMD_SET_PROFILE:
    case OKUA_CMD_SET_THROTTLE:
    case OKUA_CMD_SET_STAT_RATE:
    case OKUA_CMD_SET_DEBUG:
    case OKUA_CMD_REQUEST_STAT_NOW:
      return true;
    default:
      return false;
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

  // Ticket 13.3: no security yet.
  ack->auth_tag32 = 0;
  ack->retry_after_ms = 0;

  switch (frame.result) {
    case CMD_PARSE_OK_UNICAST:
      ack->ack_stage = OKUA_ACK_STAGE_ACCEPTED;
      ack->status_code = OKUA_STATUS_OK;
      ack->err_detail = OKUA_ERR_NONE;
      break;

    case CMD_PARSE_OK_BROADCAST:
      ack->ack_stage = OKUA_ACK_STAGE_ACCEPTED;
      ack->status_code = OKUA_STATUS_OK;
      ack->err_detail = OKUA_ERR_NONE;
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
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);
  esp_wifi_set_ps(WIFI_PS_NONE);

  if (WiFi.status() == WL_CONNECTED) {
    if (!g_udpBegun) openUdpSocket();
    return;
  }

  WiFi.begin(WIFI_SSID, WIFI_PASS);

  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    if (millis() - t0 >= WIFI_CONNECT_TIMEOUT_MS) {
      WiFi.disconnect(true, true);
      delay(WIFI_RETRY_DELAY_MS);
      WiFi.begin(WIFI_SSID, WIFI_PASS);
      t0 = millis();
    }
  }

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

// Control-plane ingress for Ticket 13.3:
// parse + structural validation + ACK policy/correlation only.
// No command execution yet.
void serviceControlPlaneIngress() {
  ParsedCmdFrame frame;
  CmdParseResult result = parseIncomingCmdFrame(&frame);
  if (result == CMD_PARSE_NONE) return;

  g_lastParsedCmdFrame = frame;
  g_lastCmdParseResult = result;

  if (!shouldEmitAckForParseResult(result)) return;

  OkuaAckPacket ack = {};
  fillAckForParseResult(frame, &ack);

  // ACK destination for F3 is source_ip + fixed ACK port (not source port).
  sendOkuaAckTo(frame.src_ip, ack);
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
  p.state_flags    = state_flags;
  p.pps_x10        = (uint16_t)pps_x10_u32;
  p.vbat_mv        = 0;
  p.free_heap      = ESP.getFreeHeap();
  p.fw_major       = FW_MAJOR;
  p.fw_minor       = FW_MINOR;
  p.reset_reason   = (uint8_t)esp_reset_reason();
  p.rsv[0] = p.rsv[1] = p.rsv[2] = 0;

  bool ok = sendUdpRaw((const uint8_t*)&p, sizeof(p), OKUA_STAT_PORT);
  if (ok) {
    g_lastStatMs = nowMs;
    g_lastEvtCounterResetMs = nowMs;
    g_evtCountSinceLastStat = 0;
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

uint32_t g_plantLastAnyActivity = 0;
uint32_t g_plantLastSentMs = 0;

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
  if (!force && (now - g_plantLastSentMs < PLANT_THROTTLE_MS)) return false;
  bool ok = sendOkuaEvt(PLANT_MIDI_BUS, toMidiCh0(PLANT_MIDI_CHANNEL_1B), note, vel, 0);
  if (ok) {
    g_plantLastSentMs = now;
    g_plantNoteActive = true;
    g_plantLastPlayedNote = note;
    ledShowNote(note);
  }
  return ok;
}

bool plantSendNoteOff(uint8_t note) {
  bool ok = sendOkuaEvt(PLANT_MIDI_BUS, toMidiCh0(PLANT_MIDI_CHANNEL_1B), note, 0, 0);
  if (ok) {
    g_plantNoteActive = false;
    ledOff();
  }
  return ok;
}

void servicePlantField() {
  float vRaw = readVmed3();

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
    return;
  } else {
    g_lastStateFlags &= (uint8_t)~STATF_CALIBRATING;
  }

  g_plantBaselineV += PLANT_BASE_A * (vRaw - g_plantBaselineV);
  g_plantSmoothV   += PLANT_SMOOTH_A * (vRaw - g_plantSmoothV);

  float dv = fabsf(vRaw - g_plantLastRawV);
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
        if (nextNote != g_plantCurrentNote) {
          if (g_plantNoteActive) plantSendNoteOff(g_plantCurrentNote);
          g_plantCurrentNote = nextNote;
          plantSendNoteOn(g_plantCurrentNote, plantMapVel(dv * PLANT_TOUCH_GAIN), true);
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
  0.100f,
  0.30f, 0.25f,
  40, 80, 120,
  800, 12000,
  0.45f
};

const FruitDetectParams& FD = (ACTIVE_FRUIT_VARIANT == FRUIT_VARIANT_V1) ? FRUIT_V1 : FRUIT_V2;

bool  g_fruitCalFastDone = false;
bool  g_fruitCalRefineDone = false;
unsigned long g_fruitBootMs = 0;
unsigned long g_fruitRefineStartMs = 0;

float g_fruitBaselineV = 0.0f;
float g_fruitFilteredV = 0.0f;
float g_fruitPrevV = 0.0f;
float g_fruitVarDv = 0.0f;
float g_fruitSigma = 0.0f;

bool  g_fruitContactActive = false;
int8_t g_fruitTouchSign = +1;
unsigned long g_fruitContactStartMs = 0;
unsigned long g_fruitLastReleaseMs = 0;
unsigned long g_fruitUpHoldStartMs = 0;
unsigned long g_fruitDownHoldStartMs = 0;
unsigned long g_fruitLastEnergyOkMs = 0;
unsigned long g_fruitRecoveryUntilMs = 0;
unsigned long g_fruitLastKeepaliveMs = 0;

void fruitSendAll(bool noteOn, uint8_t vel, uint8_t flags) {
  for (uint8_t i = 0; i < FRUIT_ROUTE_COUNT; ++i) {
    const MidiRoute& r = FRUIT_ROUTES[i];
    sendOkuaEvt(r.midi_bus, toMidiCh0(r.midi_channel_1b), r.note, noteOn ? vel : 0, flags);
  }

  if (noteOn && FRUIT_ROUTE_COUNT > 0) {
    ledShowNote(FRUIT_ROUTES[0].note);
  } else {
    ledOff();
  }
}

void calibrateFruit2Phases(float vNow) {
  const int WIN = 121;
  static float win[WIN];
  static int wi = 0;
  static int filled = 0;

  unsigned long now = millis();

  win[wi++] = vNow;
  if (wi >= WIN) wi = 0;
  if (filled < WIN) filled++;

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

      g_fruitCalFastDone = true;
      g_fruitRefineStartMs = now;
    }
    return;
  }

  if (!g_fruitCalRefineDone) {
    float dv = vNow - g_fruitBaselineV;
    if (fabsf(dv) < 0.12f) {
      g_fruitBaselineV += 0.01f * dv;
      if (g_fruitBaselineV < FRUIT_BASE_CLAMP_MIN) g_fruitBaselineV = FRUIT_BASE_CLAMP_MIN;
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

void serviceFruitField() {
  unsigned long now = millis();

  float vRaw = readVmed3();
  g_fruitFilteredV = FRUIT_FILTER_ALPHA * vRaw + (1.0f - FRUIT_FILTER_ALPHA) * g_fruitFilteredV;

  if (!g_fruitCalFastDone || !g_fruitCalRefineDone) {
    calibrateFruit2Phases(g_fruitFilteredV);
    g_lastStateFlags |= STATF_CALIBRATING;
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

  int8_t dvSign = (dv >= 0.0f) ? +1 : -1;
  int8_t signUse = g_fruitContactActive ? g_fruitTouchSign : dvSign;

  float dv_proj = dv * (float)signUse;
  float slope_proj = dv_dt * (float)signUse;

  if (!g_fruitContactActive && now >= g_fruitRecoveryUntilMs) {
    g_fruitVarDv = (1.0f - 0.05f) * g_fruitVarDv + 0.05f * (dv * dv);
    g_fruitSigma = sqrtf(fmaxf(g_fruitVarDv, 0.0f));
  }

  float th_rel_up = 0.0f;
  if (g_fruitBaselineV >= FD.v_rel_min) th_rel_up = FD.rel_up * g_fruitBaselineV;

  float th_up   = fmaxf(FD.abs_min_up,   fmaxf(th_rel_up, FD.k_sigma_up * g_fruitSigma));
  float th_down = fmaxf(FD.abs_min_down, fmaxf(FD.rel_down_f * th_up, FD.k_sigma_down * g_fruitSigma));

  bool ampStrong = (dv_proj >= FD.abs_strong_up);
  bool ampGate   = (dv_proj >= th_up);
  bool slopeGate = (slope_proj >= FD.slope_min_strong);
  bool enterCand = ampStrong || (ampGate && slopeGate);

  if (enterCand) {
    if (g_fruitUpHoldStartMs == 0) g_fruitUpHoldStartMs = now;
  } else {
    g_fruitUpHoldStartMs = 0;
  }

  bool refractory = (now - g_fruitLastReleaseMs < FD.refract_ms);
  bool enterNow = (!refractory && !g_fruitContactActive &&
                   g_fruitUpHoldStartMs &&
                   (now - g_fruitUpHoldStartMs >= FD.on_hold_ms));

  if (enterNow) {
    g_fruitContactActive = true;
    g_fruitTouchSign = dvSign;
    g_fruitContactStartMs = now;
    g_fruitLastEnergyOkMs = now;
    g_fruitDownHoldStartMs = 0;
    g_fruitLastKeepaliveMs = 0;

    fruitSendAll(true, 100, EVT_FLAG_TOUCH);
  }

  if (g_fruitContactActive) {
    g_lastStateFlags |= STATF_TOUCH_ACTIVE;
  } else {
    g_lastStateFlags &= (uint8_t)~STATF_TOUCH_ACTIVE;
  }

  if (g_fruitContactActive) {
    if (dv_proj >= FD.energy_frac * th_up) {
      g_fruitLastEnergyOkMs = now;
    }

#if FRUIT_KEEPALIVE_ENABLE
    if ((now - g_fruitLastKeepaliveMs) >= FRUIT_KEEPALIVE_MS) {
      g_fruitLastKeepaliveMs = now;
      fruitSendAll(true, 60, EVT_FLAG_TOUCH);
    }
#endif
  }

  bool levelLow = (dv_proj <= th_down);
  if (levelLow) {
    if (g_fruitDownHoldStartMs == 0) g_fruitDownHoldStartMs = now;
  } else {
    g_fruitDownHoldStartMs = 0;
  }

  bool releaseLevel    = (g_fruitDownHoldStartMs && (now - g_fruitDownHoldStartMs >= FD.off_hold_ms));
  bool releaseNoEnergy = (now - g_fruitLastEnergyOkMs >= FD.noenergy_ms);
  bool releaseTimeout  = (now - g_fruitContactStartMs >= FD.contact_max_ms);
  bool releaseDeriv    = (slope_proj <= -FD.slope_release) && (dv_proj <= 0.8f * th_up);

  bool exitNow = g_fruitContactActive && (releaseLevel || releaseNoEnergy || releaseTimeout || releaseDeriv);

  if (exitNow) {
    g_fruitContactActive = false;
    g_fruitLastReleaseMs = now;
    g_fruitUpHoldStartMs = 0;
    g_fruitDownHoldStartMs = 0;
    g_fruitRecoveryUntilMs = now + FRUIT_RECOVERY_MS;

    fruitSendAll(false, 0, 0);
  }

  if (!g_fruitContactActive && now >= g_fruitRecoveryUntilMs) {
    g_fruitBaselineV += FRUIT_BASE_A * (g_fruitFilteredV - g_fruitBaselineV);
    if (g_fruitBaselineV < FRUIT_BASE_CLAMP_MIN) g_fruitBaselineV = FRUIT_BASE_CLAMP_MIN;
  }
}


/*============================================================================================
  ZONA 14 — MODO PRUEBA
============================================================================================*/

uint32_t g_testLastPlantEvtMs = 0;
uint32_t g_testLastFruitCycleMs = 0;
bool g_testFruitActive = false;
uint32_t g_testFruitTouchStartMs = 0;
uint8_t g_testPlantNote = 60;

void servicePlantTest() {
  uint32_t now = millis();
  if (now - g_testLastPlantEvtMs < TEST_PLANT_EVENT_MS) return;
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

  ledInit();

  randomSeed(esp_random());

  g_lastEvtCounterResetMs = millis();
  g_fruitBootMs = millis();
  g_fruitFilteredV = readVmed3();
  g_fruitPrevV = g_fruitFilteredV;
  g_plantSmoothV = readVmed3();
  g_plantLastRawV = g_plantSmoothV;

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
  Serial.println("==========================================");
}


/*============================================================================================
  ZONA 16 — LOOP
============================================================================================*/

void loop() {
  ensureLink();

  // Parser CMD + ACK correlacionado basico (Ticket 13.3, sin handlers).
  serviceControlPlaneIngress();

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

  if (millis() - g_lastStatMs >= STAT_INTERVAL_MS) {
    sendOkuaStat(g_lastStateFlags);
  }

  delay(2);
}
