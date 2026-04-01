#include "okua_ota.h"

#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClient.h>

#include <esp_ota_ops.h>

#include <mbedtls/md.h>

#include "cJSON.h"

#include "okua_build_info.h"

namespace {

static const char* kOtaPrefsNs = "okua_ota";
static const char* kPrefRollout = "rollout";
static const char* kPrefArtifact = "artifact";
static const char* kPrefSha256 = "sha256";
static const char* kPrefVerCode = "vercode";
static const char* kPrefTarget = "target";
static const char* kPrefVariant = "variant";
static const char* kPrefProfile = "profile";
static const char* kDefaultBaseUrl = "http://192.168.88.254:8080";
static const uint32_t kDefaultHealthConfirmMs = 45000UL;
static const uint32_t kDefaultHttpTimeoutMs = 8000UL;

struct OkuaExpectedArtifact {
  char rollout_id[24];
  char artifact_id[72];
  char sha256[65];
  uint32_t version_code;
  char target_kind[24];
  char target_variant[32];
  char build_profile[24];
  bool valid;
};

struct OkuaOtaManifest {
  char rollout_id[48];
  char firmware_family[40];
  char target_kind[24];
  char target_variant[32];
  char compatible_hw[24];
  char build_profile[24];
  char protocol_version[24];
  char version[32];
  uint32_t version_code;
  char artifact_id[72];
  char sha256[65];
  uint32_t file_size;
  char download_url[240];
  char changelog_short[128];
  char rollout_channel[24];
  char published_at_utc[40];
  bool allow_auto_rollback;
  bool reboot_required;
};

OkuaOtaConfig g_config = {kDefaultBaseUrl, kDefaultHealthConfirmMs, kDefaultHttpTimeoutMs};
uint8_t g_state = OKUA_OTA_STATE_IDLE;
uint8_t g_error = OKUA_OTA_ERROR_NONE;
uint8_t g_flags = 0;
uint32_t g_pendingRolloutToken = 0;
bool g_configured = false;
bool g_statSentSinceBoot = false;
bool g_loopReady = false;
bool g_pendingRebootRequest = false;
uint32_t g_bootValidationStartMs = 0;
char g_lastDetail[160] = "";
OkuaExpectedArtifact g_expectedArtifact = {};

void copyString(char* dst, size_t dst_len, const char* src) {
  if (dst == nullptr || dst_len == 0) return;
  size_t i = 0;
  const char* resolved = (src != nullptr) ? src : "";
  for (; i + 1 < dst_len && resolved[i] != '\0'; ++i) {
    dst[i] = resolved[i];
  }
  dst[i] = '\0';
}

bool strEqIgnoreCase(const char* a, const char* b) {
  if (a == nullptr || b == nullptr) return false;
  while (*a != '\0' && *b != '\0') {
    char ca = *a++;
    char cb = *b++;
    if (ca >= 'A' && ca <= 'Z') ca = (char)(ca - 'A' + 'a');
    if (cb >= 'A' && cb <= 'Z') cb = (char)(cb - 'A' + 'a');
    if (ca != cb) return false;
  }
  return *a == '\0' && *b == '\0';
}

bool isHexSha256(const char* value) {
  if (value == nullptr) return false;
  size_t len = 0;
  while (value[len] != '\0') {
    const char c = value[len];
    const bool ok =
        (c >= '0' && c <= '9') ||
        (c >= 'a' && c <= 'f') ||
        (c >= 'A' && c <= 'F');
    if (!ok) return false;
    ++len;
  }
  return len == 64;
}

void setState(uint8_t state_code, uint8_t error_code, const char* detail) {
  g_state = state_code;
  g_error = error_code;
  copyString(g_lastDetail, sizeof(g_lastDetail), detail);
  if (state_code == OKUA_OTA_STATE_IDLE) {
    g_flags &= (uint8_t)~OKUA_OTA_FLAG_CHECK_PENDING;
  }
}

const char* stateKey(uint8_t state_code) {
  switch (state_code) {
    case OKUA_OTA_STATE_IDLE:
      return "idle";
    case OKUA_OTA_STATE_TRIGGERED:
      return "triggered";
    case OKUA_OTA_STATE_FETCHING_MANIFEST:
      return "fetching_manifest";
    case OKUA_OTA_STATE_VALIDATING_MANIFEST:
      return "validating_manifest";
    case OKUA_OTA_STATE_DOWNLOADING:
      return "downloading";
    case OKUA_OTA_STATE_READY_REBOOT:
      return "ready_reboot";
    case OKUA_OTA_STATE_BOOT_VALIDATING:
      return "boot_validating";
    case OKUA_OTA_STATE_BOOT_CONFIRMED:
      return "boot_confirmed";
    case OKUA_OTA_STATE_ERROR:
      return "error";
    default:
      return "unknown";
  }
}

const char* errorKey(uint8_t error_code) {
  switch (error_code) {
    case OKUA_OTA_ERROR_NONE:
      return "none";
    case OKUA_OTA_ERROR_INVALID_TRIGGER:
      return "invalid_trigger";
    case OKUA_OTA_ERROR_MANIFEST_HTTP:
      return "manifest_http";
    case OKUA_OTA_ERROR_MANIFEST_PARSE:
      return "manifest_parse";
    case OKUA_OTA_ERROR_MANIFEST_INCOMPATIBLE:
      return "manifest_incompatible";
    case OKUA_OTA_ERROR_VERSION_REJECTED:
      return "version_rejected";
    case OKUA_OTA_ERROR_ALREADY_CURRENT:
      return "already_current";
    case OKUA_OTA_ERROR_DOWNLOAD_HTTP:
      return "download_http";
    case OKUA_OTA_ERROR_DOWNLOAD_SIZE:
      return "download_size";
    case OKUA_OTA_ERROR_DOWNLOAD_HASH:
      return "download_hash";
    case OKUA_OTA_ERROR_OTA_BEGIN:
      return "ota_begin";
    case OKUA_OTA_ERROR_OTA_WRITE:
      return "ota_write";
    case OKUA_OTA_ERROR_OTA_FINALIZE:
      return "ota_finalize";
    case OKUA_OTA_ERROR_BOOT_WIFI_TIMEOUT:
      return "boot_wifi_timeout";
    case OKUA_OTA_ERROR_BOOT_STAT_TIMEOUT:
      return "boot_stat_timeout";
    case OKUA_OTA_ERROR_BOOT_IDENTITY_MISMATCH:
      return "boot_identity_mismatch";
    case OKUA_OTA_ERROR_BOOT_VALIDATE:
      return "boot_validate";
    case OKUA_OTA_ERROR_NVS:
      return "nvs_error";
    default:
      return "unknown_error";
  }
}

bool withPrefsRead(Preferences* prefs) {
  return prefs != nullptr && prefs->begin(kOtaPrefsNs, true);
}

bool withPrefsWrite(Preferences* prefs) {
  return prefs != nullptr && prefs->begin(kOtaPrefsNs, false);
}

bool loadExpectedArtifact(OkuaExpectedArtifact* out_expected) {
  if (out_expected == nullptr) return false;
  *out_expected = {};
  Preferences prefs;
  if (!withPrefsRead(&prefs)) return false;
  copyString(out_expected->rollout_id, sizeof(out_expected->rollout_id), prefs.getString(kPrefRollout, "").c_str());
  copyString(out_expected->artifact_id, sizeof(out_expected->artifact_id), prefs.getString(kPrefArtifact, "").c_str());
  copyString(out_expected->sha256, sizeof(out_expected->sha256), prefs.getString(kPrefSha256, "").c_str());
  out_expected->version_code = prefs.getUInt(kPrefVerCode, 0);
  copyString(out_expected->target_kind, sizeof(out_expected->target_kind), prefs.getString(kPrefTarget, "").c_str());
  copyString(out_expected->target_variant, sizeof(out_expected->target_variant), prefs.getString(kPrefVariant, "").c_str());
  copyString(out_expected->build_profile, sizeof(out_expected->build_profile), prefs.getString(kPrefProfile, "").c_str());
  prefs.end();
  out_expected->valid = out_expected->version_code > 0;
  return out_expected->valid;
}

bool storeExpectedArtifact(const OkuaOtaManifest& manifest) {
  Preferences prefs;
  if (!withPrefsWrite(&prefs)) return false;
  const bool ok =
      prefs.putString(kPrefRollout, manifest.rollout_id) > 0 &&
      prefs.putString(kPrefArtifact, manifest.artifact_id) > 0 &&
      prefs.putString(kPrefSha256, manifest.sha256) > 0 &&
      prefs.putUInt(kPrefVerCode, manifest.version_code) > 0 &&
      prefs.putString(kPrefTarget, manifest.target_kind) > 0 &&
      prefs.putString(kPrefVariant, manifest.target_variant) > 0 &&
      prefs.putString(kPrefProfile, manifest.build_profile) > 0;
  prefs.end();
  return ok;
}

void clearExpectedArtifact() {
  Preferences prefs;
  if (!withPrefsWrite(&prefs)) return;
  prefs.remove(kPrefRollout);
  prefs.remove(kPrefArtifact);
  prefs.remove(kPrefSha256);
  prefs.remove(kPrefVerCode);
  prefs.remove(kPrefTarget);
  prefs.remove(kPrefVariant);
  prefs.remove(kPrefProfile);
  prefs.end();
  g_expectedArtifact = {};
}

bool loadStringField(cJSON* root, const char* key, char* dst, size_t dst_len) {
  cJSON* item = cJSON_GetObjectItemCaseSensitive(root, key);
  if (!cJSON_IsString(item) || item->valuestring == nullptr || item->valuestring[0] == '\0') {
    return false;
  }
  copyString(dst, dst_len, item->valuestring);
  return true;
}

bool loadUIntField(cJSON* root, const char* key, uint32_t* out_value) {
  if (out_value == nullptr) return false;
  cJSON* item = cJSON_GetObjectItemCaseSensitive(root, key);
  if (item == nullptr || !cJSON_IsNumber(item) || item->valuedouble < 0) {
    return false;
  }
  *out_value = (uint32_t)item->valuedouble;
  return true;
}

bool manifestContainsCompatibleHw(cJSON* root, const char* expected_hw, char* stored_hw, size_t stored_hw_len) {
  cJSON* item = cJSON_GetObjectItemCaseSensitive(root, "compatible_hw");
  if (!cJSON_IsArray(item)) return false;
  cJSON* child = nullptr;
  cJSON_ArrayForEach(child, item) {
    if (!cJSON_IsString(child) || child->valuestring == nullptr) continue;
    if (strEqIgnoreCase(child->valuestring, expected_hw)) {
      copyString(stored_hw, stored_hw_len, child->valuestring);
      return true;
    }
  }
  return false;
}

bool parseManifestFlags(cJSON* root, OkuaOtaManifest* manifest) {
  if (manifest == nullptr) return false;
  manifest->allow_auto_rollback = true;
  manifest->reboot_required = true;
  cJSON* flags = cJSON_GetObjectItemCaseSensitive(root, "flags");
  if (flags == nullptr) return true;
  if (!cJSON_IsObject(flags)) return false;
  cJSON* reboot_required = cJSON_GetObjectItemCaseSensitive(flags, "reboot_required");
  if (cJSON_IsBool(reboot_required)) {
    manifest->reboot_required = cJSON_IsTrue(reboot_required);
  }
  cJSON* allow_auto_rollback = cJSON_GetObjectItemCaseSensitive(flags, "allow_auto_rollback");
  if (cJSON_IsBool(allow_auto_rollback)) {
    manifest->allow_auto_rollback = cJSON_IsTrue(allow_auto_rollback);
  }
  return true;
}

bool parseManifestJson(const char* json_text, OkuaOtaManifest* out_manifest) {
  if (json_text == nullptr || out_manifest == nullptr) return false;
  *out_manifest = {};
  cJSON* root = cJSON_Parse(json_text);
  if (root == nullptr) return false;

  uint32_t schema_version = 0;
  const bool ok =
      loadUIntField(root, "schema_version", &schema_version) &&
      schema_version == 1 &&
      loadStringField(root, "rollout_id", out_manifest->rollout_id, sizeof(out_manifest->rollout_id)) &&
      loadStringField(root, "firmware_family", out_manifest->firmware_family, sizeof(out_manifest->firmware_family)) &&
      loadStringField(root, "target_kind", out_manifest->target_kind, sizeof(out_manifest->target_kind)) &&
      loadStringField(root, "target_variant", out_manifest->target_variant, sizeof(out_manifest->target_variant)) &&
      manifestContainsCompatibleHw(root, okuaBuildCompatibleHw(), out_manifest->compatible_hw, sizeof(out_manifest->compatible_hw)) &&
      loadStringField(root, "build_profile", out_manifest->build_profile, sizeof(out_manifest->build_profile)) &&
      loadStringField(root, "protocol_version", out_manifest->protocol_version, sizeof(out_manifest->protocol_version)) &&
      loadStringField(root, "version", out_manifest->version, sizeof(out_manifest->version)) &&
      loadUIntField(root, "version_code", &out_manifest->version_code) &&
      loadStringField(root, "artifact_id", out_manifest->artifact_id, sizeof(out_manifest->artifact_id)) &&
      loadStringField(root, "sha256", out_manifest->sha256, sizeof(out_manifest->sha256)) &&
      loadUIntField(root, "file_size", &out_manifest->file_size) &&
      loadStringField(root, "download_url", out_manifest->download_url, sizeof(out_manifest->download_url)) &&
      loadStringField(root, "changelog_short", out_manifest->changelog_short, sizeof(out_manifest->changelog_short)) &&
      loadStringField(root, "rollout_channel", out_manifest->rollout_channel, sizeof(out_manifest->rollout_channel)) &&
      loadStringField(root, "published_at_utc", out_manifest->published_at_utc, sizeof(out_manifest->published_at_utc)) &&
      parseManifestFlags(root, out_manifest);

  cJSON_Delete(root);
  return ok;
}

bool validateArtifactIdentityConsistency(const OkuaOtaManifest& manifest) {
  char expected_artifact_id[72] = "";
  snprintf(expected_artifact_id, sizeof(expected_artifact_id), "sha256:%s", manifest.sha256);
  return strEqIgnoreCase(expected_artifact_id, manifest.artifact_id);
}

bool validateManifestCompatibility(const OkuaOtaManifest& manifest) {
  if (!isHexSha256(manifest.sha256)) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_PARSE, "manifest sha256 invalid");
    return false;
  }
  if (!validateArtifactIdentityConsistency(manifest)) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_PARSE, "artifact_id mismatch");
    return false;
  }
  if (manifest.file_size == 0) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_PARSE, "manifest file_size invalid");
    return false;
  }
  if (!strEqIgnoreCase(manifest.firmware_family, okuaBuildFirmwareFamily())) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_INCOMPATIBLE, "firmware_family mismatch");
    return false;
  }
  if (!strEqIgnoreCase(manifest.target_kind, okuaBuildTargetKind())) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_INCOMPATIBLE, "target_kind mismatch");
    return false;
  }
  if (!strEqIgnoreCase(manifest.target_variant, okuaBuildTargetVariant())) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_INCOMPATIBLE, "target_variant mismatch");
    return false;
  }
  if (!strEqIgnoreCase(manifest.compatible_hw, okuaBuildCompatibleHw())) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_INCOMPATIBLE, "compatible_hw mismatch");
    return false;
  }
  if (!strEqIgnoreCase(manifest.build_profile, okuaBuildProfile())) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_INCOMPATIBLE, "build_profile mismatch");
    return false;
  }
  if (!strEqIgnoreCase(manifest.protocol_version, okuaBuildProtocolVersion())) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_INCOMPATIBLE, "protocol_version mismatch");
    return false;
  }
  if (manifest.version_code < okuaBuildVersionCode()) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_VERSION_REJECTED, "downgrade rejected");
    return false;
  }
  if (manifest.version_code == okuaBuildVersionCode() &&
      strEqIgnoreCase(manifest.sha256, okuaBuildArtifactSha256())) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_ALREADY_CURRENT, "artifact already running");
    return false;
  }
  if (manifest.version_code == okuaBuildVersionCode()) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_VERSION_REJECTED, "version_code not newer");
    return false;
  }
  return true;
}

