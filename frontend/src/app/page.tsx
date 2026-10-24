const modules = [
  { title: "Agent runtime", description: "Model adapter, harness, tool registry and policy boundaries.", status: "Scaffold" },
  { title: "Voice runtime", description: "Session lifecycle, STT/TTS and interruption handling.", status: "Planned" },
  { title: "Data and memory", description: "PostgreSQL records, tenant scoping and retention controls.", status: "Scaffold" },
  { title: "Operations", description: "Health checks, CI, backup verification and recovery runbooks.", status: "Planned" }
];

export default function HomePage() {
  return (
    <main className="shell">
      <header className="header">
        <div className="brand">◈ Voice Platform</div>
        <span className="pill">Starter blueprint · v0.1</span>
      </header>
      <section className="hero">
        <p className="muted">AI AGENT CONTROL PLANE</p>
        <h1>Build agents with clear boundaries.</h1>
        <p className="muted">
          A modular foundation for Gemini-powered agents, secure tool execution,
          voice workflows and operational recovery. This dashboard is a scaffold;
          connect it to authenticated APIs as implementation progresses.
        </p>
      </section>
      <section className="grid" aria-label="Platform modules">
        {modules.map((module) => (
          <article className="card" key={module.title}>
            <span className="pill">{module.status}</span>
            <h2>{module.title}</h2>
            <p className="muted">{module.description}</p>
          </article>
        ))}
      </section>
      <section className="notice">
        <strong>Security note</strong>
        <p className="muted">
          Do not connect real customer data until authentication, tenant isolation,
          tool authorization, secret handling and backup restoration are implemented.
        </p>
      </section>
      <footer className="footer">
        Architecture scaffold only — API integration and real-time voice are not yet complete.
      </footer>
    </main>
  );
}
