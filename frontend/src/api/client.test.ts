import { afterEach, describe, expect, it, vi } from "vitest";

import { mockFetch } from "../test/fetchMock";
import { api, ApiError, buildUrl, errorMessage, setAuthToken, setUnauthorizedHandler } from "./client";

afterEach(() => {
  setAuthToken(null);
  setUnauthorizedHandler(null);
});

describe("buildUrl", () => {
  it("adds the prefix and skips empty query values", () => {
    expect(buildUrl("/products", { page: 2, search: "", category: undefined, active: true }))
      .toBe("/api/v1/products?page=2&active=true");
  });
});

describe("errorMessage", () => {
  it("uses the server's text", () => {
    expect(errorMessage({ detail: "Product 9 not found" }, 404)).toBe("Product 9 not found");
  });
  it("turns validation lists into readable field messages", () => {
    const body = { detail: [{ loc: ["body", "unit_price"], msg: "Input should be greater than or equal to 0" }] };
    expect(errorMessage(body, 422)).toBe("unit_price: Input should be greater than or equal to 0");
  });
  it("hides server internals on 500", () => {
    expect(errorMessage("Internal Server Error", 500)).toMatch(/server had a problem/);
  });
});

describe("apiRequest", () => {
  it("sends the token and JSON body", async () => {
    const { calls } = mockFetch({ "POST /products": () => ({ status: 201, body: { id: 1 } }) });
    setAuthToken("abc");
    await expect(api.post("/products", { sku: "X" })).resolves.toEqual({ id: 1 });
    const headers = calls[0].init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer abc");
    expect(calls[0].init?.body).toBe('{"sku":"X"}');
  });

  it("throws ApiError with the server message", async () => {
    mockFetch({ "POST /products": () => ({ status: 409, body: { detail: "SKU exists" } }) });
    await expect(api.post("/products", {})).rejects.toEqual(new ApiError(409, "SKU exists"));
  });

  it("calls the logout handler on 401 when logged in", async () => {
    mockFetch({ "GET /products": () => ({ status: 401, body: { detail: "Session expired" } }) });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    setAuthToken("expired");
    await expect(api.get("/products")).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledOnce();
  });

  it("reports when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.get("/health")).rejects.toMatchObject({ status: 0, message: expect.stringMatching(/reach the server/) });
  });
});
