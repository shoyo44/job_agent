import React from 'react';
import type { User } from 'firebase/auth';

interface DashboardLayoutProps {
  activeTab: 'overview' | 'pipeline' | 'logs';
  setActiveTab: (tab: 'overview' | 'pipeline' | 'logs') => void;
  firebaseUser: User | null;
  onLogout: () => Promise<void>;
  loading: boolean;
  message: string;
  checklist: Array<{ label: string; done: boolean }>;
  children: React.ReactNode;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({
  activeTab,
  setActiveTab,
  firebaseUser,
  onLogout,
  loading,
  message,
  checklist,
  children,
}) => {
  return (
    <main className="console-shell">
      <aside className="sidebar staggered">
        <div>
          <h1 className="brand">Job Agent</h1>
          <p className="eyebrow" style={{ fontSize: '0.65rem' }}>Pipeline Workspace</p>
        </div>

        <nav className="side-nav">
          <button
            className={`nav-link ${activeTab === 'overview' ? 'active' : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            Agent Pipeline
          </button>
          <button
            className={`nav-link ${activeTab === 'pipeline' ? 'active' : ''}`}
            onClick={() => setActiveTab('pipeline')}
          >
            Run Setup
          </button>
          <button
            className={`nav-link ${activeTab === 'logs' ? 'active' : ''}`}
            onClick={() => setActiveTab('logs')}
          >
            Run Results
          </button>
        </nav>

        <section className="sidebar-guide">
          <p className="strong small">How it works</p>
          <p className="muted small">1. Finish onboarding once.</p>
          <p className="muted small">2. Enter the target role and preferences.</p>
          <p className="muted small">3. Review the agent flow, cover letters, and fallback apply results.</p>
        </section>

        <section style={{ marginTop: 'auto' }}>
          <p className="strong small" style={{ marginBottom: '1rem' }}>Session Checklist</p>
          <ul className="checklist">
            {checklist.map((item) => (
              <li key={item.label} className={item.done ? 'done' : ''}>
                <span></span>
                {item.label}
              </li>
            ))}
          </ul>
        </section>

        <div className="user-info">
          <img src={firebaseUser?.photoURL || ''} alt="avatar" className="avatar" style={{ width: '32px', height: '32px' }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <p className="strong small" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {firebaseUser?.displayName || 'Authenticated user'}
            </p>
          </div>
          <button className="secondary logout-button" onClick={onLogout} disabled={loading}>
            Logout
          </button>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <p className="subtitle">{message || 'Set the goal, run the pipeline, and review what each agent produced.'}</p>
        </header>
        {children}
      </section>
    </main>
  );
};
