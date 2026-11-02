import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "../App";
import { mockFetch, TEST_USER } from "../test/fetchMock";
import { AuthProvider } from "./AuthContext";

function renderApp(path = "/") {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("login flow", () => {
  it("sends visitors who are not logged in to the login page", async () => {
    mockFetch({});
    renderApp("/inventory");
    expect(await screen.findByRole("heading", { name: "Smart Inventory Nepal" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("logs in and returns to the page that was asked for", async () => {
    const { calls } = mockFetch({
      "POST /auth/login": () => ({ body: { access_token: "tok", token_type: "bearer", expires_in: 3600, user: TEST_USER } }),
    });
    renderApp("/inventory");
    await userEvent.type(await screen.findByLabelText("Email"), "manager@test.local");
    await userEvent.type(screen.getByLabelText("Password"), "test-password-123");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("heading", { name: "Inventory" })).toBeInTheDocument();
    expect(screen.getByText("Test Manager")).toBeInTheDocument();
    expect(String(calls[0].init?.body)).toBe("username=manager%40test.local&password=test-password-123");
    expect(sessionStorage.getItem("smart-inventory.token")).toBe("tok");
  });

  it("shows the server's message when login fails", async () => {
    mockFetch({ "POST /auth/login": () => ({ status: 401, body: { detail: "Incorrect email or password" } }) });
    renderApp("/login");
    await userEvent.type(screen.getByLabelText("Email"), "x@test.local");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password");
  });

  it("restores a stored session after a page refresh", async () => {
    sessionStorage.setItem("smart-inventory.token", "stored");
    mockFetch({ "GET /auth/me": () => ({ body: TEST_USER }), "GET /dashboard/summary": () => ({ status: 503, body: {} }) });
    renderApp("/");
    // The Overview page is loaded on demand, so allow a little longer than the default 1 s.
    expect(await screen.findByRole("heading", { name: "Overview" }, { timeout: 5000 })).toBeInTheDocument();
  });

  it("shows which shop the data belongs to, and labels a demo shop's data as synthetic", async () => {
    sessionStorage.setItem("smart-inventory.token", "stored");
    mockFetch({ "GET /auth/me": () => ({ body: TEST_USER }), "GET /dashboard/summary": () => ({ status: 503, body: {} }) });
    const { unmount } = renderApp("/");
    const shop = within((await screen.findAllByRole("region", { name: "Shop" }, { timeout: 5000 }))[0]);
    expect(shop.getByText("Test Kirana Pasal")).toBeInTheDocument();
    expect(shop.queryByText(/Demo shop:/)).toBeNull();
    unmount();

    const demo = { ...TEST_USER, shop: { id: 2, name: "Demo Kirana Pasal (synthetic data)", is_demo: true } };
    mockFetch({ "GET /auth/me": () => ({ body: demo }), "GET /dashboard/summary": () => ({ status: 503, body: {} }) });
    renderApp("/");
    const demoShop = within((await screen.findAllByRole("region", { name: "Shop" }, { timeout: 5000 }))[0]);
    expect(demoShop.getByText(/Demo shop:/)).toBeInTheDocument();
  });

  it("drops an expired stored session and asks to log in", async () => {
    sessionStorage.setItem("smart-inventory.token", "expired");
    mockFetch({ "GET /auth/me": () => ({ status: 401, body: { detail: "Session expired, please log in again" } }) });
    renderApp("/");
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent(/session has expired/i);
    expect(sessionStorage.getItem("smart-inventory.token")).toBeNull();
  });

  it("logs out", async () => {
    sessionStorage.setItem("smart-inventory.token", "stored");
    mockFetch({ "GET /auth/me": () => ({ body: TEST_USER }) });
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: /Test Manager/ }));      // open the user menu
    await userEvent.click(screen.getByRole("button", { name: "Log out" }));
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    expect(sessionStorage.getItem("smart-inventory.token")).toBeNull();
  });
});
