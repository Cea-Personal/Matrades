"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ProgressiveList } from "@/components/ProgressiveList";
import { Disclosure } from "@/components/Disclosure";
import { api } from "@/lib/api";
import { useKeyedMutation } from "@/lib/useKeyedMutation";
import type { ModelProfile } from "@/features/agents/ModelProfiles";

type Agent = {
  logical_id: string; required: boolean;
  runtime: "CODEX_APP_SERVER" | "LITELLM_GATEWAY"; profile_id: string | null;
  recommended_model?: string; recommended_reasoning_effort?: string;
  configured_model?: string; configured_reasoning_effort?: string;
  model_source?: "native_agent" | "profile_override"; native_config_file?: string;
  system_prompt_override: string | null; user_prompt_override: string | null;
  permission_set_version: string;
};
type AgentStatus = {
  codex_worker_heartbeat: boolean; codex_auth_mode: string;
  agents: Array<{
    logical_id: string; configured_runtime: string; actual_runtime?: string;
    actual_model?: string | null; model_verified?: boolean; orchestrator_model?: string | null;
    requested_model?: string; last_status?: string; last_error?: string;
    last_tested_at?: string; execution_id?: string; duration_ms?: number; evidence: string;
  }>;
};
type TestResult = {
  logical_id: string; execution?: { status?: string; actual_runtime?: string };
  result?: unknown; error?: string;
};

function testAgent(id: string) {
  return api<Omit<TestResult, "logical_id">>(`/agents/${id}/test`, {
    method: "POST",
    body: JSON.stringify({ input: { purpose: "configuration_test", requested_at: new Date().toISOString() } }),
  });
}

