# CKv2 Diagnostic Tools

The live fruit diagnostic tools are auxiliary development and field-support utilities. They are not required to run the main CKv2 application runtime.

## Optional Dependencies

`tools/live_diagnostics_panel.py` uses `matplotlib` for embedded charts. Keep this dependency in the development/tooling environment instead of making it mandatory for the production runtime.

Install development and diagnostic dependencies with:

```powershell
python -m pip install -r requirements-dev.txt
```

## Tooling Scope

- `tools/fruit_diag_listener.py` listens for diagnostic UDP lines and can write CSV/log evidence.
- `tools/live_diagnostics_panel.py` displays live or recorded diagnostic sessions.
- `tests/test_live_diagnostics_panel.py` covers parser and panel model behavior for the optional diagnostics tooling.

Do not use these tools to modify field runtime, firmware, scheduled tasks, startup scripts, or hardware state unless a ticket explicitly authorizes that work.
