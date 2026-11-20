import React from "react";
import { createRoot } from "react-dom/client";
import "./styles/main.css";

function App() {
  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Product">
        <div className="brand"><span className="mark" aria-hidden="true">D</span> DataSleuth</div>
        <p className="sidebar-label">PRIVACY ENGINEERING</p>
        <p className="active">Project foundation</p>
        <div className="sidebar-footer">Local development</div>
      </aside>
      <main>
        <header className="topbar">DataSleuth <span>/</span> Project foundation</header>
        <section className="content">
          <p className="eyebrow">DEVELOPMENT BUILD</p>
          <h1>Project foundation</h1>
          <p className="intro">The discovery workflow is not available yet.</p>
          <div className="notice">
            <h2>Building the foundation</h2>
            <p>This local development build does not scan files or store findings. Implementation progress and limitations are tracked in Project_Docs/IMPLEMENTATION_STATUS.md.</p>
          </div>
        </section>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