String buildManifestUrl(uint32_t rollout_token) {
  char token_hex[9] = "";
  snprintf(token_hex, sizeof(token_hex), "%08lx", (unsigned long)rollout_token);
  String url(g_config.base_url != nullptr ? g_config.base_url : kDefaultBaseUrl);
  if (!url.endsWith("/")) url += "/";
  url += "ota/rollouts/";
  url += token_hex;
  url += "/manifest.json";
  return url;
}

bool fetchManifestJson(String* out_body) {
  if (out_body == nullptr) return false;
  setState(OKUA_OTA_STATE_FETCHING_MANIFEST, OKUA_OTA_ERROR_NONE, "fetching manifest");
  HTTPClient http;
  WiFiClient client;
  const String manifest_url = buildManifestUrl(g_pendingRolloutToken);
  http.setConnectTimeout((int)g_config.http_timeout_ms);
  http.setTimeout((uint16_t)g_config.http_timeout_ms);
  if (!http.begin(client, manifest_url)) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_HTTP, "http begin manifest failed");
    return false;
  }
  const int status = http.GET();
  if (status != HTTP_CODE_OK) {
    http.end();
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_HTTP, "manifest http status");
    return false;
  }
  *out_body = http.getString();
  http.end();
  if (out_body->length() == 0) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_HTTP, "manifest empty");
    return false;
  }
  return true;
}

