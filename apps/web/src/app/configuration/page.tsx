import { AccountRules } from "@/features/configuration/AccountRules";
import { AutomationControls } from "@/features/configuration/AutomationControls";
import { SecuritySettings } from "@/features/security/SecuritySettings";
import { WorkspaceTabs } from "@/components/WorkspaceTabs";

export default function Page() {
  return <section className="section-stack"><header><p className="eyebrow">Workspace settings</p><h1>Configuration</h1><p className="muted">Manage accounts, safety controls and authentication separately.</p></header><WorkspaceTabs label="Configuration sections" sections={[
    { id: "accounts", label: "Accounts & risk", content: <AccountRules /> },
    { id: "automation", label: "Permissions & safety", content: <AutomationControls /> },
    { id: "security", label: "Security", content: <SecuritySettings /> },
  ]} /></section>;
}
