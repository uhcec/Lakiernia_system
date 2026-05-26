import { StageWorkOrdersPage } from "../components/StageWorkOrdersPage";

export function AutomaticProductionPage() {
  return (
    <StageWorkOrdersPage
      stage="PRODUCTION"
      productionType="AUTOMATIC"
      allowManualStart={false}
      readOnly
      readOnlyLabel="Podgląd automatu"
      title="Produkcja: Automat"
      emptyMessage="Brak zleceń dla automatu"
    />
  );
}