bool hashChunkUpdate(mbedtls_md_context_t* ctx, const uint8_t* data, size_t len) {
  if (ctx == nullptr || data == nullptr || len == 0) return true;
  return mbedtls_md_update(ctx, data, len) == 0;
}

bool finalizeSha256(mbedtls_md_context_t* ctx, char* out_hex, size_t out_len) {
  if (ctx == nullptr || out_hex == nullptr || out_len < 65) return false;
  uint8_t digest[32] = {};
  if (mbedtls_md_finish(ctx, digest) != 0) return false;
  for (size_t i = 0; i < sizeof(digest); ++i) {
    snprintf(&out_hex[i * 2], out_len - (i * 2), "%02x", digest[i]);
  }
  return true;
}

bool downloadAndInstall(const OkuaOtaManifest& manifest) {
  setState(OKUA_OTA_STATE_DOWNLOADING, OKUA_OTA_ERROR_NONE, "downloading artifact");
  HTTPClient http;
  WiFiClient client;
  http.setConnectTimeout((int)g_config.http_timeout_ms);
  http.setTimeout((uint16_t)g_config.http_timeout_ms);
  if (!http.begin(client, manifest.download_url)) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_DOWNLOAD_HTTP, "http begin artifact failed");
    return false;
  }
  const int status = http.GET();
  if (status != HTTP_CODE_OK) {
    http.end();
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_DOWNLOAD_HTTP, "artifact http status");
    return false;
  }

  const esp_partition_t* update_partition = esp_ota_get_next_update_partition(nullptr);
  if (update_partition == nullptr) {
    http.end();
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_OTA_BEGIN, "no ota partition");
    return false;
  }

  esp_ota_handle_t ota_handle = 0;
  if (esp_ota_begin(update_partition, manifest.file_size, &ota_handle) != ESP_OK) {
    http.end();
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_OTA_BEGIN, "esp_ota_begin failed");
    return false;
  }

  WiFiClient* stream = http.getStreamPtr();
  const mbedtls_md_info_t* md_info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_context_t md_ctx;
  mbedtls_md_init(&md_ctx);
  if (md_info == nullptr || mbedtls_md_setup(&md_ctx, md_info, 0) != 0 || mbedtls_md_starts(&md_ctx) != 0) {
    mbedtls_md_free(&md_ctx);
    esp_ota_abort(ota_handle);
    http.end();
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_DOWNLOAD_HASH, "sha256 init failed");
    return false;
  }

  uint8_t buffer[1024];
  uint32_t total_written = 0;
  bool write_ok = true;
  while (http.connected() && total_written < manifest.file_size) {
    const size_t available = (size_t)stream->available();
    if (available == 0) {
      delay(2);
      continue;
    }
    const size_t to_read = available < sizeof(buffer) ? available : sizeof(buffer);
    const int read_bytes = stream->readBytes(buffer, to_read);
    if (read_bytes <= 0) {
      write_ok = false;
      break;
    }
    if (!hashChunkUpdate(&md_ctx, buffer, (size_t)read_bytes)) {
      write_ok = false;
      break;
    }
    if (esp_ota_write(ota_handle, buffer, (size_t)read_bytes) != ESP_OK) {
      write_ok = false;
      setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_OTA_WRITE, "esp_ota_write failed");
      break;
    }
    total_written += (uint32_t)read_bytes;
  }

  char downloaded_sha256[65] = "";
  const bool hash_ok = finalizeSha256(&md_ctx, downloaded_sha256, sizeof(downloaded_sha256));
  mbedtls_md_free(&md_ctx);
  http.end();

  if (!write_ok || !hash_ok) {
    esp_ota_abort(ota_handle);
    if (g_error == OKUA_OTA_ERROR_NONE) {
      setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_DOWNLOAD_HTTP, "artifact stream failed");
    }
    return false;
  }
  if (total_written != manifest.file_size) {
    esp_ota_abort(ota_handle);
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_DOWNLOAD_SIZE, "artifact size mismatch");
    return false;
  }
  if (!strEqIgnoreCase(downloaded_sha256, manifest.sha256)) {
    esp_ota_abort(ota_handle);
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_DOWNLOAD_HASH, "artifact sha256 mismatch");
    return false;
  }
  if (esp_ota_end(ota_handle) != ESP_OK) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_OTA_FINALIZE, "esp_ota_end failed");
    return false;
  }
  if (!storeExpectedArtifact(manifest)) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_NVS, "ota expectation persist failed");
    return false;
  }
  loadExpectedArtifact(&g_expectedArtifact);
  if (esp_ota_set_boot_partition(update_partition) != ESP_OK) {
    clearExpectedArtifact();
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_OTA_FINALIZE, "set boot partition failed");
    return false;
  }

  g_flags &= (uint8_t)~OKUA_OTA_FLAG_CHECK_PENDING;
  g_flags |= OKUA_OTA_FLAG_PENDING_REBOOT;
  g_pendingRebootRequest = true;
  setState(OKUA_OTA_STATE_READY_REBOOT, OKUA_OTA_ERROR_NONE, "ota installed, reboot pending");
  return true;
}

