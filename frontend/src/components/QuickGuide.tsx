import React from 'react';

interface QuickGuideProps {
  isOpen: boolean;
  onClose: () => void;
}

export const QuickGuide: React.FC<QuickGuideProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div className="glass" style={{
      position: 'fixed',
      inset: 0,
      zIndex: 100,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '2rem',
      background: 'rgba(54, 69, 79, 0.4)'
    }}>
      <div className="panel staggered" style={{ maxWidth: '600px', width: '100%', animation: 'fadeIn 0.3s ease-out' }}>
        <header className="panel-header">
          <p className="eyebrow">Operator Instruction</p>
          <h2 className="brand">Quick Operations Guide</h2>
        </header>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <section>
            <p className="strong small">1. Authentication</p>
            <p className="muted small">Login with your Google account. This secures your session and tracks your specific application history.</p>
          </section>

          <section>
            <p className="strong small">2. Transient Credentials</p>
            <p className="muted small">Provide your LinkedIn email, password, and upload your resume. We use these for the current session only; they are not persisted to our databases for your privacy.</p>
          </section>

          <section>
            <p className="strong small">3. Pipeline Execution</p>
            <p className="muted small">Use the <strong>Pipeline Config</strong> tab to set your goals. <strong>Dry Run</strong> is recommended for first-time use to see potential matches without submitting.</p>
          </section>

          <section>
            <p className="strong small">4. Monitoring</p>
            <p className="muted small">Check <strong>Execution Logs</strong> for real-time feedback. If your run is Asynchronous, you can poll its status using the Run ID provided.</p>
          </section>
        </div>

        <button className="primary" onClick={onClose} style={{ marginTop: '2rem', width: '100%' }}>
          Got it, let's work
        </button>
      </div>
    </div>
  );
};
