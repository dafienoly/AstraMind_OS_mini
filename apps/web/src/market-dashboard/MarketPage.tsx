import { MarketRotation } from "../market/MarketRotation";
import { MarketDashboard } from "./MarketDashboard";
import { EtfRotationPage } from "./etf-rotation/EtfRotationPage";
import { StockRealtimePage } from "./realtime/StockRealtimePage";

export function MarketPage() {
  const query = new URLSearchParams(window.location.search);
  const tab = query.get("tab") ?? "overview";
  const view = query.get("view") ?? "heatmap";
  if (tab === "industries" && view === "rotation") {
    return <MarketRotation />;
  }
  if (tab === "industries" && view === "lifecycle") {
    return <MarketDashboard view="lifecycle" />;
  }
  if (tab === "industries") {
    return <MarketDashboard view="heatmap" />;
  }
  if (tab === "etf") {
    return <EtfRotationPage />;
  }
  if (tab === "stocks") {
    return <StockRealtimePage />;
  }
  return <MarketDashboard view="overview" />;
}