bool performPendingCheck() {
  if (g_pendingRolloutToken == 0) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_INVALID_TRIGGER, "rollout token missing");
    return false;
  }

  String manifest_json;
  if (!fetchManifestJson(&manifest_json)) return false;

  setState(OKUA_OTA_STATE_VALIDATING_MANIFEST, OKUA_OTA_ERROR_NONE, "validating manifest");
  OkuaOtaManifest manifest = {};
  if (!parseManifestJson(manifest_json.c_str(), &manifest)) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_MANIFEST_PARSE, "manifest parse failed");
    return false;
  }
  if (!validateManifestCompatibility(manifest)) return false;
  return downloadAndInstall(manifest);
}

bool pendingVerifyOnRunningPartition() {
  const esp_partition_t* running = esp_ota_get_running_partition();
  if (running == nullptr) return false;
  esp_ota_img_states_t ota_state = ESP_OTA_IMG_UNDEFINED;
  if (esp_ota_get_state_partition(running, &ota_state) != ESP_OK) return false;
  return ota_state == ESP_OTA_IMG_PENDING_VERIFY;
}

void startBootValidationIfNeeded() {
  okuaRefreshRunningArtifactIdentity();
  loadExpectedArtifact(&g_expectedArtifact);
  const bool pending_verify = pendingVerifyOnRunningPartition();
  if (!pending_verify) {
    if (g_expectedArtifact.valid) {
      clearExpectedArtifact();
      setState(OKUA_OTA_STATE_IDLE, OKUA_OTA_ERROR_NONE, "stale ota expectation cleared");
      Serial.println("[OTA] Cleared stale expected artifact without pending verify");
    } else {
      g_flags &= (uint8_t)~OKUA_OTA_FLAG_PENDING_VERIFY;
    }
    return;
  }
  g_bootValidationStartMs = millis();
  g_statSentSinceBoot = false;
  g_flags |= OKUA_OTA_FLAG_PENDING_VERIFY;
  setState(OKUA_OTA_STATE_BOOT_VALIDATING, OKUA_OTA_ERROR_NONE, "boot validation pending");
}

