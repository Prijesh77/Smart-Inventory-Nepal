import { useRef, type KeyboardEvent } from "react";

/** Accessible tabs: arrow keys move between tabs, the selected tab is announced. */
export function Tabs<T extends string>({ tabs, selected, onSelect, label }: {
  tabs: { id: T; label: string; count?: number }[];
  selected: T;
  onSelect: (id: T) => void;
  label: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(event: KeyboardEvent, index: number) {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    const next = (index + step + tabs.length) % tabs.length;
    refs.current[next]?.focus();
    onSelect(tabs[next].id);
  }

  return (
    <div role="tablist" aria-label={label} className="mb-6 flex gap-2 overflow-x-auto border-b border-slate-200">
      {tabs.map((tab, i) => {
        const active = tab.id === selected;
        return (
          <button
            key={tab.id}
            ref={(el) => { refs.current[i] = el; }}
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={active}
            aria-controls={`panel-${tab.id}`}
            tabIndex={active ? 0 : -1}
            onClick={() => onSelect(tab.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
              active ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800"}`}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span className={`ml-2 rounded-full px-2 py-0.5 text-xs tabular-nums ${active ? "bg-brand-100 text-brand-700" : "bg-slate-100 text-slate-600"}`}>
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: React.ReactNode }) {
  return <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`}>{children}</div>;
}
