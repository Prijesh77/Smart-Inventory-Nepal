/** Types matching the API's responses (see http://127.0.0.1:8000/docs). Money and quantities
 * from NUMERIC columns arrive as strings (e.g. "4.20") so no precision is lost. */

export type Role = "admin" | "manager" | "viewer";

export interface Shop {
  id: number;
  name: string;
  is_demo: boolean;           // true = synthetic demo data
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  shop: Shop;                 // every user belongs to exactly one shop and sees only its data
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export type RunStatus = "pending" | "running" | "completed" | "failed";
export type StockStatus = "out_of_stock" | "low" | "ok" | "no_recent_demand";
export type RiskCategory =
  | "critical_stockout_risk" | "reorder_soon" | "healthy" | "excess_inventory" | "insufficient_data";

export interface TransactionRow {
  id: number;
  product_id: number;
  sku: string;
  txn_type: "initial" | "receipt" | "sale" | "adjustment" | "return";
  quantity: number;
  balance_after: number;
  reason: string | null;
  purchase_order_id: number | null;
  created_by_email: string | null;
  created_at: string;
}

export interface DashboardSummary {
  as_of: string | null;
  active_products: number;
  units_on_hand: number;
  inventory_value: number;
  products_without_cost: number;
  stock_status: Partial<Record<StockStatus, number>>;
  sales: {
    last_28_days_units: number;
    last_28_days_revenue: number;
    change_vs_previous_28_days: number | null;
    daily_trend: { date: string; units: number; revenue: number }[];
    /** Nepali fiscal year (1 Shrawan - end of Asar) up to the last sales day. */
    fiscal_year?: { label: string; start: string; end: string; units: number; revenue: number };
  } | null;
  recommendations: {
    run_id: number;
    created_at: string;
    counts: Partial<Record<RiskCategory, number>>;
    products_to_reorder: number;
    critical: number;
    excess: number;
    estimated_order_cost: number;
  } | null;
  forecast: {
    run_id: number;
    model_name: string;
    origin_date: string;
    horizon_days: number;
    predicted_units: Record<string, number>;
  } | null;
  purchase_orders: { open: number; open_order_value: number; drafts: number };
  recent_activity: TransactionRow[];
  simulated_fields: string[];
}

export interface RunInfo {
  id: number;
  status: RunStatus;
  error_message: string | null;
}

export interface StockItem {
  product_id: number;
  sku: string;
  name: string;
  category_code: string;
  on_hand: number;
  on_order: number;
  backorders: number;
  inventory_position: number;
  avg_daily_sales: number;
  days_of_cover: number | null;
  lead_time_days: number | null;
  stock_status: StockStatus;
  updated_at: string | null;
}

export type ManualMovement = "adjustment" | "sale" | "return";

export type ForecastModel = "auto" | "random_forest_v1" | "moving_avg_28";

export interface ForecastRun {
  id: number;
  model_name: ForecastModel;
  model_version: string;
  origin_date: string;
  horizon_days: number;
  status: RunStatus;
  params: { assumptions?: string[]; history_ends?: string; model_choice?: string } | null;
  metrics: { products?: number; total_units?: number; test_wape_28d?: number; test_bias_pct_28d?: number } | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface DayValue {
  date: string;
  units: number;
  is_available: boolean;
}

export interface ProductForecast {
  product_id: number;
  sku: string;
  run: ForecastRun;
  history: DayValue[];
  actual_in_window: DayValue[];
  forecast: { date: string; horizon: number; predicted_units: number }[];
  total_forecast: number;
}

export type ReviewStatus = "pending" | "approved" | "rejected" | "ordered";

export interface PolicySettings {
  service_level: number;
  review_period_days: number;
  ordering_cost: number;
  holding_cost_rate: number;
  min_cycle_days: number;
  max_cycle_days: number;
  excess_cover_days: number;
}

export interface RecommendationRun {
  id: number;
  forecast_run_id: number | null;
  policy_settings: PolicySettings;
  status: RunStatus;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  summary: { counts: Partial<Record<RiskCategory, number>>; total_suggested_order_cost: number } | null;
}

export interface Recommendation {
  id: number;
  product_id: number;
  sku: string;
  name: string;
  on_hand: string | null;
  inventory_position: string | null;
  lead_time_days: number;
  forecast_lead_time_demand: string | null;
  forecast_protection_demand: string | null;
  safety_stock: string | null;
  reorder_point: string | null;
  order_up_to: string | null;
  suggested_qty: number;
  estimated_order_cost: string | null;
  stockout_probability: string | null;
  days_of_cover: string | null;
  risk_category: RiskCategory;
  explanation: string;
  warnings: string[];
  review_status: ReviewStatus;
  reviewed_at: string | null;
}

export interface RecommendationPage extends Page<Recommendation> {
  run: RecommendationRun;
}

export interface PurchaseOrderLine {
  id: number;
  product_id: number;
  sku: string;
  name: string;
  quantity_ordered: number;
  quantity_received: number;
  quantity_outstanding: number;
  unit_cost: string | null;
  line_total: string | null;
  recommendation_id: number | null;
}

export type PurchaseOrderStatus = "draft" | "submitted" | "partially_received" | "received" | "cancelled";

export interface PurchaseOrder {
  id: number;
  po_number: string;
  supplier_id: number;
  supplier_code: string;
  supplier_name: string;
  status: PurchaseOrderStatus;
  expected_date: string | null;
  submitted_at: string | null;
  received_at: string | null;
  notes: string | null;
  created_at: string;
  lines: PurchaseOrderLine[];
  total_units: number;
  total_cost: string;
  note: string;
}

export interface CategoryPerformance {
  category: string;
  name: string;
  products: number;
  units_sold: number;
  revenue: number;
  avg_daily_units: number;
  units_on_hand: number;
  inventory_value: number;
  days_of_cover: number | null;
}

export interface WeeklyPoint {
  week_start: string;
  category: string;
  units: number;
}

export type SimPolicy = "baseline_demand_sd" | "engine_ma28" | "engine_rf";

export interface SimulationRow {
  policy: SimPolicy;
  service_level: number;
  demand_class: string;
  fill_rate: number | null;
  stockout_rate: number | null;
  units_lost: number;
  avg_inventory_value: number;
  n_orders: number;
  holding_cost: number;
  ordering_cost: number;
  total_cost: number;
  lost_margin: number;
}

export interface SimulationRun {
  id: number;
  name: string;
  status: RunStatus;
  params: { service_levels: number[]; ordering_cost: number; holding_cost_rate: number; uncertain_lead_time: boolean };
  results: {
    note: string;
    summary: SimulationRow[];
    matched_comparisons: { policy: SimPolicy; reference: SimPolicy; fill_rate: number | null; policy_value: number | null;
      reference_value: number | null; pct_diff: number | null }[];
    items: number;
    days: number;
  } | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface PolicyDefaults extends PolicySettings {
  forecast_horizons: number[];
}

export interface ImportError {
  row: number;
  column: string;
  message: string;
}

export type ImportType = "suppliers" | "products" | "opening_stock" | "sales";

/** GET /forecasts/model: the shop's own Random Forest and what "auto" forecasts use. */
export interface ModelStatus {
  trained: boolean;
  needs_retraining?: boolean;   // trained before the current features (e.g. festivals)
  trained_at: string | null;
  history_days: number;
  needed_days: number;
  can_train: boolean;
  training: boolean;
  last_error: string | null;
  holdout_wape: Partial<Record<"random_forest_v1" | "moving_avg_28", number>>;
  auto_uses: string;
  auto_reason: string | null;
}

export interface ImportPreview {
  import_type?: ImportType;
  rows_total: number;
  rows_valid: number;
  rows_invalid: number;
  would_add: number;
  would_replace: number;
  errors: ImportError[];
  errors_truncated: boolean;
  preview: Record<string, string | number | boolean | null>[];   // first valid rows; columns depend on the import type
  can_import: boolean;
}

export interface ImportJob {
  id: number;
  filename: string;
  import_type: string;
  status: RunStatus;
  rows_total: number;
  rows_valid: number;
  rows_invalid: number;
  errors: { errors?: ImportError[]; added?: number; replaced?: number; truncated?: boolean; categories_added?: number;
            units?: number } | null;
  created_at: string;
}

export interface Evaluation {
  model_name: string;
  model_version: string;
  period: "validation" | "test";
  horizon_days: number;
  demand_class: string;
  n_observations: number;
  mae: string | null;
  rmse: string | null;
  wape: string | null;
  bias_pct: string | null;
}

export interface Category {
  id: number;
  code: string;
  name: string;
}

export interface Supplier {
  id: number;
  code: string;
  name: string;
  lead_time_days: number;
  lead_time_sd_days: string;
  contact_email: string | null;
}

export type DemandClass = "smooth" | "erratic" | "intermittent" | "lumpy";

export interface Product {
  id: number;
  sku: string;
  name: string;
  category: Category;
  department: string | null;
  supplier: Supplier | null;
  unit_price: string;
  unit_cost: string | null;
  lead_time_days: number | null;
  effective_lead_time_days: number | null;
  min_order_qty: number;
  pack_size: number;
  demand_class: DemandClass | null;
  is_active: boolean;
  on_hand: number;
  created_at: string;
  updated_at: string;
}

/** Body for POST /products and PATCH /products/{id}. */
export interface ProductInput {
  sku?: string;
  name: string;
  category_code: string;
  department: string | null;
  supplier_id: number | null;
  unit_price: string;
  unit_cost: string | null;
  lead_time_days: number | null;
  min_order_qty: number;
  pack_size: number;
  is_active?: boolean;
}

export interface SalesHistory {
  product_id: number;
  sku: string;
  start: string;
  end: string;
  total_units: number;
  points: { sales_date: string; units: number; unit_price: string | null; is_available: boolean }[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