bool bootIdentityMatchesExpectation() {
  if (!g_expectedArtifact.valid) {
    return okuaBuildArtifactSha256()[0] != '\0';
  }

  // Download/install already validated the raw firmware bytes against the
  // manifest's file sha256. On boot we should confirm the runtime identity of
  // the newly running image, not re-compare the running partition hash against
  // the original .bin file hash from the catalog/store, because those hashes
  // are not guaranteed to be the same representation.
  if (okuaBuildVersionCode() != g_expectedArtifact.version_code) return false;
  if (g_expectedArtifact.target_kind[0] != '\0' &&
      !strEqIgnoreCase(okuaBuildTargetKind(), g_expectedArtifact.target_kind)) {
    return false;
  }
  if (g_expectedArtifact.target_variant[0] != '\0' &&
      !strEqIgnoreCase(okuaBuildTargetVariant(), g_expectedArtifact.target_variant)) {
    return false;
  }
  if (g_expectedArtifact.build_profile[0] != '\0' &&
      !strEqIgnoreCase(okuaBuildProfile(), g_expectedArtifact.build_profile)) {
    return false;
  }
  return true;
}

void rollbackAndReboot(uint8_t error_code, const char* detail) {
  setState(OKUA_OTA_STATE_ERROR, error_code, detail);
  if (esp_ota_mark_app_invalid_rollback_and_reboot() != ESP_OK) {
    ESP.restart();
  }
}

