import { StageWorkOrdersPage } from "../components/StageWorkOrdersPage";

export function SurfacePreparationPage() {
  return (
    <StageWorkOrdersPage
      stage="SURFACE_PREPARATION"
      title="Przygotowanie powierzchni"
      emptyMessage="Brak zleceń do przygotowania"
    />
  );
}
