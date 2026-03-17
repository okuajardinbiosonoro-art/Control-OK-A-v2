#pragma once

#include <stddef.h>
#include <stdint.h>

// OKUA v1 is defined as little-endian. ESP32 matches this, and this check
// guards accidental cross-builds on incompatible targets.
#if defined(__BYTE_ORDER__) && defined(__ORDER_LITTLE_ENDIAN__)
#if (__BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__)
#error "OKUA protocol requires little-endian target"
#endif
#endif

static const uint16_t OKUA_MAGIC = 0x4B4F;
static const uint8_t OKUA_PROTOCOL_VERSION = 1;

// Control-plane and data-plane ports (F3 contract).
static const uint16_t OKUA_EVT_PORT = 5005;
static const uint16_t OKUA_STAT_PORT = 5006;
static const uint16_t OKUA_CMD_PORT = 5007;
static const uint16_t OKUA_ACK_PORT = 5008;

// Node-side UDP bind for control-plane ingress.
// Binding to CMD keeps local listener semantics explicit.
static const uint16_t OKUA_NODE_BIND_PORT = OKUA_CMD_PORT;

enum OkuaPacketType : uint8_t {
  OKUA_TYPE_EVT = 1,
  OKUA_TYPE_STAT = 2,
  OKUA_TYPE_CMD = 3,
  OKUA_TYPE_ACK = 4,
};

// EVT flags
static const uint8_t EVT_FLAG_TOUCH = 0x01;
static const uint8_t EVT_FLAG_HEARTBEAT = 0x02;
static const uint8_t EVT_FLAG_CALIBRATING = 0x04;

// STAT state_flags
static const uint8_t STATF_CALIBRATING = 0x01;
static const uint8_t STATF_ERROR_ADC = 0x02;
static const uint8_t STATF_WIFI_REASSOC = 0x04;
static const uint8_t STATF_TOUCH_ACTIVE = 0x08;

// CMD ids frozen in spec_control_f3.md
// Handlers are intentionally not implemented in Ticket 13.1.
enum OkuaCmdId : uint8_t {
  OKUA_CMD_PING = 0x01,
  OKUA_CMD_REBOOT_SOFT = 0x02,
  OKUA_CMD_SET_PROFILE = 0x03,
  OKUA_CMD_SET_THROTTLE = 0x04,
  OKUA_CMD_SET_STAT_RATE = 0x05,
  OKUA_CMD_SET_DEBUG = 0x06,
  OKUA_CMD_REQUEST_STAT_NOW = 0x07,
};

enum OkuaAckStage : uint8_t {
  OKUA_ACK_STAGE_ACCEPTED = 1,
  OKUA_ACK_STAGE_EXECUTED = 2,
  OKUA_ACK_STAGE_REJECTED = 3,
};

enum OkuaStatusCode : uint8_t {
  OKUA_STATUS_OK = 0x00,
  OKUA_STATUS_RESERVED = 0x01,
  OKUA_STATUS_INVALID_AUTH = 0x02,
  OKUA_STATUS_INVALID_ARG = 0x03,
  OKUA_STATUS_UNSUPPORTED_CMD = 0x04,
  OKUA_STATUS_RATE_LIMITED = 0x05,
  OKUA_STATUS_REPLAY_REJECTED = 0x06,
  OKUA_STATUS_BUSY = 0x07,
  OKUA_STATUS_INTERNAL_ERROR = 0x08,
};

enum OkuaErrDetail : uint16_t {
  OKUA_ERR_NONE = 0x0000,
  OKUA_ERR_ARG0_OUT_OF_RANGE = 0x0001,
  OKUA_ERR_ARG1_OUT_OF_RANGE = 0x0002,
  OKUA_ERR_PROFILE_ID_UNKNOWN = 0x0003,
  OKUA_ERR_THROTTLE_INVALID = 0x0004,
  OKUA_ERR_STAT_RATE_INVALID = 0x0005,
  OKUA_ERR_DEBUG_LEVEL_INVALID = 0x0006,
  OKUA_ERR_BROADCAST_NOT_ALLOWED = 0x0007,
  OKUA_ERR_NONCE_REUSED = 0x0008,
  OKUA_ERR_NONCE_OUT_OF_WINDOW = 0x0009,
  OKUA_ERR_AUTH_TAG_MISMATCH = 0x000A,
  OKUA_ERR_RATE_LIMIT_EXCEEDED = 0x000B,
  OKUA_ERR_NODE_STATE_BLOCKED = 0x000C,
  OKUA_ERR_CMD_IN_PROGRESS = 0x000D,
  OKUA_ERR_MALFORMED_PACKET = 0x000E,
};

