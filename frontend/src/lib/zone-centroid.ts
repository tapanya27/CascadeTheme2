/** Approximate lon/lat centroid from a zone GeoJSON polygon (WGS84). */

export function zoneCentroidFromGeoJson(
  geojson: Record<string, unknown> | null | undefined
): { lon: number; lat: number } | null {
  if (!geojson || typeof geojson !== "object") return null;
  const root = geojson as {
    type?: string;
    coordinates?: unknown;
    geometry?: { type?: string; coordinates?: unknown };
  };
  const type = root.type === "Feature" ? root.geometry?.type : root.type;
  const coordinates =
    root.type === "Feature" ? root.geometry?.coordinates : root.coordinates;
  if (!type || !coordinates) return null;

  const rings: number[][] = [];
  if (type === "Polygon") {
    const poly = coordinates as number[][][];
    if (poly[0]) rings.push(...poly[0]);
  } else if (type === "MultiPolygon") {
    const mp = coordinates as number[][][][];
    for (const poly of mp) {
      if (poly[0]) rings.push(...poly[0]);
    }
  } else {
    return null;
  }

  let sumLon = 0;
  let sumLat = 0;
  let n = 0;
  for (const pt of rings) {
    if (Array.isArray(pt) && pt.length >= 2) {
      sumLon += Number(pt[0]);
      sumLat += Number(pt[1]);
      n += 1;
    }
  }
  if (n === 0) return null;
  return { lon: sumLon / n, lat: sumLat / n };
}
