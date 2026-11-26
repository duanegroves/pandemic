import { createContext, useContext, useMemo } from "react";
import type { CityMeta, Meta } from "./types";

export const MetaContext = createContext<Meta | null>(null);

export function useMeta(): Meta {
  const m = useContext(MetaContext);
  if (!m) throw new Error("meta not loaded");
  return m;
}

export function useCityMap(): Map<string, CityMeta> {
  const m = useMeta();
  return useMemo(() => new Map(m.cities.map((c) => [c.name, c])), [m]);
}
