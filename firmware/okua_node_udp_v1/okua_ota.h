#pragma once

#include <stdint.h>

enum OkuaOtaRuntimeStateCode : uint8_t {
  OKUA_OTA_STATE_IDLE = 0,
  OKUA_OTA_STATE_TRIGGERED = 1,
  OKUA_OTA_STATE_FETCHING_MANIFEST = 2,
  OKUA_OTA_STATE_VALIDATING_MANIFEST = 3,
  OKUA_OTA_STATE_DOWNLOADING = 4,
  OKUA_OTA_STATE_READY_REBOOT = 5,
  OKUA_OTA_STATE_BOOT_VALIDATING = 6,
  OKUA_OTA_STATE_BOOT_CONFIRMED = 7,
  OKUA_OTA_STATE_ERROR = 255,
};

enum OkuaOtaRuntimeErrorCode : uint8_t {
  OKUA_OTA_ERROR_NONE = 0,
  OKUA_OTA_ERROR_INVALID_TRIGGER = 1,
  OKUA_OTA_ERROR_MANIFEST_HTTP = 2,
  OKUA_OTA_ERROR_MANIFEST_PARSE = 3,
  OKUA_OTA_ERROR_MANIFEST_INCOMPATIBLE = 4,
  OKUA_OTA_ERROR_VERSION_REJECTED = 5,
  OKUA_OTA_ERROR_ALREADY_CURRENT = 6,
  OKUA_OTA_ERROR_DOWNLOAD_HTTP = 7,
  OKUA_OTA_ERROR_DOWNLOAD_SIZE = 8,
  OKUA_OTA_ERROR_DOWNLOAD_HASH = 9,
  OKUA_OTA_ERROR_OTA_BEGIN = 10,
  OKUA_OTA_ERROR_OTA_WRITE = 11,
  OKUA_OTA_ERROR_OTA_FINALIZE = 12,
  OKUA_OTA_ERROR_BOOT_WIFI_TIMEOUT = 13,
  OKUA_OTA_ERROR_BOOT_STAT_TIMEOUT = 14,
  OKUA_OTA_ERROR_BOOT_IDENTITY_MISMATCH = 15,
  OKUA_OTA_ERROR_BOOT_VALIDATE = 16,
  OKUA_OTA_ERROR_NVS = 17,
};

enum OkuaOtaRuntimeFlagBits : uint8_t {
  OKUA_OTA_FLAG_CHECK_PENDING = 0x01,
  OKUA_OTA_FLAG_PENDING_REBOOT = 0x02,
  OKUA_OTA_FLAG_PENDING_VERIFY = 0x04,
  OKUA_OTA_FLAG_HEALTH_CONFIRMED = 0x08,
};

struct OkuaOtaConfig {
  const char* base_url;
  uint32_t health_confirm_ms;
  uint32_t http_timeout_ms;
};

struct OkuaOtaTelemetry {
  uint8_t state_code;
  uint8_t error_code;
  uint8_t flags;
  const char* state_key;
  const char* error_key;
};

void okuaOtaConfigure(const OkuaOtaConfig& config);
void okuaOtaBegin();
bool okuaOtaQueueCheck(uint32_t rollout_token);
void okuaOtaService(uint32_t now_ms, bool wifi_connected, bool loop_ready);
void okuaOtaNotifyWiFiConnected(uint32_t now_ms);
void okuaOtaNotifyStatSent();
bool okuaOtaShouldAbortWiFiConnect(uint32_t now_ms);
void okuaOtaHandleWiFiConnectTimeout();
bool okuaOtaConsumePendingReboot();
OkuaOtaTelemetry okuaOtaGetTelemetry();
const char* okuaOtaStateKey();
const char* okuaOtaErrorKey();
const char* okuaOtaLastDetail();
