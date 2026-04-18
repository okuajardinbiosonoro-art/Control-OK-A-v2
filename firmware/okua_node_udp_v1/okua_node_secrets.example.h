#pragma once

// Copy this file to `okua_node_secrets.h` in the same folder and set local
// credentials. The real file is ignored by git.
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASS "YOUR_WIFI_PASSWORD"
#define OKUA_CONTROL_SECRET "YOUR_CONTROL_PLANE_SHARED_SECRET"

// Optional node identity overrides (otherwise defaults from the main firmware .ino apply).
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

// Optional OTA port override.
// Keep this value in sync with the OTA Deploy dialog in CKv2 and with the
// local HTTP server port used on the PC.
// #define OKUA_OTA_PORT 18080
//
// If you prefer to pin the full URL explicitly, you can also override:
// #define OKUA_OTA_BASE_URL "http://192.168.1.70:18080"

// Optional Wi-Fi channel lock override.
// Use 0 to let station scan/connect without forcing a fixed channel.
// #define WIFI_CHANNEL 13

// Optional profile overrides for manual field builds.
// Since the main firmware reads this file before defaults, these can switch
// mode/sensor without editing the .ino.
// #define ACTIVE_MODE MODE_FIELD
// #define ACTIVE_SENSOR SENSOR_FRUIT
// #define ACTIVE_FRUIT_VARIANT FRUIT_VARIANT_V2

// Optional fruit routing presets:
// - FRUIT_ROUTE_PRESET_EB_FANOUT -> ch 1, 3, 5  (EB1 + ED1 + EF1)
// - FRUIT_ROUTE_PRESET_EC_FANOUT -> ch 2, 4, 5  (EC1 + EE1 + EF1)
// - FRUIT_ROUTE_PRESET_CUSTOM    -> define FRUIT_ROUTE_* manually
// #define FRUIT_ROUTE_PRESET FRUIT_ROUTE_PRESET_EB_FANOUT

// Optional fixed offset for fruit nodes that need it.
// By default the firmware auto-calibrates and keeps a stable baseline.
// Use this only if a sensor needs a manual anchor around a known rest level.
// #define FRUIT_FIXED_OFFSET_V 1.50f
// #define FRUIT_FIXED_OFFSET_WINDOW_V 0.35f

// Optional fruit ADC input override (default PIN_SIGNAL=32).
// Use this if a field board routes the analog signal to a different ADC pin.
// #define PIN_SIGNAL 33

// Optional ADC scan debug over Serial for fruit mode.
// Prints p32/p33/p34/p35/p36/p39 values every interval so you can identify
// which pin changes while touching the sensor.
// #define FRUIT_ADC_SCAN_SERIAL 1
// #define FRUIT_ADC_SCAN_INTERVAL_MS 200UL

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

// Example for EB1 field/fruit on Mikrotik-compatible network:
// #define NODE_LABEL "EB1"
// #define NODE_ID 1
// #define ACTIVE_MODE MODE_FIELD
// #define ACTIVE_SENSOR SENSOR_FRUIT
// #define FRUIT_ROUTE_PRESET FRUIT_ROUTE_PRESET_EB_FANOUT
// #define WIFI_CHANNEL 0

// Example for EC1 field/fruit on the same network:
// #define NODE_LABEL "EC1"
// #define NODE_ID 2
// #define ACTIVE_MODE MODE_FIELD
// #define ACTIVE_SENSOR SENSOR_FRUIT
// #define FRUIT_ROUTE_PRESET FRUIT_ROUTE_PRESET_EC_FANOUT
// #define FRUIT_FIXED_OFFSET_V -1.0f
// #define WIFI_CHANNEL 0
