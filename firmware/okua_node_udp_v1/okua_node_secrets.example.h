#pragma once

// Copy this file to `okua_node_secrets.h` in the same folder and set local
// credentials. The real file is ignored by git.
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASS "YOUR_WIFI_PASSWORD"
#define OKUA_CONTROL_SECRET "YOUR_CONTROL_PLANE_SHARED_SECRET"

// Optional node identity overrides (otherwise defaults from .ino apply).
// Canonical mapping:
//   EB1=1, EC1=2, ED1=3, EE1=4, EF1=5
//   EB2=6, EC2=7, ED2=8, EE2=9, EF2=10
//   ...
//   EB5=21, EC5=22, ED5=23, EE5=24, EF5=25
// #define NODE_LABEL "EB1"
// #define NODE_ID 1

// Optional UDP destination override for EVT/STAT (host running CKv2).
// #define PC_IP_A 192
// #define PC_IP_B 168
// #define PC_IP_C 88
// #define PC_IP_D 251

// Optional Wi-Fi channel lock override.
// Use 0 to let station scan/connect without forcing a fixed channel.
// #define WIFI_CHANNEL 13

// ---------------------------------------------------------------------------
// Test-bank notes (no production defaults changed):
// - Current firmware defaults are already:
//   ACTIVE_MODE   = MODE_TEST
//   ACTIVE_SENSOR = SENSOR_PLANT
// - That means automatic note generation is already enabled in this branch.
// - For test nodes EB2/EC2/ED2 only override identity + Wi-Fi + PC_IP here.
//
// Example for EB2 in a local test network:
// #define NODE_LABEL "EB2"
// #define NODE_ID 6
// #define WIFI_CHANNEL 0
// #define PC_IP_A 192
// #define PC_IP_B 168
// #define PC_IP_C 1
// #define PC_IP_D 57
