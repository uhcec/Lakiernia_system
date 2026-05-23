import { StageWorkOrdersPage } from "../components/StageWorkOrdersPage";

export function PackingPage() {
  return <StageWorkOrdersPage stage="PACKING" title="Pakowanie" emptyMessage="Brak zleceń do pakowania" />;
}