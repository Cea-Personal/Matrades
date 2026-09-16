export type OverviewIconName = "account" | "trend" | "plan" | "terminal" | "calendar" | "research" | "idea" | "book" | "chevron" | "metals";

const paths: Record<OverviewIconName, React.ReactNode> = {
  account: <><circle cx="12" cy="7" r="4" /><path d="M4 22v-3a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v3" /></>,
  trend: <path d="m2 17 7-8 5 5 8-10M16 4h6v6" />,
  plan: <><path d="M8 4H4v18h16V4h-4M8 10h8M8 14h8M8 18h5" /><rect x="8" y="2" width="8" height="4" rx="1" /></>,
  terminal: <><rect x="2" y="3" width="20" height="18" rx="2" /><path d="m6 8 4 4-4 4m7 0h5" /></>,
  calendar: <><rect x="3" y="5" width="18" height="17" rx="2" /><path d="M7 2v6m10-6v6M3 11h18m-13 4h3v3H8z" /></>,
  research: <><path d="M14 3H4v18h16V9l-6-6Zm0 0v6h6M8 8h2M8 12h4M8 16h4" /><path d="m15 14 3 3-3 3" /></>,
  idea: <><path d="M9 19h6m-6 3h6M8 14a7 7 0 1 1 8 0c-1 1-1 2-1 3H9c0-1 0-2-1-3Z" /></>,
  book: <path d="M12 5v16M2 4c4-1 7-1 10 1 3-2 6-2 10-1v16c-4-1-7-1-10 1-3-2-6-2-10-1V4Z" />,
  chevron: <path d="m9 5 7 7-7 7" />,
  metals: <><path d="m8 3-3 7h14l-3-7H8Zm-5 10-2 7h10l-2-7H3Zm12 0-2 7h10l-2-7h-6Z" /><path d="M8 3v4h8M3 13v4h6m6-4v4h6" /></>,
};

export function OverviewIcon({ name }: { name: OverviewIconName }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
