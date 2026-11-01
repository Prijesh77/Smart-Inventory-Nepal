import { vi } from "vitest";

type Handler = (url: string, init?: RequestInit) => { status?: number; body: unknown };

/** Replace fetch with a fake that answers from `routes` ("METHOD /path" -> handler). */
export function mockFetch(routes: Record<string, Handler>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const key = `${init?.method ?? "GET"} ${url.split("?")[0].replace("/api/v1", "")}`;
    const handler = routes[key];
    if (!handler) throw new Error(`No mock for ${key}`);
    const { status = 200, body } = handler(url, init);
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, calls };
}

export const TEST_USER = {
  id: 1, email: "manager@test.local", full_name: "Test Manager", role: "manager", is_active: true,
  created_at: "2026-10-29T00:00:00Z", shop: { id: 1, name: "Test Kirana Pasal", is_demo: false },
};
