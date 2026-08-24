import { ApprovalInbox } from "@/features/approvals/ApprovalInbox";
import { AuditLog } from "@/features/audit/AuditLog";
import { HealthDashboard } from "@/features/health/HealthDashboard";
import { JournalTimeline } from "@/features/journal/JournalTimeline";
import { NotificationCenter } from "@/features/notifications/NotificationCenter";
import { PerformanceDashboard } from "@/features/performance/PerformanceDashboard";

export default function Page() { return <section className="section-stack"><ApprovalInbox/><JournalTimeline/><AuditLog/><PerformanceDashboard/><NotificationCenter/><HealthDashboard/></section>; }
