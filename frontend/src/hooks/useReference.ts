import { api } from "../api/client";
import type { Category, Shelf, Supplier } from "../api/types";
import { useApi } from "./useApi";

/** Categories, suppliers and shelves for filters and forms. */
export function useReference() {
  return useApi(async (signal) => {
    const [categories, suppliers, shelves] = await Promise.all([
      api.get<Category[]>("/categories", undefined, signal),
      api.get<Supplier[]>("/suppliers", undefined, signal),
      api.get<Shelf[]>("/shelves", undefined, signal).catch(() => [] as Shelf[]),   // optional: forms work without
    ]);
    return { categories, suppliers, shelves };
  });
}
