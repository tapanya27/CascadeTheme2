import { Suspense } from "react";

import { LoadingState } from "@/components/states";

import MapPageInner from "./page-inner";

export default function MapPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading map…" />}>
      <MapPageInner />
    </Suspense>
  );
}
