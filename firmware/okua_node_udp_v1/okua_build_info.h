#pragma once

#include <stddef.h>
#include <stdint.h>

struct OkuaBuildInfoConfig {
  uint8_t fw_major;
  uint8_t fw_minor;
  uint8_t fw_patch;
  const char* version_str;
  uint32_t version_code;
  const char* target_kind;
  const char* target_variant;
  const char* build_profile;
  const char* protocol_version;
  const char* firmware_family;
  const char* compatible_hw;
};

struct OkuaBuildIdentity {
  uint8_t fw_major;
  uint8_t fw_minor;
  uint8_t fw_patch;
  uint32_t version_code;
  const char* version_str;
  const char* target_kind;
  const char* target_variant;
  const char* build_profile;
  const char* protocol_version;
  const char* firmware_family;
  const char* compatible_hw;
  const char* artifact_id;
  const char* artifact_sha256;
};

void okuaConfigureBuildInfo(const OkuaBuildInfoConfig& config);
const OkuaBuildIdentity& okuaGetBuildIdentity();
bool okuaRefreshRunningArtifactIdentity();
const char* okuaBuildArtifactId();
const char* okuaBuildArtifactSha256();
uint32_t okuaBuildVersionCode();
const char* okuaBuildVersionStr();
const char* okuaBuildTargetKind();
const char* okuaBuildTargetVariant();
const char* okuaBuildProfile();
const char* okuaBuildProtocolVersion();
const char* okuaBuildFirmwareFamily();
const char* okuaBuildCompatibleHw();
