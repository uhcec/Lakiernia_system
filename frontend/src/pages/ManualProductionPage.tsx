import { StageWorkOrdersPage } from "../components/StageWorkOrdersPage";

export function ManualProductionPage() {
  return (
    <StageWorkOrdersPage
      stage="PRODUCTION"
      productionType="MANUAL"
      title="Produkcja ręczna"
      emptyMessage="Brak zleceń do produkcji ręcznej"
    />
  );
}