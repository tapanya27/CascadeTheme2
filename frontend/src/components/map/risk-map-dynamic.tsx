"use client";

import dynamic from "next/dynamic";

import { LoadingState } from "@/components/states";

export const RiskMapDynamic = dynamic(
  () => import("@/components/map/risk-map").then((m) => m.RiskMap),
  {
    ssr: false,
    loading: () => <LoadingState label="Loading map…" />,
  }
);
