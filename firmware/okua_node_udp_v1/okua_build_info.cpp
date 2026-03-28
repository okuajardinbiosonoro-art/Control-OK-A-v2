#include "okua_build_info.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

#include <esp_ota_ops.h>
#include <esp_partition.h>

namespace {

static const char* kDefaultVersionStr = "0.0.0-dev";
static const char* kDefaultTargetKind = "unknown";
static const char* kDefaultTargetVariant = "generic";
static const char* kDefaultBuildProfile = "test";
static const char* kDefaultProtocolVersion = "okua_v1";
static const char* kDefaultFirmwareFamily = "okua_node_udp_v1";
static const char* kDefaultCompatibleHw = "esp32dev";

OkuaBuildInfoConfig g_config = {
    0,
    0,
    0,
    kDefaultVersionStr,
    0,
    kDefaultTargetKind,
    kDefaultTargetVariant,
    kDefaultBuildProfile,
    kDefaultProtocolVersion,
    kDefaultFirmwareFamily,
    kDefaultCompatibleHw,
};

char g_versionStr[32] = "0.0.0-dev";
char g_targetKind[24] = "unknown";
char g_targetVariant[32] = "generic";
char g_buildProfile[24] = "test";
char g_protocolVersion[24] = "okua_v1";
char g_firmwareFamily[40] = "okua_node_udp_v1";
char g_compatibleHw[24] = "esp32dev";
char g_artifactSha256[65] = "";
char g_artifactId[72] = "";
bool g_configured = false;
bool g_identityCached = false;
OkuaBuildIdentity g_identity = {};

void copyNormalizedAscii(char* dst, size_t dst_len, const char* src) {
  if (dst == nullptr || dst_len == 0) return;
  const char* resolved = (src != nullptr && src[0] != '\0') ? src : "";
  size_t i = 0;
  for (; i + 1 < dst_len && resolved[i] != '\0'; ++i) {
    const unsigned char ch = (unsigned char)resolved[i];
    dst[i] = (char)tolower(ch);
  }
  dst[i] = '\0';
}

void copyString(char* dst, size_t dst_len, const char* src, const char* fallback) {
  if (dst == nullptr || dst_len == 0) return;
  const char* resolved = (src != nullptr && src[0] != '\0') ? src : fallback;
  if (resolved == nullptr) resolved = "";
  size_t i = 0;
  for (; i + 1 < dst_len && resolved[i] != '\0'; ++i) {
    dst[i] = resolved[i];
  }
  dst[i] = '\0';
}

void refreshIdentityStruct() {
  g_identity.fw_major = g_config.fw_major;
  g_identity.fw_minor = g_config.fw_minor;
  g_identity.fw_patch = g_config.fw_patch;
  g_identity.version_code = g_config.version_code;
  g_identity.version_str = g_versionStr;
  g_identity.target_kind = g_targetKind;
  g_identity.target_variant = g_targetVariant;
  g_identity.build_profile = g_buildProfile;
  g_identity.protocol_version = g_protocolVersion;
  g_identity.firmware_family = g_firmwareFamily;
  g_identity.compatible_hw = g_compatibleHw;
  g_identity.artifact_id = g_artifactId;
  g_identity.artifact_sha256 = g_artifactSha256;
  g_identityCached = true;
}

}  // namespace

void okuaConfigureBuildInfo(const OkuaBuildInfoConfig& config) {
  g_config = config;
  copyString(g_versionStr, sizeof(g_versionStr), config.version_str, kDefaultVersionStr);
  copyNormalizedAscii(g_targetKind, sizeof(g_targetKind), config.target_kind);
  if (g_targetKind[0] == '\0') copyString(g_targetKind, sizeof(g_targetKind), kDefaultTargetKind, kDefaultTargetKind);
  copyNormalizedAscii(g_targetVariant, sizeof(g_targetVariant), config.target_variant);
  if (g_targetVariant[0] == '\0') copyString(g_targetVariant, sizeof(g_targetVariant), kDefaultTargetVariant, kDefaultTargetVariant);
  copyNormalizedAscii(g_buildProfile, sizeof(g_buildProfile), config.build_profile);
  if (g_buildProfile[0] == '\0') copyString(g_buildProfile, sizeof(g_buildProfile), kDefaultBuildProfile, kDefaultBuildProfile);
  copyNormalizedAscii(g_protocolVersion, sizeof(g_protocolVersion), config.protocol_version);
  if (g_protocolVersion[0] == '\0') copyString(g_protocolVersion, sizeof(g_protocolVersion), kDefaultProtocolVersion, kDefaultProtocolVersion);
  copyNormalizedAscii(g_firmwareFamily, sizeof(g_firmwareFamily), config.firmware_family);
  if (g_firmwareFamily[0] == '\0') copyString(g_firmwareFamily, sizeof(g_firmwareFamily), kDefaultFirmwareFamily, kDefaultFirmwareFamily);
  copyNormalizedAscii(g_compatibleHw, sizeof(g_compatibleHw), config.compatible_hw);
  if (g_compatibleHw[0] == '\0') copyString(g_compatibleHw, sizeof(g_compatibleHw), kDefaultCompatibleHw, kDefaultCompatibleHw);
  if (g_config.version_code == 0) {
    g_config.version_code =
        ((uint32_t)g_config.fw_major * 10000UL) +
        ((uint32_t)g_config.fw_minor * 100UL) +
        (uint32_t)g_config.fw_patch;
  }
  g_configured = true;
  okuaRefreshRunningArtifactIdentity();
  refreshIdentityStruct();
}

bool okuaRefreshRunningArtifactIdentity() {
  const esp_partition_t* running = esp_ota_get_running_partition();
  if (running == nullptr) {
    g_artifactSha256[0] = '\0';
    g_artifactId[0] = '\0';
    refreshIdentityStruct();
    return false;
  }

  uint8_t digest[32] = {};
  if (esp_partition_get_sha256(running, digest) != ESP_OK) {
    g_artifactSha256[0] = '\0';
    g_artifactId[0] = '\0';
    refreshIdentityStruct();
    return false;
  }

  for (size_t i = 0; i < sizeof(digest); ++i) {
    snprintf(&g_artifactSha256[i * 2], sizeof(g_artifactSha256) - (i * 2), "%02x", digest[i]);
  }
  snprintf(g_artifactId, sizeof(g_artifactId), "sha256:%s", g_artifactSha256);
  refreshIdentityStruct();
  return true;
}

const OkuaBuildIdentity& okuaGetBuildIdentity() {
  if (!g_configured) {
    okuaConfigureBuildInfo(g_config);
  } else if (!g_identityCached) {
    refreshIdentityStruct();
  }
  return g_identity;
}

const char* okuaBuildArtifactId() { return okuaGetBuildIdentity().artifact_id; }
const char* okuaBuildArtifactSha256() { return okuaGetBuildIdentity().artifact_sha256; }
uint32_t okuaBuildVersionCode() { return okuaGetBuildIdentity().version_code; }
const char* okuaBuildVersionStr() { return okuaGetBuildIdentity().version_str; }
const char* okuaBuildTargetKind() { return okuaGetBuildIdentity().target_kind; }
const char* okuaBuildTargetVariant() { return okuaGetBuildIdentity().target_variant; }
const char* okuaBuildProfile() { return okuaGetBuildIdentity().build_profile; }
const char* okuaBuildProtocolVersion() { return okuaGetBuildIdentity().protocol_version; }
const char* okuaBuildFirmwareFamily() { return okuaGetBuildIdentity().firmware_family; }
const char* okuaBuildCompatibleHw() { return okuaGetBuildIdentity().compatible_hw; }
