"use client";

import dynamic from "next/dynamic";
import { LoadingState } from "@/components/states";

export const ImpactMapDynamic = dynamic(
  () => import("@/components/map/impact-map").then((m) => m.ImpactMap),
  {
    ssr: false,
    loading: () => <LoadingState label="Loading spatial impact map…" />,
  }
);
