"use client";

import Link from "next/link";

import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Expandable } from "@/components/ui/expandable";
import { PageMain, Panel, Section } from "@/components/ui/section";

export default function AboutPage() {
  return (
    <>
      <Header
        title="About the Project"
        subtitle="Find places that may need help, learn why, and see what we can do — with honest labels for demo vs live data."
        showCity={false}
      />
      <PageMain>
        <Section title="What this tool is for">
          <Panel className="space-y-3 text-sm leading-relaxed text-muted-foreground">
            <p>
              Floods and service disruptions do not affect every neighborhood equally.
              This dashboard highlights areas where flood exposure, limited road access,
              and distance from healthcare may stack together.
            </p>
            <p>
              Use it to explore cities, compare communities, practice what-if scenarios,
              and discuss next steps — for college demos, planning conversations, and
              research prototypes.
            </p>
          </Panel>
        </Section>

        <Section title="How to read the numbers">
          <div className="grid gap-3 md:grid-cols-3">
            <Panel>
              <h3 className="font-medium text-foreground">Risk scores</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Transparent planning scores. They are not flood forecasts.
              </p>
            </Panel>
            <Panel>
              <h3 className="font-medium text-foreground">What-if results</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Simulated desk exercises. They are not historical incidents.
              </p>
            </Panel>
            <Panel>
              <h3 className="font-medium text-foreground">Demo / study data</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Curated demonstration datasets are labelled. Never treat them as live
                crisis feeds.
              </p>
            </Panel>
          </div>
        </Section>

        <Callout tone="info" title="Cities included">
          Nagpur, Mumbai, Chennai, Guwahati (India) and Kathmandu (Nepal). Switch cities
          from the header. Each city’s data stays separate.
        </Callout>

        <Section title="Suggested walkthrough for judges">
          <ol className="surface list-decimal space-y-2 px-5 py-4 text-sm text-muted-foreground">
            <li>Choose a city on Home.</li>
            <li>Open Explore the Map — click a colored area.</li>
            <li>Tap the bell → Try a Demo Alert → Show Me on the Map.</li>
            <li>Read What is happening? / Why / What can we do?</li>
            <li>Open How Can We Help? and What If Something Goes Wrong?</li>
          </ol>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button asChild>
              <Link href="/">Go to Home</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/map">Open map</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/alerts">New Alerts</Link>
            </Button>
          </div>
        </Section>

        <Expandable title="How This System Works">
          <ul className="space-y-1 text-xs text-muted-foreground">
            <li>Frontend: Next.js App Router, TypeScript, Tailwind CSS, Leaflet, Recharts</li>
            <li>Backend: FastAPI + PostgreSQL/PostGIS</li>
            <li>
              Risk scores are planning scores from the existing assessment pipeline —
              not verified flood probabilities
            </li>
            <li>
              Alerts: labeled Demo Alert adapter + Open-Meteo forecast poll (not IMD/DHM
              official warnings). Read / acknowledge / resolve stay separate.
            </li>
            <li>
              Flood early-warning models remain experimental; metrics stay out of the
              main cards
            </li>
            <li>API base URL: NEXT_PUBLIC_API_BASE_URL</li>
          </ul>
        </Expandable>
      </PageMain>
    </>
  );
}
