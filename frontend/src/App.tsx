import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuditEventsPage } from "./pages/AuditEventsPage";
import { AutomaticProductionPage } from "./pages/AutomaticProductionPage";
import { ClientsPage } from "./pages/ClientsPage";
import { CreateWorkOrderPage } from "./pages/CreateWorkOrderPage";
import { DecoralProductionPage } from "./pages/DecoralProductionPage";
import { EmployeesPage } from "./pages/EmployeesPage";
import { FoilsPage } from "./pages/FoilsPage";
import { HangingPage } from "./pages/HangingPage";
import { LoginPage } from "./pages/LoginPage";
import { ManualProductionPage } from "./pages/ManualProductionPage";
import { ManagerPanelPage } from "./pages/ManagerPanelPage";
import { PackingPage } from "./pages/PackingPage";
import { PaintInventoryPage } from "./pages/PaintInventoryPage";
import { StatystykiPage } from "./pages/StatystykiPage";
import { SurfacePreparationPage } from "./pages/SurfacePreparationPage";
import { WorkOrderDetailPage } from "./pages/WorkOrderDetailPage";
import { WorkOrdersListPage } from "./pages/WorkOrdersListPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/zlecenia" replace />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/audyt" element={<AuditEventsPage />} />
        <Route path="/farby" element={<PaintInventoryPage />} />
        <Route path="/klienci" element={<ClientsPage />} />
        <Route path="/folie" element={<FoilsPage />} />
        <Route path="/pracownicy" element={<EmployeesPage />} />
        <Route path="/statystyki" element={<StatystykiPage />} />
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
