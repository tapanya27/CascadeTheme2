import { Sidebar } from "@/components/layout/sidebar";
import { AlertsProvider } from "@/lib/alerts-context";
import { CityProvider } from "@/lib/city-context";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <CityProvider>
      <AlertsProvider>
        <div className="flex min-h-screen flex-col bg-background text-foreground lg:h-screen lg:flex-row lg:overflow-hidden">
          <Sidebar />
          <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto lg:overflow-hidden">
            {children}
          </div>
        </div>
      </AlertsProvider>
    </CityProvider>
  );
}
