import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider } from "../auth/AuthContext";
import { TEST_USER } from "./fetchMock";

/** Render a page as a logged-in user. Add "GET /auth/me" to the fetch mock via `meRoute(role)`. */
export function renderLoggedIn(ui: ReactElement, path = "/") {
  sessionStorage.setItem("smart-inventory.token", "test-token");
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </AuthProvider>,
  );
}

export function meRoute(role: "admin" | "manager" | "viewer" = "manager") {
  return { "GET /auth/me": () => ({ body: { ...TEST_USER, role } }) };
}
