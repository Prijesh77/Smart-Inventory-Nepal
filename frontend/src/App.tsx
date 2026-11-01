import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { CurrencyProvider } from "./auth/CurrencyContext";
import { RequireAuth } from "./auth/RequireAuth";
import { Layout } from "./components/Layout";
import { Spinner } from "./components/ui";
import { LoginPage } from "./pages/LoginPage";
import { NotFound } from "./pages/Placeholder";

// Each page is downloaded only when it is first opened, so the login page loads fast
// and the chart library is not part of the first download.
const named = <K extends string>(loader: () => Promise<Record<K, React.ComponentType>>, name: K) =>
  lazy(() => loader().then((m) => ({ default: m[name] })));

const OverviewPage = named(() => import("./pages/OverviewPage"), "OverviewPage");
const ProductsPage = named(() => import("./pages/products/ProductsPage"), "ProductsPage");
const ProductDetailPage = named(() => import("./pages/products/ProductDetailPage"), "ProductDetailPage");
const InventoryPage = named(() => import("./pages/inventory/InventoryPage"), "InventoryPage");
const ForecastsPage = named(() => import("./pages/forecasts/ForecastsPage"), "ForecastsPage");
const RecommendationsPage = named(() => import("./pages/recommendations/RecommendationsPage"), "RecommendationsPage");
const PurchaseOrdersPage = named(() => import("./pages/purchase-orders/PurchaseOrdersPage"), "PurchaseOrdersPage");
const PurchaseOrderDetailPage = named(() => import("./pages/purchase-orders/PurchaseOrderDetailPage"), "PurchaseOrderDetailPage");
const AnalyticsPage = named(() => import("./pages/analytics/AnalyticsPage"), "AnalyticsPage");
const SettingsPage = named(() => import("./pages/settings/SettingsPage"), "SettingsPage");

const page = (element: JSX.Element) => <Suspense fallback={<Spinner label="Loading page…" />}>{element}</Suspense>;

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route path="/" element={page(<OverviewPage />)} />
        <Route path="/products" element={page(<ProductsPage />)} />
        <Route path="/products/:id" element={page(<ProductDetailPage />)} />
        <Route path="/inventory" element={page(<InventoryPage />)} />
        <Route path="/forecasts" element={page(<ForecastsPage />)} />
        <Route path="/recommendations" element={page(<RecommendationsPage />)} />
        <Route path="/purchase-orders" element={page(<PurchaseOrdersPage />)} />
        <Route path="/purchase-orders/:id" element={page(<PurchaseOrderDetailPage />)} />
        <Route path="/analytics" element={page(<AnalyticsPage />)} />
        <Route path="/settings" element={page(<SettingsPage />)} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <CurrencyProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </CurrencyProvider>
    </AuthProvider>
  );
}
