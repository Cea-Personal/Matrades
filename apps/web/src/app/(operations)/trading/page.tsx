"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { TradeManagement } from "@/features/trading/TradeManagement";
import { TradeProposalPanel, type Proposal } from "@/features/trading/TradeProposalPanel";
import { api, type Resource } from "@/lib/api";

export default function TradingPage() {
  const client=useQueryClient();const [message,setMessage]=useState("");
  const proposals=useQuery<Resource[]>({queryKey:["trading","proposals"],queryFn:()=>api("/trade-proposals")});
  const pending=proposals.data?.filter(item=>item.state==="AWAITING_HIL2"||item.state==="BLOCKED")??[];
  const decide=useMutation({mutationFn:({id,action}:{id:string;action:string})=>api(`/trade-proposals/${id}/decisions`,{method:"POST",body:JSON.stringify({action})}),onSuccess:async()=>{setMessage("HIL-2 decision persisted.");await client.invalidateQueries({queryKey:["trading"]});},onError:(error:Error)=>setMessage(error.message)});
  return <section className="section-stack"><header><p className="eyebrow">Human-in-the-loop 2</p><h1>Trade proposals</h1><p className="muted">Only server-created, fresh, policy-evaluated proposals are actionable.</p></header>{message&&<p className="notice">{message}</p>}{proposals.isPending?<p>Loading proposals…</p>:pending.length?pending.map(item=><TradeProposalPanel key={item.id} proposal={item as unknown as Proposal} onDecision={action=>decide.mutate({id:item.id,action})}/>):<article className="card empty">No proposals currently require HIL-2 review.</article>}<article className="card"><h2>Proposal history</h2>{proposals.data?.length?<div className="table-wrap"><table><thead><tr><th>Instrument</th><th>Direction</th><th>State</th><th>Strategy</th><th>Updated</th></tr></thead><tbody>{proposals.data.map(item=><tr key={item.id}><td>{String(item.instrument)}</td><td>{String(item.direction)}</td><td>{item.state}</td><td>{String(item.strategy_version)}</td><td>{new Date(item.updated_at).toLocaleString()}</td></tr>)}</tbody></table></div>:<p className="empty">No persisted proposals.</p>}</article><TradeManagement/></section>;
}
