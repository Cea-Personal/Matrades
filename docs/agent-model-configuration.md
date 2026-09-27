# Agent model configuration

`.codex/agents/<logical_id>.toml` is the source of model and reasoning-effort
defaults for the agent registry, API and isolated agent worker. Files are read
on each configuration request/job; defaults are not cached at process startup.
Invalid or missing native configurations fail visibly instead of selecting an
older hard-coded model.

An explicitly saved model profile takes precedence for that agent. In the
Agents view, choose **Native agent file** to remove a profile selection and follow
the file again. Stable default profile IDs are retained for existing selections.
Saved profiles also remain authoritative when their ID matches a default ID.

The parent Codex orchestrator uses its own native model/effort, or its saved
Codex profile. It does not reuse the specialist model. A specialist invocation
gets a private, temporary native role configuration containing its selected
model/effort. All other role settings, including instructions and read-only
permissions, are preserved. The temporary file is removed after thread cleanup;
the original agent files are never rewritten.

The Agents table distinguishes current configuration from historical execution:

- **Configured runtime / model**: current file default or saved profile override.
- **Model source**: native file path or explicitly saved profile.
- **Last-run runtime / model**: observed execution model, not the requested model.
  Codex evidence comes from the completed thread's JSONL turn context; gateway
  evidence comes from the completion response's model metadata.
- **Model unverified — retest**: legacy records or runtimes without model evidence.
  Successful research can still be recorded without claiming a verified model.

Configuration refreshes in the UI every 15 seconds. Historical executions are
not rewritten when a file changes. API agent tests reuse the worker's persisted
execution rather than adding a second record that copies the requested model.

After upgrading this application code, restart the API and agent worker and
rebuild/restart the frontend if serving a production bundle. For containerized
services, rebuild images after changing agent files unless those files are
mounted from the host. Keep the API and worker on the same configuration revision.

The implementation follows the native-role precedence described in the official
[Codex subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents)
and the installed [App Server protocol](https://learn.chatgpt.com/docs/app-server).
Per-thread role layers use the documented
[agent configuration keys](https://learn.chatgpt.com/docs/config-file/config-reference).
