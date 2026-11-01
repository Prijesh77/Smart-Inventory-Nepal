import { api } from "../../api/client";
import type { PurchaseOrder, RecommendationPage } from "../../api/types";

/** Every approved recommendation id in one run (the list is paged, at most 100 per page). */
export async function approvedIds(runId: number): Promise<number[]> {
  const ids: number[] = [];
  for (let page = 1; ; page++) {
    const result = await api.get<RecommendationPage>("/recommendations",
      { run_id: runId, review_status: "approved", page, page_size: 100 });
    ids.push(...result.items.map((r) => r.id));
    if (page >= result.pages) return ids;
  }
}

/** Draft purchase orders (one per supplier) from this run's approved recommendations. */
export async function createDraftOrders(runId: number): Promise<PurchaseOrder[]> {
  const ids = await approvedIds(runId);
  if (!ids.length) return [];
  return api.post<PurchaseOrder[]>("/purchase-orders/from-recommendations", { recommendation_ids: ids });
}
