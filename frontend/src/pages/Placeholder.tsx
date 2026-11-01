import { Link } from "react-router-dom";

import { EmptyState, PageHeader } from "../components/ui";

export function NotFound() {
  return (
    <>
      <PageHeader title="Page not found" />
      <EmptyState title="There is no page at this address.">
        <Link to="/" className="text-brand-600 hover:underline">Go to the overview</Link>
      </EmptyState>
    </>
  );
}
