import { StageWorkOrdersPage } from "../components/StageWorkOrdersPage";

export function DecoralProductionPage() {
  return (
    <StageWorkOrdersPage
      stage="DECORAL_PRODUCTION"
      title="Produkcja Decoral"
      emptyMessage="Brak zleceń do produkcji Decoral"
    />
  );
}