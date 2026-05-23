import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { CreateWorkOrderPage } from "./pages/CreateWorkOrderPage";
import { ManagerPanelPage } from "./pages/ManagerPanelPage";
import { WorkOrdersListPage } from "./pages/WorkOrdersListPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/zlecenia" replace />} />
      <Route element={<AppLayout />}>
        <Route path="/kierownik" element={<ManagerPanelPage />} />
        <Route path="/zlecenia" element={<WorkOrdersListPage />} />
        <Route path="/zlecenia/nowe" element={<CreateWorkOrderPage />} />
      </Route>
    </Routes>
  );
}