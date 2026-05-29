import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { AuditEventsPage } from "./pages/AuditEventsPage";
import { AutomaticProductionPage } from "./pages/AutomaticProductionPage";
import { CreateWorkOrderPage } from "./pages/CreateWorkOrderPage";
import { DecoralProductionPage } from "./pages/DecoralProductionPage";
import { HangingPage } from "./pages/HangingPage";
import { ManualProductionPage } from "./pages/ManualProductionPage";
import { ManagerPanelPage } from "./pages/ManagerPanelPage";
import { PackingPage } from "./pages/PackingPage";
import { SurfacePreparationPage } from "./pages/SurfacePreparationPage";
import { WorkOrderDetailPage } from "./pages/WorkOrderDetailPage";
import { WorkOrdersListPage } from "./pages/WorkOrdersListPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/zlecenia" replace />} />
      <Route element={<AppLayout />}>
        <Route path="/audyt" element={<AuditEventsPage />} />
        <Route path="/kierownik" element={<ManagerPanelPage />} />
        <Route path="/przygotowanie" element={<SurfacePreparationPage />} />
        <Route path="/zawieszanie" element={<HangingPage />} />
        <Route path="/produkcja-reczna" element={<ManualProductionPage />} />
        <Route path="/produkcja-automat" element={<AutomaticProductionPage />} />
        <Route path="/produkcja-decoral" element={<DecoralProductionPage />} />
        <Route path="/pakowanie" element={<PackingPage />} />
        <Route path="/zlecenia" element={<WorkOrdersListPage />} />
        <Route path="/zlecenia/nowe" element={<CreateWorkOrderPage />} />
        <Route path="/zlecenia/:id" element={<WorkOrderDetailPage />} />
      </Route>
    </Routes>
  );
}