export function AgentConfiguration() {
  const client = useQueryClient();
  const agents = useQuery<Agent[]>({
    queryKey: ["agents", "registry"], queryFn: () => api("/agents/registry"),
    refetchInterval: 15_000,
  });
  const profiles = useQuery<ModelProfile[]>({
    queryKey: ["agents", "profiles"], queryFn: () => api("/agents/profiles"),
    refetchInterval: 15_000,
  });
  const runtimeStatus = useQuery<AgentStatus>({
    queryKey: ["agents", "status"], queryFn: () => api("/agents/status"),
    refetchInterval: 15_000,
  });
  const [selected, setSelected] = useState<Agent | null>(null);
  const [individualResults, setIndividualResults] = useState<Record<string, TestResult>>({});
  const bulkTestRunning = useRef(false);
  const [allResults, setAllResults] = useState<TestResult[]>([]);
  const [error, setError] = useState("");
  const save = useMutation({
    mutationFn: (agent: Agent) => api(`/agents/${agent.logical_id}`, {
      method: "PUT", body: JSON.stringify(agent),
    }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["agents"] }); setSelected(null);
    },
    onError: (e: Error) => setError(e.message),
  });
  const test = useKeyedMutation({
    mutationFn: testAgent,
    onSuccess: async (value, id) => {
      setIndividualResults(previous => ({ ...previous, [id]: { ...value, logical_id: id } }));
      await client.invalidateQueries({ queryKey: ["agents", "status"] });
    },
    onError: (e: Error, id) => {
      setIndividualResults(previous => ({ ...previous, [id]: { logical_id: id, error: e.message } }));
    },
  });
  const testAll = useMutation({
    retry: false,
    mutationFn: async () => Promise.all((agents.data ?? []).map(async agent => {
      try {
        return {
          logical_id: agent.logical_id,
          ...await testAgent(agent.logical_id),
        };
      } catch (cause) {
        return { logical_id: agent.logical_id, error: cause instanceof Error ? cause.message : String(cause) };
      }
    })),
    onSuccess: async values => {
      setAllResults(values); await client.invalidateQueries({ queryKey: ["agents", "status"] });
    },
    onError: (e: Error) => setError(e.message),
    onSettled: () => { bulkTestRunning.current = false; },
  });
  const startTest = (id: string) => {
    if (bulkTestRunning.current || !test.mutate(id)) return;
    setIndividualResults(previous => {
      const next = { ...previous };
      delete next[id];
      return next;
    });
  };
  const startAllTests = () => {
    if (bulkTestRunning.current || test.hasPending() || !agents.data?.length) return;
    bulkTestRunning.current = true;
    setError("");
    testAll.mutate();
  };

  return <section className="section-stack">
    <article className="card">
      <div className="actions">
        <div>
          <h2>Logical agent registry</h2>
          <p className="muted">Native agent files supply the defaults. Saved profiles are explicit overrides. Last-run models are shown only when runtime evidence verifies them.</p>
        </div>
        <button className="btn primary" disabled={testAll.isPending || test.pendingKeys.size > 0 || agents.isPending || agents.isError || !agents.data?.length}
          onClick={startAllTests}>Test all logical agents</button>
      </div>
      <p className={runtimeStatus.data?.codex_worker_heartbeat ? "notice good" : "notice bad"}>
        {runtimeStatus.data?.codex_worker_heartbeat
          ? `Codex App Server worker heartbeat: healthy · authentication: ${runtimeStatus.data.codex_auth_mode}`
          : "Codex App Server worker heartbeat: unavailable — start/restart agent-worker"}
      </p>
      <p className="muted">The isolated agent-worker uses host Codex authentication. Configuration refreshes every 15 seconds; changing a file does not rewrite historical executions.</p>
      {agents.isError && <p role="alert" className="notice bad">Unable to load agent configuration: {agents.error.message}</p>}
      {runtimeStatus.isError && <p role="alert" className="notice bad">Execution evidence is unavailable. Current configuration is still shown separately.</p>}
      {agents.isPending ? <p>Loading…</p> : <ProgressiveList items={agents.data ?? []} label="agents" pageSize={6}>
        {visible => <div className="table-wrap"><table>
          <thead><tr><th>Agent</th><th>Configured runtime / model</th><th>Last-run runtime / model</th><th>Last execution evidence</th><th>Model source</th><th>Tools</th><th /></tr></thead>
          <tbody>{visible.map(agent => {
            const status = runtimeStatus.data?.agents.find(item => item.logical_id === agent.logical_id);
            const profile = profiles.data?.find(item => item.id === agent.profile_id);
            const configuredModel = agent.configured_model ?? profile?.model ?? agent.recommended_model;
            const verifiedModel = status?.model_verified ? status.actual_model : null;
            const isTesting = test.pendingKeys.has(agent.logical_id) || testAll.isPending;
            const individualResult = individualResults[agent.logical_id];
            return <tr key={agent.logical_id}>
              <td><strong>{agent.logical_id}</strong>{agent.required && <small> protected</small>}</td>
              <td>{agent.runtime}<small>{configuredModel ?? "Configuration unavailable"} · {agent.configured_reasoning_effort ?? (agent.runtime === "CODEX_APP_SERVER" ? agent.recommended_reasoning_effort : null) ?? "model default"}</small></td>
              <td>{status?.actual_runtime ?? "Not tested"}
                <small>{verifiedModel ?? (status?.execution_id ? "Model unverified — retest" : "No execution evidence")}</small>
                {status?.orchestrator_model && agent.logical_id !== "orchestrator" && <small>Orchestrator: {status.orchestrator_model}</small>}
                {verifiedModel && configuredModel && verifiedModel !== configuredModel && <small>Configured model differs from this historical run</small>}
              </td>
              <td>{status?.last_status ?? "Not tested"}
                {status?.last_error && <small>{status.last_error}</small>}
                {status?.execution_id && <small>{status.execution_id.slice(0, 12)} · {status.last_tested_at ? new Date(status.last_tested_at).toLocaleString() : ""} · {status.duration_ms ?? 0} ms</small>}
              </td>
              <td>{agent.model_source === "profile_override" ? "Saved profile override" : "Native agent file"}
                <small>{agent.model_source === "profile_override" ? profile?.name ?? "Saved model profile" : agent.native_config_file ?? `.codex/agents/${agent.logical_id}.toml`}</small>
              </td>
              <td>{agent.permission_set_version}</td>
              <td><button className="btn compact" onClick={() => setSelected({ ...agent })}>Configure</button>{" "}
                <button className="btn compact" disabled={isTesting} aria-busy={isTesting}
                  onClick={() => startTest(agent.logical_id)}>{isTesting ? "Testing…" : "Test"}</button>
                {individualResult?.error && <small role="alert" className="notice bad">Test failed: {individualResult.error}</small>}
              </td>
            </tr>;
          })}</tbody>
        </table></div>}
      </ProgressiveList>}
    </article>
    {allResults.length > 0 && <article className="card">
      <h2>Agent test execution summary</h2>
      <ProgressiveList items={allResults} label="test results">{visible => <ul className="record-list">
        {visible.map(item => <li key={item.logical_id}><strong>{item.logical_id}</strong>
          <span>{item.execution?.status ?? "ERROR"} · {item.execution?.actual_runtime ?? "unknown runtime"}</span>
          <small>{item.error ?? "Execution persisted"}</small></li>)}
      </ul>}</ProgressiveList>
    </article>}
    {selected && <form className="card form-stack" onSubmit={e => {
      e.preventDefault(); setError(""); save.mutate(selected);
    }}>
      <h2>Configure {selected.logical_id}</h2>
      <label>Model profile<select value={selected.profile_id ?? ""} onChange={e => {
        const profile = profiles.data?.find(item => item.id === e.target.value);
        setSelected({ ...selected, profile_id: profile?.id ?? null, runtime: profile?.runtime ?? "CODEX_APP_SERVER" });
      }}>
        <option value="">Native agent file ({selected.recommended_model ?? "configuration unavailable"})</option>
        {profiles.data?.map(profile => <option key={profile.id} value={profile.id}>{profile.name} · {profile.runtime}</option>)}
      </select></label>
      <p className="muted">Choose Native agent file to follow edits in {selected.native_config_file ?? `.codex/agents/${selected.logical_id}.toml`}. A saved profile overrides the model for this agent without editing its file.</p>
      <label>System prompt override<textarea value={selected.system_prompt_override ?? ""}
        onChange={e => setSelected({ ...selected, system_prompt_override: e.target.value || null })} /></label>
      <label>User prompt override<textarea value={selected.user_prompt_override ?? ""}
        onChange={e => setSelected({ ...selected, user_prompt_override: e.target.value || null })} /></label>
      <p className="muted">System and user chains resolve independently. Profile changes cannot alter the permission set.</p>
      <div className="actions"><button className="btn primary" disabled={save.isPending}>Activate configuration</button>
        <button type="button" className="btn" onClick={() => setSelected(null)}>Cancel</button></div>
    </form>}
    {Object.keys(individualResults).length > 0 && <article className="card"><h2>Bounded execution results</h2>
      <ProgressiveList items={Object.values(individualResults).reverse()} label="individual test results">
        {visible => <div className="section-stack">{visible.map(item => <Disclosure key={item.logical_id}
          title={`${item.logical_id} · ${item.error ? "ERROR" : item.execution?.status ?? "Completed"}`}>
          <pre>{JSON.stringify(item, null, 2)}</pre>
        </Disclosure>)}</div>}
      </ProgressiveList></article>}
    {error && <p className="notice bad">{error}</p>}
  </section>;
}
