import { useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import type { ForecastRun, PolicySettings, RecommendationRun } from "../../api/types";
import { SelectField, TextField } from "../../components/fields";
import { Button, ErrorMessage, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDate } from "../../lib/format";
import { waitForRun } from "../../lib/runs";
import { MODEL_LABEL } from "../forecasts/ForecastRuns";

/** New recommendation run from a completed forecast, optionally with different policy settings. */
export function NewRunForm({ defaults, onDone, onCancel, pollMs }: {
  defaults: PolicySettings | null;
  onDone: (run: RecommendationRun) => void;
  onCancel: () => void;
  pollMs?: number;
}) {
  const forecasts = useApi((signal) => api.get<ForecastRun[]>("/forecasts/runs", { limit: 50 }, signal));
  const completed = forecasts.data?.filter((r) => r.status === "completed") ?? [];
  const [forecastId, setForecastId] = useState("");
  const [serviceLevel, setServiceLevel] = useState(String(Math.round((defaults?.service_level ?? 0.95) * 100)));
  const [review, setReview] = useState(String(defaults?.review_period_days ?? 7));
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const sl = Number(serviceLevel);
    const rp = Number(review);
    if (!(sl >= 50 && sl <= 99.9)) return setError("Service level must be between 50% and 99.9%");
    if (!Number.isInteger(rp) || rp < 1 || rp > 28) return setError("Review period must be 1–28 whole days");
    setError(null);
    setStatus("Calculating recommendations for every product…");
    try {
      const run = await api.post<RecommendationRun>("/recommendations/runs", {
        forecast_run_id: forecastId ? Number(forecastId) : null, service_level: sl / 100, review_period_days: rp });
      await waitForRun("/recommendations/runs", run.id, pollMs);
      onDone(await api.get<RecommendationRun>(`/recommendations/runs/${run.id}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create recommendations");
    } finally {
      setStatus(null);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {error && <ErrorMessage message={error} />}
      <SelectField id="forecast-run" label="Forecast to use" value={forecastId} onChange={(e) => setForecastId(e.target.value)}>
        <option value="">Latest completed forecast</option>
        {completed.map((r) => (
          <option key={r.id} value={r.id}>
            #{r.id} · {MODEL_LABEL[r.model_name]} · {r.horizon_days} days from {fmtDate(r.origin_date)}
          </option>
        ))}
      </SelectField>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <TextField id="service-level" label="Service level target (%)" inputMode="decimal" value={serviceLevel}
                   onChange={(e) => setServiceLevel(e.target.value)}
                   hint="Chance of not running out in each period. Higher = more safety stock." />
        <TextField id="review-period" label="Review period (days)" inputMode="numeric" value={review}
                   onChange={(e) => setReview(e.target.value)} hint="How often stock is checked and orders placed." />
      </div>
      <p className="text-xs text-slate-500">
        The forecast must cover the lead time plus the review period (e.g. 14 + 7 = 21 days), otherwise those items get
        "insufficient data". Ordering and holding costs are the assumptions set in Settings.
      </p>
      <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-4">
        {status && <Spinner label={status} />}
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={!!status}>{status ? "Running…" : "Create recommendations"}</Button>
      </div>
    </form>
  );
}
