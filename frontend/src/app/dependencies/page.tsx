"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Header } from "@/components/layout/header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Expandable } from "@/components/ui/expandable";
import { PageMain, Panel, Section } from "@/components/ui/section";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { api, ApiError, type DependencyGraph, type GraphEdge } from "@/lib/api";
import { useCity } from "@/lib/city-context";

const EVIDENCE_LABEL: Record<string, string> = {
  observed: "Observed — based on available data",
  assumed: "Assumed — reasonable planning assumption",
  hypothesized: "Hypothesis — candidate link, not proven",
};

export default function DependenciesPage() {
  const { cityId, city } = useCity();
  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<GraphEdge | null>(null);
  const [seeding, setSeeding] = useState(false);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    setSelected(null);
    try {
      const data = await api.dependencyGraph(cityId);
      if (id !== seq.current) return;
      setGraph(data);
    } catch (e) {
      if (id !== seq.current) return;
      setError(e instanceof ApiError ? e.message : "Could not load connections");
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, [cityId]);

  useEffect(() => {
    void load();
  }, [load]);

  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [] as Node[], edges: [] as Edge[] };
    const n = graph.nodes.length;
    const nodes: Node[] = graph.nodes.map((node, i) => {
      const angle = (2 * Math.PI * i) / Math.max(n, 1) - Math.PI / 2;
      const r = Math.min(200, 80 + n * 8);
      return {
        id: node.id,
        data: { label: node.label },
        position: {
          x: 260 + r * Math.cos(angle),
          y: 200 + r * Math.sin(angle),
        },
        style: {
          border: "1px solid #94a3b8",
          borderRadius: 8,
          padding: 8,
          fontSize: 12,
          background: "#ffffff",
          width: 140,
        },
      };
    });
    const edges: Edge[] = graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.relationship_type.replace(/_/g, " "),
      animated: e.evidence_kind === "hypothesized",
      markerEnd: { type: MarkerType.ArrowClosed },
      style: {
        stroke:
          e.evidence_kind === "observed"
            ? "#0f766e"
            : e.evidence_kind === "assumed"
              ? "#b45309"
              : "#64748b",
        strokeDasharray: e.evidence_kind === "hypothesized" ? "6 4" : undefined,
      },
    }));
    return { nodes, edges };
  }, [graph]);

  async function seedGraph() {
    setSeeding(true);
    setError(null);
    try {
      await api.runAssessments(cityId, { seed_dependency_graph: true });
      await load();
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not build connection graph"
      );
    } finally {
      setSeeding(false);
    }
  }

  const sourceLabel =
    graph?.nodes.find((n) => n.id === selected?.source)?.label ?? selected?.source;
  const targetLabel =
    graph?.nodes.find((n) => n.id === selected?.target)?.label ?? selected?.target;

  return (
    <>
      <Header
        title="Connections"
        subtitle={`${city?.name ?? cityId} — how hazards, services, and communities may link`}
      />
      <PageMain>
        <Callout tone="warning" title="Not proven cause-and-effect">
          This graph shows analytical relationships for planning. Solid teal =
          observed, amber = assumed, dashed gray = hypothesis. Hypotheses are not
          proven causal claims.
        </Callout>

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => void load()} disabled={loading}>
            Refresh
          </Button>
          <Button
            variant="secondary"
            disabled={seeding || loading}
            onClick={() => void seedGraph()}
          >
            {seeding ? "Building…" : "Rebuild from assessments"}
          </Button>
          {graph ? (
            <>
              <Badge variant="outline">{graph.nodes.length} items</Badge>
              <Badge variant="outline">{graph.edges.length} links</Badge>
              <Badge variant={graph.is_dag ? "authentic" : "synthetic"}>
                {graph.is_dag ? "No loops" : "Contains loops"}
              </Badge>
            </>
          ) : null}
        </div>

        <div
          className="flex flex-wrap gap-4 text-xs text-muted-foreground"
          role="list"
          aria-label="Link type legend"
        >
          <span role="listitem" className="flex items-center gap-1.5">
            <span className="h-0.5 w-6 bg-[#0f766e]" aria-hidden /> Observed
          </span>
          <span role="listitem" className="flex items-center gap-1.5">
            <span className="h-0.5 w-6 bg-[#b45309]" aria-hidden /> Assumed
          </span>
          <span role="listitem" className="flex items-center gap-1.5">
            <span
              className="h-0.5 w-6 border-t-2 border-dashed border-slate-500"
              aria-hidden
            />{" "}
            Hypothesis
          </span>
        </div>

        {loading ? <LoadingState label="Loading connections…" /> : null}
        {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}

        {!loading && !error && graph && graph.edges.length === 0 ? (
          <EmptyState
            title="No connections yet"
            description="Run community assessments to build the default planning graph, then refresh."
            action={
              <Button disabled={seeding} onClick={() => void seedGraph()}>
                {seeding ? "Building…" : "Rebuild from assessments"}
              </Button>
            }
          />
        ) : null}

        {!loading && !error && graph && graph.edges.length > 0 ? (
          <Section title="Relationship map">
            <div className="grid gap-4 lg:grid-cols-[1.5fr_0.9fr]">
              <Panel className="h-[min(480px,70vh)] overflow-hidden p-0">
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  fitView
                  onEdgeClick={(_, edge) => {
                    const match =
                      graph.edges.find((e) => e.id === edge.id) ?? null;
                    setSelected(match);
                  }}
                  onNodeClick={(_, node) => {
                    const related = graph.edges.find(
                      (e) => e.source === node.id || e.target === node.id
                    );
                    setSelected(related ?? null);
                  }}
                >
                  <Background gap={16} color="#e2e8f0" />
                  <Controls showInteractive={false} />
                </ReactFlow>
              </Panel>

              <Panel className="space-y-3">
                <h3 className="font-display text-base">Selected link</h3>
                {selected ? (
                  <>
                    <p className="text-sm font-medium">
                      {sourceLabel} → {targetLabel}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {selected.relationship_type.replace(/_/g, " ")}
                    </p>
                    <Badge
                      variant={
                        selected.evidence_kind === "hypothesized"
                          ? "synthetic"
                          : selected.evidence_kind === "observed"
                            ? "authentic"
                            : "secondary"
                      }
                    >
                      {EVIDENCE_LABEL[selected.evidence_kind] ??
                        selected.evidence_kind}
                    </Badge>
                    <p className="text-sm">
                      {selected.evidence ??
                        "No short explanation was stored for this link."}
                    </p>
                    {selected.evidence_kind === "hypothesized" ? (
                      <Callout tone="warning" title="Hypothesis">
                        Treat this as a candidate for investigation, not a confirmed
                        causal pathway.
                      </Callout>
                    ) : null}
                    <Expandable title="Technical details">
                      <dl className="space-y-1 text-xs text-muted-foreground">
                        <div>
                          <dt className="inline font-medium text-foreground">
                            Edge id:{" "}
                          </dt>
                          <dd className="inline">{selected.id}</dd>
                        </div>
                        <div>
                          <dt className="inline font-medium text-foreground">
                            Source / target:{" "}
                          </dt>
                          <dd className="inline">
                            {selected.source} → {selected.target}
                          </dd>
                        </div>
                        {selected.provenance != null ? (
                          <div>
                            <dt className="font-medium text-foreground">
                              Provenance keys
                            </dt>
                            <dd className="mt-1">
                              {Object.keys(
                                selected.provenance as Record<string, unknown>
                              ).join(", ") || "none"}
                            </dd>
                          </div>
                        ) : null}
                      </dl>
                    </Expandable>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Click a link or node on the map to read what it means.
                  </p>
                )}

                {graph.notes.length > 0 ? (
                  <Expandable title="Graph notes">
                    <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
                      {graph.notes.map((n) => (
                        <li key={n}>{n}</li>
                      ))}
                    </ul>
                  </Expandable>
                ) : null}
              </Panel>
            </div>
          </Section>
        ) : null}
      </PageMain>
    </>
  );
}
