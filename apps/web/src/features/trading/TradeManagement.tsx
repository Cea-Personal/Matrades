"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Resource } from "@/lib/api";

// Reconciliation state path: AWAITING_MANUAL_ENTRY → AMBIGUOUS or ACTIVE; execute manually.

export function TradeManagement(){
  const client=useQueryClient();const [message,setMessage]=useState("");
  const [monitorInput,setMonitorInput]=useState({trade_id:"",current_price:""});
  const trades=useQuery<Resource[]>({queryKey:["trading","active"],queryFn:()=>api("/trade-management/trades")});
  const reconciliations=useQuery<Resource[]>({queryKey:["trading","reconciliations"],queryFn:()=>api("/trade-management/reconciliations")});
  const recommendations=useQuery<Resource[]>({queryKey:["trading","recommendations"],queryFn:()=>api("/trade-management/recommendations")});
  const decide=useMutation({mutationFn:({id,action}:{id:string;action:string})=>api(`/trade-management/recommendations/${id}/decisions`,{method:"POST",body:JSON.stringify({action})}),onSuccess:async()=>{setMessage("HIL-3 decision recorded; manual broker action remains required.");await client.invalidateQueries({queryKey:["trading"]});},onError:(error:Error)=>setMessage(error.message)});
  const monitor=useMutation({mutationFn:()=>api("/trade-management/monitor",{method:"POST",body:JSON.stringify({...monitorInput,bridge_fresh:true})}),onSuccess:async()=>{setMessage("Fresh monitoring facts and recommendation persisted.");await client.invalidateQueries({queryKey:["trading"]});},onError:(error:Error)=>setMessage(error.message)});
  return <section className="section-stack"><header><h1>Manual trade management</h1><p className="muted">Broker observations are authoritative. Matrades records approval intent but never writes orders.</p></header>{message&&<p className="notice">{message}</p>}
    <div className="grid two"><article className="card"><h2>Active broker positions</h2>{trades.isPending?<p>Loading…</p>:trades.data?.length?<ul className="record-list">{trades.data.map(item=><li key={item.id}><strong>{String((item.broker_position as Record<string,unknown>)?.instrument??item.id)}</strong><span>{item.state}</span><small>{String((item.broker_position as Record<string,unknown>)?.pnl??"P&L unavailable")}</small></li>)}</ul>:<p className="empty">No reconciled active positions.</p>}</article><article className="card"><h2>Reconciliation</h2>{reconciliations.data?.length?<ul className="record-list">{reconciliations.data.map(item=><li key={item.id}><strong>{item.state}</strong><span>{String(item.reason??item.selected_position_id??"Pending broker match")}</span></li>)}</ul>:<p className="empty">No reconciliation attempts.</p>}</article></div>
    <article className="card"><h2>HIL-3 recommendations</h2>{recommendations.isPending?<p>Loading…</p>:recommendations.data?.length?<div className="table-wrap"><table><thead><tr><th>Action</th><th>Reason</th><th>State</th><th>Decision</th></tr></thead><tbody>{recommendations.data.map(item=><tr key={item.id}><td>{String(item.action)}</td><td>{String(item.reason)}</td><td>{item.state}</td><td>{item.state==="ACTION_REQUIRED"?<div className="actions"><button className="btn primary compact" disabled={decide.isPending} onClick={()=>decide.mutate({id:item.id,action:"APPROVE"})}>Approve manually</button><button className="btn compact" disabled={decide.isPending} onClick={()=>decide.mutate({id:item.id,action:"WAIT"})}>Wait</button><button className="btn compact" disabled={decide.isPending} onClick={()=>decide.mutate({id:item.id,action:"REJECT"})}>Reject</button></div>:String(item.decision??"Recorded")}</td></tr>)}</tbody></table></div>:<p className="empty">No management recommendations.</p>}</article>
    <form className="card form-grid" onSubmit={event=>{event.preventDefault();monitor.mutate();}}><h2 className="full">Run deterministic monitoring</h2><label>Active trade<select required value={monitorInput.trade_id} onChange={e=>setMonitorInput({...monitorInput,trade_id:e.target.value})}><option value="">Select trade</option>{trades.data?.map(item=><option value={item.id} key={item.id}>{String((item.broker_position as Record<string,unknown>)?.instrument??item.id)}</option>)}</select></label><label>Current observed price<input required type="number" step="any" value={monitorInput.current_price} onChange={e=>setMonitorInput({...monitorInput,current_price:e.target.value})}/></label><button className="btn primary" disabled={monitor.isPending}>Evaluate management facts</button></form>
  </section>;
}
