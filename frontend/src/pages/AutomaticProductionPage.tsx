import { StageWorkOrdersPage } from "../components/StageWorkOrdersPage";

export function AutomaticProductionPage() {
  return (
    <StageWorkOrdersPage
      stage="PRODUCTION"
      productionType="AUTOMATIC"
      allowManualStart={false}
      readOnly
      readOnlyLabel="Podgląd automatu"
      title="Produkcja automat"
      emptyMessage="Brak zleceń do produkcji automat"
    />
  );
}