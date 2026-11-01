import { api, ApiError } from "../api/client";
import type { RunInfo } from "../api/types";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Background jobs (forecasts, recommendations) return 202 at once.
 * Ask for the run's status until it is completed or failed.
 */
export async function waitForRun(path: string, id: number, intervalMs = 1500, maxWaitMs = 180_000): Promise<RunInfo> {
  const started = Date.now();
  for (;;) {
    const run = await api.get<RunInfo>(`${path}/${id}`);
    if (run.status === "completed") return run;
    if (run.status === "failed") throw new ApiError(500, run.error_message ?? "The run failed");
    if (Date.now() - started > maxWaitMs) throw new ApiError(504, "The run is taking too long; check again later");
    await sleep(intervalMs);
  }
}

/** Forecast all products (28 days, the shop's best available model), then create recommendations from that forecast. */
export async function runPlanning(onStep: (step: string) => void, intervalMs?: number): Promise<void> {
  onStep("Forecasting demand for every product…");
  const forecast = await api.post<RunInfo>("/forecasts/runs", { model_name: "auto", horizon_days: 28 });
  await waitForRun("/forecasts/runs", forecast.id, intervalMs);
  onStep("Calculating reorder recommendations…");
  const recs = await api.post<RunInfo>("/recommendations/runs", { forecast_run_id: forecast.id });
  await waitForRun("/recommendations/runs", recs.id, intervalMs);
}
