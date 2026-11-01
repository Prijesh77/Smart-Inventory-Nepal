import { api } from "../api/client";
import type { Category, Supplier } from "../api/types";
import { useApi } from "./useApi";

/** Categories and suppliers for filters and forms. */
export function useReference() {
  return useApi(async (signal) => {
    const [categories, suppliers] = await Promise.all([
      api.get<Category[]>("/categories", undefined, signal),
      api.get<Supplier[]>("/suppliers", undefined, signal),
    ]);
    return { categories, suppliers };
  });
}
