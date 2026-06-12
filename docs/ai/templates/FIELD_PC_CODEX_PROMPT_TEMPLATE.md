# Field PC Codex Prompt Template

Use this template to prepare a sanitized task prompt for controlled field-PC work. Replace every placeholder locally before use, and do not commit the filled prompt.

## Objective

Describe the operational check or maintenance task in one short paragraph.

## Scope

- Target environment: `<FIELD_PC_DESCRIPTION>`
- Runtime status to preserve: `<RUNTIME_TO_PRESERVE>`
- Allowed inspection commands: `<SAFE_COMMANDS_ONLY>`
- Files or services to observe: `<OBSERVATION_TARGETS>`

## Hard Limits

- Do not stop, restart, or modify production runtime unless explicitly approved.
- Do not install packages or tools.
- Do not expose tokens, passwords, user hashes, private IPs, hostnames, or real file paths.
- Do not run scripts that change hardware, firmware, scheduled tasks, startup behavior, or network exposure unless the ticket explicitly allows it.

## Verification

List the checks that prove the task succeeded without revealing private infrastructure details.

## Required Report

- Runtime preserved: yes/no
- Files inspected:
- Commands executed:
- Findings:
- Risks:
- Follow-up recommended:
