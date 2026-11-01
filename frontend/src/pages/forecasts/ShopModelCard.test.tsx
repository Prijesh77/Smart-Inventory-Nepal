import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ModelStatus } from "../../api/types";
import { mockFetch } from "../../test/fetchMock";
import { ShopModelCard } from "./ShopModelCard";

const YOUNG: ModelStatus = {
  trained: false, trained_at: null, history_days: 60, needed_days: 203, can_train: false, training: false,
  last_error: null, holdout_wape: {}, auto_uses: "moving_avg_28",
  auto_reason: "Auto: 28-day moving average, because this shop's Random Forest is not trained yet.",
};
const TRAINED: ModelStatus = {
  ...YOUNG, trained: true, trained_at: "2026-11-01T06:00:00Z", history_days: 548, can_train: true,
  holdout_wape: { random_forest_v1: 0.424, moving_avg_28: 0.435 }, auto_uses: "random_forest_v1",
  auto_reason: "Auto: this shop's Random Forest, the more accurate model on the last 28 days.",
};

describe("ShopModelCard", () => {
  it("tells a young shop how much history it has and why the moving average is used", async () => {
    mockFetch({ "GET /forecasts/model": () => ({ body: YOUNG }) });
    render(<ShopModelCard canTrain onTrained={() => undefined} />);
    expect(await screen.findByText("Forecasts use: 28-day moving average.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Sales history for training" })).toHaveAttribute("aria-valuenow", "60");
    expect(screen.getByRole("button", { name: "Train model" })).toBeDisabled();
    expect(screen.getByText("Needs more sales history first.")).toBeInTheDocument();
  });

  it("retrains, waits for the training to finish, then reports it", async () => {
    let state: ModelStatus = TRAINED;
    const onTrained = vi.fn();
    const { calls } = mockFetch({
      "GET /forecasts/model": () => ({ body: state }),
      "POST /forecasts/model/train": () => { state = { ...TRAINED, training: true }; return { status: 202, body: { training: true } }; },
    });
    render(<ShopModelCard canTrain onTrained={onTrained} pollMs={20} />);
    expect(await screen.findByText(/its error was/)).toHaveTextContent("42.4%");
    await userEvent.click(screen.getByRole("button", { name: "Retrain model" }));
    expect(await screen.findByText(/Training on this shop's sales/)).toBeInTheDocument();
    state = { ...TRAINED, trained_at: "2026-11-02T06:00:00Z" };              // the background job finishes
    await vi.waitFor(() => expect(onTrained).toHaveBeenCalledTimes(1));
    expect(calls.filter((c) => c.url.endsWith("/forecasts/model/train"))).toHaveLength(1);
  });

  it("asks for retraining when the forest was trained before the festival features", async () => {
    mockFetch({ "GET /forecasts/model": () => ({ body: { ...TRAINED, needs_retraining: true, auto_uses: "moving_avg_28" } }) });
    render(<ShopModelCard canTrain onTrained={() => undefined} />);
    expect(await screen.findByRole("note")).toHaveTextContent("trained before the forecasts learned about Nepali festivals");
    expect(screen.getByRole("button", { name: "Retrain model" })).toBeEnabled();
  });

  it("viewers see the status without a button", async () => {
    mockFetch({ "GET /forecasts/model": () => ({ body: TRAINED }) });
    render(<ShopModelCard canTrain={false} onTrained={() => undefined} />);
    expect(await screen.findByText("Forecasts use: Random Forest.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
