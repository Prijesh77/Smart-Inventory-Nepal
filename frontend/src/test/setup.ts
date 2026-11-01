import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { setDateStyle } from "../lib/nepaliDate";

// jsdom has no layout engine; charts only need ResizeObserver to exist.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

// Page tests check AD dates; BS display has its own tests (lib/nepaliDate.test.ts).
beforeEach(() => setDateStyle("ad", false));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sessionStorage.clear();
});
