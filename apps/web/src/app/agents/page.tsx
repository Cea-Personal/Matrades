import { ModelProfiles } from "@/features/agents/ModelProfiles";
import { AgentConfiguration } from "@/features/agents/AgentConfiguration";
import { PromptConfiguration } from "@/features/agents/PromptConfiguration";
import { WorkspaceTabs } from "@/components/WorkspaceTabs";

export default function Page() {
  return <section className="section-stack"><header><p className="eyebrow">AI workspace</p><h1>Agents</h1><p className="muted">Check agent status, then configure models or prompts when needed.</p></header><WorkspaceTabs label="Agent sections" sections={[
    { id: "registry", label: "Agent status", content: <AgentConfiguration /> },
    { id: "models", label: "Model profiles", content: <ModelProfiles /> },
    { id: "prompts", label: "Prompts", content: <PromptConfiguration /> },
  ]} /></section>;
}