struct OkuaHdr {
  uint16_t magic;
  uint8_t ver;
  uint8_t type;
  uint16_t node_id;
  uint16_t seq;
} __attribute__((packed));

struct OkuaEvtPacket {
  OkuaHdr hdr;
  uint8_t midi_bus;
  uint8_t midi_ch;
  uint8_t note;
  uint8_t vel;
  uint32_t ts_ms;
  int8_t rssi_dbm;
  uint8_t flags;
  uint8_t rsv[2];
} __attribute__((packed));

struct OkuaStatPacket {
  OkuaHdr hdr;
  uint32_t uptime_s;
  int8_t rssi_dbm;
  uint8_t state_flags;
  uint16_t pps_x10;
  uint16_t vbat_mv;
  uint32_t free_heap;
  uint8_t fw_major;
  uint8_t fw_minor;
  uint8_t reset_reason;
  uint8_t rsv[3];
} __attribute__((packed));

// OKUA_CMD = 28 bytes total (8-byte header + 20-byte payload)
struct OkuaCmdPacket {
  OkuaHdr hdr;
  uint8_t cmd_id;
  uint8_t cmd_flags;
  uint16_t arg0;
  uint16_t arg1;
  uint64_t nonce;
  uint8_t rsv0[2];
  uint32_t auth_tag32;
} __attribute__((packed));

// OKUA_ACK = 28 bytes total (8-byte header + 20-byte payload)
struct OkuaAckPacket {
  OkuaHdr hdr;
  uint8_t cmd_id_echo;
  uint8_t ack_stage;
  uint8_t status_code;
  uint8_t ack_flags;
  uint16_t err_detail;
  uint16_t retry_after_ms;
  uint64_t nonce_echo;
  uint32_t auth_tag32;
} __attribute__((packed));

static const size_t OKUA_HDR_SIZE = 8;
static const size_t OKUA_EVT_SIZE = 20;
static const size_t OKUA_STAT_SIZE = 28;
static const size_t OKUA_CMD_SIZE = 28;
static const size_t OKUA_ACK_SIZE = 28;

static_assert(sizeof(OkuaHdr) == OKUA_HDR_SIZE, "OkuaHdr must be 8 bytes");
static_assert(sizeof(OkuaEvtPacket) == OKUA_EVT_SIZE, "OkuaEvtPacket must be 20 bytes");
static_assert(sizeof(OkuaStatPacket) == OKUA_STAT_SIZE, "OkuaStatPacket must be 28 bytes");
static_assert(sizeof(OkuaCmdPacket) == OKUA_CMD_SIZE, "OkuaCmdPacket must be 28 bytes");
static_assert(sizeof(OkuaAckPacket) == OKUA_ACK_SIZE, "OkuaAckPacket must be 28 bytes");

static inline bool okuaIsCmdPacketSizeValid(size_t packet_len) {
  return packet_len == OKUA_CMD_SIZE;
}

static inline bool okuaIsAckPacketSizeValid(size_t packet_len) {
  return packet_len == OKUA_ACK_SIZE;
}

static inline void okuaInitAckSkeleton(
    OkuaAckPacket* ack,
    uint16_t responder_node_id,
    uint16_t cmd_seq,
    uint8_t cmd_id,
    uint64_t nonce_echo) {
  if (ack == nullptr) {
    return;
  }
  *ack = {};
  ack->hdr.magic = OKUA_MAGIC;
  ack->hdr.ver = OKUA_PROTOCOL_VERSION;
  ack->hdr.type = OKUA_TYPE_ACK;
  ack->hdr.node_id = responder_node_id;
  ack->hdr.seq = cmd_seq;
  ack->cmd_id_echo = cmd_id;
  ack->ack_stage = OKUA_ACK_STAGE_REJECTED;
  ack->status_code = OKUA_STATUS_UNSUPPORTED_CMD;
  ack->ack_flags = 0;
  ack->err_detail = OKUA_ERR_NONE;
  ack->retry_after_ms = 0;
  ack->nonce_echo = nonce_echo;
  ack->auth_tag32 = 0;
}
