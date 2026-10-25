"use client";

import dynamic from "next/dynamic";

import { LoadingState } from "@/components/states";

export const CaseMapDynamic = dynamic(
  () => import("@/components/map/case-map").then((m) => m.CaseMap),
  {
    ssr: false,
    loading: () => <LoadingState label="Loading impact map…" />,
  }
);
