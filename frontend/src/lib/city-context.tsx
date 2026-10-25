"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { api, type CityProfile } from "@/lib/api";

type CityContextValue = {
  cities: CityProfile[];
  cityId: string;
  setCityId: (id: string) => void;
  city: CityProfile | null;
  loading: boolean;
};

const CityContext = createContext<CityContextValue | null>(null);
const STORAGE_KEY = "critical1_city_id";

export function CityProvider({ children }: { children: React.ReactNode }) {
  const [cities, setCities] = useState<CityProfile[]>([]);
  const [cityId, setCityIdState] = useState("nagpur");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const saved =
      typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
    void api
      .cities()
      .then((res) => {
        setCities(res.items);
        const next = saved || res.default_city_id || "nagpur";
        setCityIdState(next);
      })
      .catch(() => {
        setCities([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const setCityId = useCallback((id: string) => {
    setCityIdState(id);
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, id);
    }
  }, []);

  const city = useMemo(
    () => cities.find((c) => c.id === cityId) || null,
    [cities, cityId]
  );

  const value = useMemo(
    () => ({ cities, cityId, setCityId, city, loading }),
    [cities, cityId, setCityId, city, loading]
  );

  return <CityContext.Provider value={value}>{children}</CityContext.Provider>;
}

export function useCity() {
  const ctx = useContext(CityContext);
  if (!ctx) {
    throw new Error("useCity must be used within CityProvider");
  }
  return ctx;
}
