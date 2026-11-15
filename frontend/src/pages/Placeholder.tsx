import { Link } from "react-router-dom";

import { EmptyState, PageHeader } from "../components/ui";
import { t } from "../lib/i18n";

export function NotFound() {
  return (
    <>
      <PageHeader title={t("Page not found")} />
      <EmptyState title={t("There is no page at this address.")}>
        <Link to="/" className="text-brand-600 hover:underline">{t("Go to the overview")}</Link>
      </EmptyState>
    </>
  );
}
