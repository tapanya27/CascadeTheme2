import { afterEach, describe, expect, it, vi } from "vitest";

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("throws when NEXT_PUBLIC_API_BASE_URL is missing", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    const { api } = await import("@/lib/api");
    await expect(api.health()).rejects.toThrow(/NEXT_PUBLIC_API_BASE_URL/);
  });

  it("surfaces ApiError on non-OK responses", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: "Server Error",
        text: async () => JSON.stringify({ detail: "boom" }),
      })
    );
    const { api, ApiError } = await import("@/lib/api");
    await expect(api.health()).rejects.toBeInstanceOf(ApiError);
    await expect(api.health()).rejects.toMatchObject({
      message: "boom",
      status: 500,
    });
  });

  it("parses successful JSON", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        statusText: "OK",
        text: async () =>
          JSON.stringify({
            status: "ok",
            version: "0.3.0",
            database: "connected",
            postgis: true,
            postgis_version: "3.4",
            error: null,
          }),
      })
    );
    const { api } = await import("@/lib/api");
    const health = await api.health();
    expect(health.status).toBe("ok");
    expect(health.postgis).toBe(true);
  });

  it("appends city_id on map and zone requests", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () =>
        JSON.stringify({
          city_id: "kathmandu",
          zones: { type: "FeatureCollection", features: [] },
          hazards: { type: "FeatureCollection", features: [] },
          infrastructure: { type: "FeatureCollection", features: [] },
          generated_at: new Date().toISOString(),
          notes: [],
        }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const { api } = await import("@/lib/api");
    await api.mapLayers("kathmandu");
    await api.zones("kathmandu");
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes("city_id=kathmandu"))).toBe(true);
    expect(urls.every((u) => !u.includes("city_id=nagpur"))).toBe(true);
  });
});

