import { fmtInt } from "../lib/format";
import { Button } from "./ui";

export function Pagination({ page, pages, total, pageSize, onPage }:
  { page: number; pages: number; total: number; pageSize: number; onPage: (page: number) => void }) {
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(total, page * pageSize);
  return (
    <nav aria-label="Pages" className="mt-2 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4 text-sm">
      <p className="text-slate-500">
        Showing <span className="font-medium text-slate-700 tabular-nums">{fmtInt(first)}–{fmtInt(last)} of {fmtInt(total)}</span>
      </p>
      <div className="flex items-center gap-2">
        <Button variant="secondary" onClick={() => onPage(page - 1)} disabled={page <= 1}>Previous</Button>
        <span className="px-1 text-slate-600 tabular-nums">Page {page} of {pages}</span>
        <Button variant="secondary" onClick={() => onPage(page + 1)} disabled={page >= pages}>Next</Button>
      </div>
    </nav>
  );
}
