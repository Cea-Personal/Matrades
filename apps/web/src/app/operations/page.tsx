import { ApprovalInbox } from "@/features/approvals/ApprovalInbox";
import { AuditLog } from "@/features/audit/AuditLog";
import { HealthDashboard } from "@/features/health/HealthDashboard";
import { JournalTimeline } from "@/features/journal/JournalTimeline";
import { NotificationCenter } from "@/features/notifications/NotificationCenter";
import { PerformanceDashboard } from "@/features/performance/PerformanceDashboard";
import { WorkspaceTabs } from "@/components/WorkspaceTabs";

export default function Page() { return <section className="section-stack"><header><p className="eyebrow">Operational workspace</p><h1>Operations</h1><p className="muted">Monitor execution and dependencies; inspect history only when needed.</p></header><HealthDashboard /><WorkspaceTabs label="Operations sections" sections={[
  { id: "execution", label: "Execution", content: <ApprovalInbox /> },
  { id: "journal", label: "Journal", content: <JournalTimeline /> },
  { id: "performance", label: "Performance", content: <PerformanceDashboard /> },
  { id: "notifications", label: "Notifications", content: <NotificationCenter /> },
  { id: "audit", label: "Audit log", content: <AuditLog /> },
]} /></section>; }
