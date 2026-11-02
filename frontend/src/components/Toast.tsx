import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { Icon } from "./Icons";

/**
 * Short confirmations ("Settings saved", "Imported products.xlsx") that slide in at the bottom-right and
 * disappear after a few seconds. Messages the user must act on (errors, links to follow) stay on the page instead.
 */
type Tone = "success" | "info";
interface Toast { id: number; tone: Tone; message: string }
type Show = (message: string, tone?: Tone) => void;

const ToastContext = createContext<Show | null>(null);
const LIFETIME_MS = 5000;
let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((t) => t.id !== id)), []);
  const show = useCallback<Show>((message, tone = "success") => {
    const id = nextId++;
    setToasts((all) => [...all.slice(-2), { id, tone, message }]);         // at most 3 at a time
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-2 sm:left-auto sm:right-6">
        {toasts.map((t) => <ToastItem key={t.id} toast={t} onClose={() => dismiss(t.id)} />)}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onClose, LIFETIME_MS);
    return () => clearTimeout(timer);
  }, [onClose]);
  const ToneIcon = toast.tone === "success" ? Icon.check : Icon.info;
  return (
    <div role="status"
         className="toast-in pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl bg-slate-900 px-4 py-3 text-sm text-white shadow-lg shadow-slate-900/20 ring-1 ring-white/10">
      <ToneIcon className={`mt-0.5 h-4 w-4 shrink-0 ${toast.tone === "success" ? "text-emerald-400" : "text-brand-300"}`} />
      <p className="min-w-0 flex-1 leading-relaxed">{toast.message}</p>
      <button type="button" onClick={onClose} aria-label="Dismiss message"
              className="-mr-1 rounded p-0.5 text-slate-400 hover:bg-white/10 hover:text-white">
        <Icon.close className="h-4 w-4" />
      </button>
    </div>
  );
}

/** Show a toast. Outside a ToastProvider (some unit tests) it does nothing. */
export function useToast(): Show {
  return useContext(ToastContext) ?? (() => undefined);
}
