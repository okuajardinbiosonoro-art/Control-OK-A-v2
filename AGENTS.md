# Agent Workflow Guardrails

Agents working on CKv2 must first read [docs/ai/AGENT_WORKFLOW.md](docs/ai/AGENT_WORKFLOW.md).

Minimum rules:

- Do not touch the field PC or production runtime unless a human explicitly authorizes that scope.
- Do not install dependencies, run unknown scripts, execute hardware diagnostics, or launch the app without approval.
- Do not run `git clean`, destructive reset commands, or broad cleanup commands.
- Do not modify real secrets, runtime configs, token files, user files, field state, `dist/`, build outputs, or firmware unless the ticket explicitly allows it.
- Do not push without explicit approval.
- Provide a pre-close report before functional commits.
- Split commits by purpose: documentation, security guardrails, firmware, tools, runtime, assets, and tests should not be mixed casually.
- Do not create or use agent worktrees inside the main repository directory.
