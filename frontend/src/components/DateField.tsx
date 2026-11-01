import { useState } from "react";

import { fmtDate } from "../lib/format";
import { bsInputValue, dateStyle, parseBs } from "../lib/nepaliDate";
import { TextField } from "./fields";

/**
 * A date the user types in the chosen calendar. `value` and `onChange` always use AD "YYYY-MM-DD", like the API.
 * In BS styles the user types e.g. 2083-07-15 and sees the AD date below; onChange(null) means "not a valid date
 * yet", so the form can refuse to send it. In AD style it is the browser's own date picker.
 */
export function DateField({ id, label, value, onChange, max, hint }: {
  id: string; label: string; value: string; onChange: (iso: string | null) => void; max?: string; hint?: string;
}) {
  const bs = dateStyle() !== "ad";
  const [text, setText] = useState(() => (bs ? bsInputValue(value) : value));
  const [error, setError] = useState<string | undefined>();

  if (!bs) {
    return <TextField id={id} label={label} type="date" value={value} max={max} hint={hint}
                      onChange={(e) => onChange(e.target.value)} />;
  }

  function change(next: string) {
    setText(next);
    if (!next.trim()) {
      setError(undefined);
      return onChange("");
    }
    const iso = parseBs(next);
    if (!iso) {
      setError("Not a real BS date; type it like 2083-07-15 (year-month-day)");
      return onChange(null);
    }
    if (max && iso > max) {
      setError(`Must be on or before ${fmtDate(max)}`);
      return onChange(null);
    }
    setError(undefined);
    onChange(iso);
  }

  const parsed = text.trim() ? parseBs(text) : null;
  const shown = parsed && !error ? `= ${new Date(`${parsed}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })} (AD)${hint ? `. ${hint}` : ""}` : hint;
  return (
    <TextField id={id} label={`${label} (BS)`} value={text} placeholder="2083-07-15" inputMode="numeric"
               error={error} hint={shown} onChange={(e) => change(e.target.value)} />
  );
}
