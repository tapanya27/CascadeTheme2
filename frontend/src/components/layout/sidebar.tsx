"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  BellRing,
  ClipboardList,
  Compass,
  HelpCircle,
  Home,
  Lightbulb,
  MapPinned,
  Menu,
  ShieldAlert,
  Wrench,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { useCity } from "@/lib/city-context";
import { cn } from "@/lib/utils";

const primaryNav: {
  href: string;
  label: string;
  hint: string;
  icon: typeof MapPinned;
}[] = [
  {
    href: "/",
    label: "Home",
    hint: "Start here",
    icon: Home,
  },
  {
    href: "/map",
    label: "Explore the Map",
    hint: "Click areas to learn more",
    icon: Compass,
  },
  {
    href: "/alerts",
    label: "New Alerts",
    hint: "Fresh warnings & notices",
    icon: BellRing,
  },
  {
    href: "/community-risk",
    label: "Community Risk & Impact",
    hint: "Impact radius & fragility",
    icon: ShieldAlert,
  },
  {
    href: "/tasks",
    label: "Verification Tasks",
    hint: "Assigned checks & follow-ups",
    icon: ClipboardList,
  },
  {
    href: "/zones",
    label: "Places That Need Attention",
    hint: "Areas scored for review",
    icon: MapPinned,
  },
  {
    href: "/intelligence",
    label: "What If Something Goes Wrong?",
    hint: "Try a simple scenario",
    icon: Wrench,
  },
  {
    href: "/interventions",
    label: "How Can We Help?",
    hint: "Suggested next steps",
    icon: Lightbulb,
  },
  {
    href: "/about",
    label: "About the Project",
    hint: "How this system works",
    icon: HelpCircle,
  },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav
      className="flex flex-1 flex-col gap-1 overflow-y-auto px-2 pb-4 quiet-scroll"
      aria-label="Primary"
    >
      {primaryNav.map((item) => {
        const showActive =
          item.href === "/"
            ? pathname === "/"
            : pathname === item.href || pathname.startsWith(`${item.href}/`);
        const Icon = item.icon;
        return (
          <Link
            key={`${item.href}-${item.label}`}
            href={item.href}
            onClick={onNavigate}
            className={cn(
              "group flex items-center gap-2.5 rounded-2xl px-3 py-2.5 text-sm transition-all duration-200",
              showActive
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-foreground/80 hover:bg-secondary"
            )}
            aria-current={showActive ? "page" : undefined}
          >
            <span
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-xl border transition-colors",
                showActive
                  ? "border-white/30 bg-white/15 text-white"
                  : "border-border bg-white text-primary"
              )}
            >
              <Icon className="h-4 w-4" aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block font-medium leading-tight">{item.label}</span>
              <span
                className={cn(
                  "block text-[11px]",
                  showActive ? "text-white/80" : "text-muted-foreground"
                )}
              >
                {item.hint}
              </span>
            </span>
          </Link>
        );
      })}
    </nav>
  );
}

export function Sidebar() {
  const [open, setOpen] = useState(false);
  const { city } = useCity();

  const brand = (
    <div className="flex items-center gap-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-primary/25 bg-primary/10 text-primary">
        <ShieldAlert className="h-5 w-5" aria-hidden />
      </div>
      <div>
        <p className="font-display text-[15px] font-semibold leading-tight tracking-wide text-foreground">
          CRIVAL
        </p>
        <p className="text-[11px] text-muted-foreground">
          Let&apos;s keep communities safe
        </p>
      </div>
    </div>
  );

  return (
    <>
      <div className="flex items-center justify-between border-b border-border bg-card px-4 py-3 lg:hidden">
        {brand}
        <Button
          type="button"
          size="icon"
          variant="ghost"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </Button>
      </div>
      {open ? (
        <div
          id="mobile-nav"
          className="max-h-[75vh] overflow-y-auto border-b border-border bg-card lg:hidden quiet-scroll"
        >
          <NavLinks onNavigate={() => setOpen(false)} />
        </div>
      ) : null}

      <aside className="relative z-30 hidden w-[17.5rem] shrink-0 flex-col border-r border-border bg-card/90 backdrop-blur-md lg:flex">
        <div className="border-b border-border px-4 py-5">{brand}</div>
        <div className="pt-3">
          <NavLinks />
        </div>
        <div className="mt-auto border-t border-border px-4 py-3 text-[11px] text-muted-foreground">
          Exploring{" "}
          <span className="font-semibold text-primary">
            {city?.name ?? "—"}
          </span>
        </div>
      </aside>
    </>
  );
}
