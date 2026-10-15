import { lazy, Suspense, useEffect, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import type { MapProps } from "./LeafletMap";

const LeafletMap = lazy(() => import("./LeafletMap"));

export function MapView(props: MapProps & { className?: string }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const fallback = <Skeleton className="h-full w-full rounded-none" />;
  return (
    <div className={`relative isolate overflow-hidden rounded-xl border ${props.className ?? "h-[420px]"}`}>
      {mounted ? <Suspense fallback={fallback}><LeafletMap {...props} /></Suspense> : fallback}
    </div>
  );
}