void maybeFinalizeBootValidation(uint32_t now_ms, bool wifi_connected, bool loop_ready) {
  if ((g_flags & OKUA_OTA_FLAG_PENDING_VERIFY) == 0) return;
  if (g_bootValidationStartMs == 0) g_bootValidationStartMs = now_ms;
  if ((now_ms - g_bootValidationStartMs) < g_config.health_confirm_ms) return;

  if (!wifi_connected) {
    rollbackAndReboot(OKUA_OTA_ERROR_BOOT_WIFI_TIMEOUT, "wifi not healthy after ota boot");
    return;
  }
  if (!loop_ready) {
    rollbackAndReboot(OKUA_OTA_ERROR_BOOT_VALIDATE, "main loop not ready");
    return;
  }
  if (!g_statSentSinceBoot) {
    rollbackAndReboot(OKUA_OTA_ERROR_BOOT_STAT_TIMEOUT, "no stat emitted after ota boot");
    return;
  }
  okuaRefreshRunningArtifactIdentity();
  if (!bootIdentityMatchesExpectation()) {
    rollbackAndReboot(OKUA_OTA_ERROR_BOOT_IDENTITY_MISMATCH, "boot identity mismatch");
    return;
  }
  if (esp_ota_mark_app_valid_cancel_rollback() == ESP_OK) {
    g_flags &= (uint8_t)~OKUA_OTA_FLAG_PENDING_VERIFY;
    g_flags |= OKUA_OTA_FLAG_HEALTH_CONFIRMED;
    clearExpectedArtifact();
    setState(OKUA_OTA_STATE_BOOT_CONFIRMED, OKUA_OTA_ERROR_NONE, "ota boot confirmed");
  } else {
    rollbackAndReboot(OKUA_OTA_ERROR_BOOT_VALIDATE, "esp_ota_mark_app_valid failed");
  }
}

}  // namespace

