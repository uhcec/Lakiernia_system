import { StageWorkOrdersPage } from "../components/StageWorkOrdersPage";

export function AutomaticProductionPage() {
  return (
    <StageWorkOrdersPage
      stage="PRODUCTION"
      productionType="AUTOMATIC"
      allowManualStart={false}
      readOnly
      readOnlyLabel="Status automatu"
      title="Produkcja: Automat"
      emptyMessage="Brak zleceń do zawieszania lub na automacie"
    />
  );
}
