/** A clickable column header for server-side sorting. Screen readers hear the sort direction. */
export function SortHeader({ label, field, sort, order, onSort, align = "left" }: {
  label: string;
  field: string;
  sort: string;
  order: "asc" | "desc";
  onSort: (field: string) => void;
  align?: "left" | "right";
}) {
  const active = sort === field;
  return (
    <th scope="col" aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}
        className={`py-2 pr-4 font-medium ${align === "right" ? "text-right" : "text-left"}`}>
      <button type="button" onClick={() => onSort(field)}
              className={`group inline-flex items-center gap-1 uppercase tracking-wider hover:text-slate-800 ${active ? "text-slate-900" : ""}`}>
        {label}
        <span aria-hidden className={`text-[10px] ${active ? "text-brand-600" : "text-slate-300 group-hover:text-slate-400"}`}>
          {active ? (order === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );
}
