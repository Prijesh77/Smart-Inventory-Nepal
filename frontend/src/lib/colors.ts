/**
 * Chart colours, one meaning each, used the same way on every page.
 * Status colours (red/amber/green) are reserved for states and always shown
 * with a text label, never colour alone. Series colours are from the
 * Okabe-Ito palette, which stays distinguishable with colour-vision deficiency.
 */
import type { RiskCategory, StockStatus } from "../api/types";

export const SERIES = {
  blue: "#0072B2",
  orange: "#E69F00",
  green: "#009E73",
  pink: "#CC79A7",
  sky: "#56B4E9",
  gray: "#94A3B8",
};

export const STATUS = {
  critical: "#DC2626",
  warning: "#D97706",
  good: "#059669",
  info: "#2563EB",
  neutral: "#94A3B8",
};

export const STOCK_STATUS_STYLE: Record<StockStatus, { label: string; color: string; tone: "red" | "amber" | "green" | "gray" }> = {
  out_of_stock: { label: "Out of stock", color: STATUS.critical, tone: "red" },
  low: { label: "Low", color: STATUS.warning, tone: "amber" },
  ok: { label: "OK", color: STATUS.good, tone: "green" },
  no_recent_demand: { label: "No recent sales", color: STATUS.neutral, tone: "gray" },
};

export const RISK_STYLE: Record<RiskCategory, { label: string; color: string; tone: "red" | "amber" | "green" | "blue" | "gray" }> = {
  critical_stockout_risk: { label: "Critical stockout risk", color: STATUS.critical, tone: "red" },
  reorder_soon: { label: "Reorder soon", color: STATUS.warning, tone: "amber" },
  healthy: { label: "Healthy", color: STATUS.good, tone: "green" },
  excess_inventory: { label: "Excess inventory", color: STATUS.info, tone: "blue" },
  insufficient_data: { label: "Insufficient data", color: STATUS.neutral, tone: "gray" },
};

export const GRID = "#EEF2F6";            // soft gridlines: they guide the eye without competing with the data
export const AXIS = "#64748B";

/** One tooltip look for every chart: white card, rounded, soft shadow. Spread into <Tooltip {...TOOLTIP} />. */
export const TOOLTIP = {
  contentStyle: { borderRadius: 10, border: "1px solid #E2E8F0", boxShadow: "0 8px 24px rgb(15 23 42 / 0.08)",
    padding: "8px 12px", fontSize: 12 },
  labelStyle: { color: "#0F172A", fontWeight: 600, marginBottom: 4 },
  itemStyle: { padding: 0 },
  cursor: { stroke: "#CBD5E1", strokeDasharray: "4 4" },
};
