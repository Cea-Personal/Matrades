import { Connections } from "@/features/configuration/Connections";
import { ProviderBindings } from "@/features/configuration/ProviderBindings";
import { YouTubeDiscovery } from "@/features/configuration/YouTubeDiscovery";
import { WorkspaceTabs } from "@/components/WorkspaceTabs";

export default function Page() { return <section className="section-stack"><header><p className="eyebrow">Provider boundary</p><h1>Connections & data sources</h1><p className="muted">Manage providers, account bindings and video discovery in one place.</p></header><WorkspaceTabs label="Connection sections" sections={[
  { id: "sources", label: "Data sources", content: <Connections /> },
  { id: "bindings", label: "Account bindings", content: <ProviderBindings /> },
  { id: "youtube", label: "YouTube discovery", content: <YouTubeDiscovery /> },
]} /></section>; }