void okuaOtaConfigure(const OkuaOtaConfig& config) {
  g_config = config;
  if (g_config.base_url == nullptr || g_config.base_url[0] == '\0') {
    g_config.base_url = kDefaultBaseUrl;
  }
  if (g_config.health_confirm_ms == 0) {
    g_config.health_confirm_ms = kDefaultHealthConfirmMs;
  }
  if (g_config.http_timeout_ms == 0) {
    g_config.http_timeout_ms = kDefaultHttpTimeoutMs;
  }
  g_configured = true;
}

void okuaOtaBegin() {
  if (!g_configured) {
    okuaOtaConfigure(g_config);
  }
  g_pendingRolloutToken = 0;
  g_pendingRebootRequest = false;
  g_loopReady = false;
  g_statSentSinceBoot = false;
  g_flags &= (uint8_t)~OKUA_OTA_FLAG_PENDING_REBOOT;
  startBootValidationIfNeeded();
}

bool okuaOtaQueueCheck(uint32_t rollout_token) {
  if (rollout_token == 0) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_INVALID_TRIGGER, "rollout token invalid");
    return false;
  }
  if ((g_flags & OKUA_OTA_FLAG_PENDING_VERIFY) != 0) {
    setState(OKUA_OTA_STATE_ERROR, OKUA_OTA_ERROR_BOOT_VALIDATE, "ota verify in progress");
    return false;
  }
  g_pendingRolloutToken = rollout_token;
  g_flags |= OKUA_OTA_FLAG_CHECK_PENDING;
  setState(OKUA_OTA_STATE_TRIGGERED, OKUA_OTA_ERROR_NONE, "ota check queued");
  return true;
}

