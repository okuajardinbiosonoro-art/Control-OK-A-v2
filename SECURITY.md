# CKv2 Security Policy

CKv2 is currently treated as lightweight production. The field PC is not a laboratory target and must not be used for experiments, package installs, agent trials, or undocumented changes.

Before pushing or sharing repository changes:

- Do not commit secrets, tokens, password hashes, control secrets, Wi-Fi credentials, real runtime configs, or private operational state.
- Do not commit `dist/`, generated executables, installers, binary build output, logs, caches, or real field artifacts.
- Do not install or run new tools against field or dirty development environments without human review and approval.
- Report suspected vulnerabilities, exposed secrets, or accidental sensitive files internally before any push.
- Review [docs/security/TOOLING_SECURITY_POLICY.md](docs/security/TOOLING_SECURITY_POLICY.md) before adding tooling, agents, automation, or networked diagnostics.
