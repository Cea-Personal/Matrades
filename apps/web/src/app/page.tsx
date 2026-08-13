import { AuthEntryLinks } from "@/features/identity/AuthFlow";

export default function HomePage() {
  return (
    <section className="landing" aria-labelledby="traderx-home">
      <div className="landing-copy">
        <p className="eyebrow">Manual trading decision support</p>
        <h1 id="traderx-home">Make the evidence earn the trade.</h1>
        <p className="lede">Authenticate to access the Command Center. TraderX keeps market eligibility, portfolio risk, and your final manual decision in the right order.</p>
        <div className="principles">
          <p>Capital preservation first. No order is ever submitted by TraderX.</p>
          <p>Market eligibility evidence precedes ranking, and a ranking never replaces an active market silently.</p>
        </div>
      </div>
      <aside className="entry-panel" aria-labelledby="entry-heading">
        <h2 id="entry-heading">Enter TraderX</h2>
        <p>New installation? Create the first owner account, then secure it with your authenticator.</p>
        <AuthEntryLinks />
      </aside>
    </section>
  );
}
