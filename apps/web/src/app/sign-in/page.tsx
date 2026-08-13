import { AuthScreen } from "@/features/identity/AuthFlow";

type SignInPageProps = {
  searchParams: Promise<{ reason?: string | string[] }>;
};

export default async function SignInPage({ searchParams }: SignInPageProps) {
  const { reason } = await searchParams;
  const value = Array.isArray(reason) ? reason[0] : reason;
  const notices: Record<string, string> = {
    "session-expired": "Your session ended. Sign in again to continue; no pending action was completed.",
    "setup-unavailable": "Initial owner setup is no longer available. Sign in with the existing account.",
    "mfa-enrollment-required": "Complete sign-in first, then enroll your authenticator."
  };
  return <AuthScreen route="sign-in" notice={value ? notices[value] : undefined} />;
}
