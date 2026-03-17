# Firmware workspace

This repository now tracks the node sketch used by CKv2 tickets under:

- `firmware/okua_node_udp_v1/okua_node_udp_v1.ino`
- `firmware/okua_node_udp_v1/okua_control_plane.h`

Ticket 13.1 scope in this folder:

- explicit F3 control-plane ports (`5005/5006/5007/5008`)
- packed `OKUA_CMD` and `OKUA_ACK` models (28 bytes each)
- baseline enums/constants for later command handling

No command execution handlers are active yet.

Ticket 13.2 adds UDP CMD receive parsing + structural validation/classification
without ACK emission and without command execution.

Local Wi-Fi secrets override:

- defaults in repo: `WIFI_SSID="OKUA_CORE"` and `WIFI_PASS="CHANGE_ME"`
- default control secret in repo: `OKUA_CONTROL_SECRET="CHANGE_ME_CONTROL_SECRET"`
- optional local override: `firmware/okua_node_udp_v1/okua_node_secrets.h`
- template: `firmware/okua_node_udp_v1/okua_node_secrets.example.h`
