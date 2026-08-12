import { AuthFlow } from "@/features/identity/AuthFlow";

export default function HomePage() {
  return (
    <section aria-labelledby="traderx-home">
      <h1 id="traderx-home">TraderX</h1>
      <p>Capital preservation first. Authenticate to access the Command Center.</p>
      <AuthFlow />
      <p>TraderX provides manual trading decision support only; it never submits an order.</p>
      <p>Market eligibility evidence precedes ranking, and a ranking never replaces an active market silently.</p>
    </section>
  );
}
