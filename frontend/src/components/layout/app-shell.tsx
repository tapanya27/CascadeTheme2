import { Sidebar } from "@/components/layout/sidebar";
import { AlertsProvider } from "@/lib/alerts-context";
import { CityProvider } from "@/lib/city-context";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <CityProvider>
      <AlertsProvider>
        <div className="flex min-h-screen flex-col bg-background text-foreground lg:flex-row">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col">{children}</div>
        </div>
      </AlertsProvider>
    </CityProvider>
  );
}
