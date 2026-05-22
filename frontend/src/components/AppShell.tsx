import { Outlet, NavLink } from "react-router-dom";
import { Captions, ListChecks } from "lucide-react";

export default function AppShell() {
  return (
    <div className="app-shell">
      <aside className="rail" aria-label="Primary">
        <div className="brand-mark">
          <Captions size={22} strokeWidth={2.2} />
        </div>
        <nav className="rail-nav">
          <NavLink to="/tasks" className={({ isActive }) => (isActive ? "rail-link active" : "rail-link")}>
            <ListChecks size={20} />
            <span>Tasks</span>
          </NavLink>
        </nav>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Local AI transcription</p>
            <strong>Subtitle Generator</strong>
          </div>
          <a className="ghost-link" href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
            API docs
          </a>
        </header>
        <main className="page-frame">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
