import { StageWorkOrdersPage } from "../components/StageWorkOrdersPage";

export function HangingPage() {
  return <StageWorkOrdersPage stage="HANGING" title="Zawieszanie" emptyMessage="Brak zleceń do zawieszania" />;
}