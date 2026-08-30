import { AccountRules } from "@/features/configuration/AccountRules";
import { AutomationControls } from "@/features/configuration/AutomationControls";
import { SecuritySettings } from "@/features/security/SecuritySettings";

export default function Page() {
  return <><SecuritySettings /><AutomationControls /><AccountRules /></>;
}