void okuaOtaService(uint32_t now_ms, bool wifi_connected, bool loop_ready) {
  g_loopReady = g_loopReady || loop_ready;
  maybeFinalizeBootValidation(now_ms, wifi_connected, g_loopReady);
  if ((g_flags & OKUA_OTA_FLAG_CHECK_PENDING) == 0) return;
  if (!wifi_connected) return;
  if (g_state == OKUA_OTA_STATE_READY_REBOOT) return;
  if (g_state == OKUA_OTA_STATE_BOOT_VALIDATING) return;
  if (g_state == OKUA_OTA_STATE_ERROR && g_pendingRolloutToken == 0) return;

  const bool ok = performPendingCheck();
  if (!ok) {
    g_flags &= (uint8_t)~OKUA_OTA_FLAG_CHECK_PENDING;
    g_pendingRolloutToken = 0;
    return;
  }
  g_pendingRolloutToken = 0;
}

void okuaOtaNotifyStatSent() {
  g_statSentSinceBoot = true;
}

bool okuaOtaShouldAbortWiFiConnect(uint32_t now_ms) {
  if ((g_flags & OKUA_OTA_FLAG_PENDING_VERIFY) == 0) return false;
  if (g_bootValidationStartMs == 0) g_bootValidationStartMs = now_ms;
  return (now_ms - g_bootValidationStartMs) >= g_config.health_confirm_ms;
}

void okuaOtaHandleWiFiConnectTimeout() {
  rollbackAndReboot(OKUA_OTA_ERROR_BOOT_WIFI_TIMEOUT, "wifi connect timeout during ota validation");
}

bool okuaOtaConsumePendingReboot() {
  if (!g_pendingRebootRequest) return false;
  g_pendingRebootRequest = false;
  g_flags &= (uint8_t)~OKUA_OTA_FLAG_PENDING_REBOOT;
  return true;
}

OkuaOtaTelemetry okuaOtaGetTelemetry() {
  OkuaOtaTelemetry telemetry = {};
  telemetry.state_code = g_state;
  telemetry.error_code = g_error;
  telemetry.flags = g_flags;
  telemetry.state_key = stateKey(g_state);
  telemetry.error_key = errorKey(g_error);
  return telemetry;
}

const char* okuaOtaStateKey() { return stateKey(g_state); }
const char* okuaOtaErrorKey() { return errorKey(g_error); }
const char* okuaOtaLastDetail() { return g_lastDetail; }
