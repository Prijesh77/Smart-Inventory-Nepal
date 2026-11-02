import { useEffect, useState } from "react";

import { api, ApiError } from "../../api/client";
import type { ModelStatus } from "../../api/types";
import { Button, ErrorMessage, Skeleton, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDateTime, fmtInt, fmtPct } from "../../lib/format";
import { MODEL_LABEL } from "./ForecastRuns";

/** The shop's own Random Forest: whether it is trained, how accurate it was, and a button to (re)train it. */
export function ShopModelCard({ canTrain, onTrained, pollMs = 2000 }:
  { canTrain: boolean; onTrained: () => void; pollMs?: number }) {
  const { data, error, loading, reload } = useApi((signal) => api.get<ModelStatus>("/forecasts/model", undefined, signal));
  const [starting, setStarting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const training = data?.training ?? false;

  useEffect(() => {                      // while training, check again every few seconds
    if (!training) return;
    const timer = setTimeout(reload, pollMs);
    return () => clearTimeout(timer);
  }, [training, data, pollMs, reload]);

  const [wasTraining, setWasTraining] = useState(false);
  useEffect(() => {
    if (wasTraining && !training) onTrained();
    setWasTraining(training);
  }, [training]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function train() {
    setStarting(true);
    setFailure(null);
    try {
      await api.post("/forecasts/model/train");
      reload();
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Training could not start");
    } finally {
      setStarting(false);
    }
  }

  if (error) return <ErrorMessage message={error} onRetry={reload} />;
  if (loading && !data) return <Skeleton variant="text" />;
  if (!data) return null;
  const rf = data.holdout_wape.random_forest_v1;
  const ma = data.holdout_wape.moving_avg_28;
  const share = Math.min(1, data.history_days / data.needed_days);

  return (
    <div className="space-y-3 text-sm text-slate-700">
      <p>
        <span className="font-medium text-slate-900">Forecasts use: {MODEL_LABEL[data.auto_uses] ?? data.auto_uses}.</span>{" "}
        {data.auto_reason?.replace(/^Auto: [^,]*, /, "Chosen ")}
      </p>
      {data.needs_retraining && (
        <p role="note" className="rounded-md bg-amber-50 p-3 text-amber-900">
          This Random Forest was trained before the forecasts learned about Nepali festivals. Retrain it so it can
          learn this shop&apos;s Dashain and Tihar patterns; until then the moving average is used.
        </p>
      )}
      {data.trained ? (
        <p>
          The Random Forest was trained on this shop&apos;s own sales{data.trained_at ? ` on ${fmtDateTime(data.trained_at)}` : ""}.
          {rf !== undefined && ma !== undefined && <> On the last 28 days its error was <strong>{fmtPct(rf)}</strong>, against{" "}
            <strong>{fmtPct(ma)}</strong> for the 28-day moving average (lower is better).</>}
          {" "}Retrain after importing new sales.
        </p>
      ) : (
        <div className="space-y-2">
          <p>
            The Random Forest learns this shop&apos;s own patterns once there are about {fmtInt(data.needed_days)} days
            (7 months) of sales; this shop has <strong>{fmtInt(data.history_days)}</strong>. Until then the moving average
            gives forecasts and reorder suggestions.
          </p>
          <div className="h-2 w-full max-w-md rounded-full bg-slate-100" role="progressbar" aria-label="Sales history for training"
               aria-valuemin={0} aria-valuemax={data.needed_days} aria-valuenow={data.history_days}>
            <div className="h-2 rounded-full bg-brand-500" style={{ width: `${share * 100}%` }} />
          </div>
        </div>
      )}
      {data.last_error && <ErrorMessage message={`The last training failed: ${data.last_error}`} />}
      {failure && <ErrorMessage message={failure} />}
      {canTrain && (
        <div className="flex items-center gap-3">
          <Button onClick={train} disabled={!data.can_train || training || starting}>
            {data.trained ? "Retrain model" : "Train model"}
          </Button>
          {training && <Spinner label="Training on this shop's sales… (usually under a minute)" />}
          {!data.can_train && !training && <span className="text-xs text-slate-500">Needs more sales history first.</span>}
        </div>
      )}
    </div>
  );
}
