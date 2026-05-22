import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import TaskDetailPage from "./pages/TaskDetailPage";
import TaskListPage from "./pages/TaskListPage";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/tasks" replace />} />
          <Route path="/tasks" element={<TaskListPage />} />
          <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
