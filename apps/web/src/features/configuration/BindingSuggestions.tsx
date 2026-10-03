"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ProgressiveList } from "@/components/ProgressiveList";
import { api } from "@/lib/api";

type Suggestion = {
  candidate_id: string;
  lane: { asset_class: string; instrument_type: string } | null;
  capability: string;
  authority_purpose: string;
  connection_name: string;
  status: "READY" | "NEEDS_TEST" | "ALREADY_BOUND";
  reason: string;
  notes: string[];
};
type Recommendation = {
  id: string;
  account_id: string;
  state: string;
  matrix_version: number;
  mode: "AI_ASSISTED" | "RULE_BASED";
  message: string;
  stale: boolean;
  suggestions: Suggestion[];
  gaps: { lane: string; reason: string }[];
};
type ApplyResult = { verified_count: number; unverified_count: number };

export function BindingSuggestions({ accountId, configurationRevision, configurationReady }: {
  accountId: string;
  configurationRevision: string;
  configurationReady: boolean;
}) {
  const client = useQueryClient();
  const path = `/accounts/${accountId}/provider-binding-suggestions`;
  const queryKey = ["provider-binding-suggestions", accountId, configurationRevision];
  const recommendations = useQuery<Recommendation | null>({
    queryKey, queryFn: () => api(path), enabled: Boolean(accountId) && configurationReady,
  });
  const [selection, setSelection] = useState<{ id: string; candidates: string[] } | null>(null);
  const generate = useMutation({
    mutationFn: async () => {
      await client.cancelQueries({ queryKey: ["provider-binding-suggestions", accountId] });
      return api<Recommendation>(path, { method: "POST" });
    },
    onSuccess: result => { client.setQueryData(queryKey, result); setSelection(null); },
  });
  const apply = useMutation({
    mutationFn: (input: { recommendation_id: string; candidate_ids: string[] }) =>
      api<ApplyResult>(`${path}/apply`, { method: "POST", body: JSON.stringify(input) }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["provider-bindings", accountId] });
      await client.invalidateQueries({ queryKey: ["provider-binding-suggestions", accountId] });
    },
    onError: async () => {
      await client.invalidateQueries({ queryKey: ["provider-binding-suggestions", accountId] });
    },
  });
  const recommendation = recommendations.data;
  const selected = selection && selection.id === recommendation?.id ? selection.candidates
    : (recommendation?.suggestions ?? []).filter(item => item.status === "READY").map(item => item.candidate_id);
  const busy = generate.isPending || apply.isPending;
  const reviewable = Boolean(recommendation && !recommendation.stale && recommendation.state !== "APPLIED");
  const error = generate.error ?? apply.error ?? recommendations.error;

  return <article className="card form-stack">
    <div className="split"><div><h3>AI binding assistance</h3><p className="muted">Suggest sources for this account’s enabled lanes, price history and economic context.</p></div>
      <button className="btn primary" disabled={!accountId || !configurationReady || busy} onClick={() => {
        apply.reset(); generate.mutate();
      }}>{generate.isPending ? "Reviewing sources…" : "Suggest bindings with AI"}</button>
    </div>
    {error ? <p role="alert" className="notice bad">{error.message}</p> : null}
    {apply.data ? <p role="status" className="notice good">Applied: {apply.data.verified_count} verified, {apply.data.unverified_count} awaiting connection testing.</p> : null}
    {recommendation ? <>
      <p className={`notice ${recommendation.mode === "RULE_BASED" ? "warn" : "good"}`}>
        {recommendation.mode === "AI_ASSISTED" ? "AI assisted" : "Rule based"} · Matrix v{recommendation.matrix_version}. {recommendation.message}
      </p>
      {recommendation.stale && recommendation.state !== "APPLIED" ? <p className="notice warn">Your configuration changed. Generate new suggestions before applying them.</p> : null}
      {recommendation.state === "APPLIED" ? <p className="muted">These suggestions have been applied. Generate again to review remaining gaps.</p> : null}
      {recommendation.suggestions.length ? <ProgressiveList items={recommendation.suggestions} pageSize={6} label="binding suggestions" scopeKey={recommendation.id}>{visible => <div className="table-wrap"><table>
        <thead><tr><th>Apply</th><th>Coverage</th><th>Source & use</th><th>Reason</th></tr></thead>
        <tbody>{visible.map(item => {
          const coverage = item.lane ? `${item.lane.asset_class} · ${item.lane.instrument_type}` : "Economic context";
          return <tr key={item.candidate_id}>
            <td>{item.status === "ALREADY_BOUND" ? <span>Already verified</span> : <label>
              <input type="checkbox" aria-label={`Apply ${coverage} ${item.capability} ${item.connection_name}`}
                disabled={!reviewable || busy} checked={selected.includes(item.candidate_id)}
                onChange={event => setSelection({ id: recommendation.id, candidates: event.target.checked
                  ? [...selected, item.candidate_id] : selected.filter(id => id !== item.candidate_id) })} />
              {item.status === "NEEDS_TEST" ? "Needs testing" : "Ready"}
            </label>}</td>
            <td>{coverage}</td><td>{item.connection_name}<small>{item.capability} · {item.authority_purpose}</small></td>
            <td>{item.reason}{item.notes.map((note, index) => <small key={index}>{note}</small>)}</td>
          </tr>;
        })}</tbody>
      </table></div>}</ProgressiveList> : <p className="empty">No compatible bindings can be suggested from the configured sources.</p>}
      {recommendation.gaps.length ? <div className="inset"><h4>Missing coverage</h4><ul>{recommendation.gaps.map(gap => <li key={gap.lane}>{gap.lane.replace(":", " · ")}: {gap.reason}</li>)}</ul></div> : null}
      {recommendation.suggestions.some(item => item.status !== "ALREADY_BOUND") ? <>
        <small>Tested capabilities can be verified when applied. Untested suggestions are saved for Test & verify. Existing bindings are retained.</small>
        <button className="btn primary" disabled={!reviewable || !selected.length || busy}
          onClick={() => apply.mutate({ recommendation_id: recommendation.id, candidate_ids: selected })}>
          {apply.isPending ? "Applying…" : `Apply ${selected.length} selected bindings`}
        </button>
      </> : null}
    </> : <p className="muted">Choose an account and request suggestions based on its research matrix and configured connections.</p>}
  </article>;
}
