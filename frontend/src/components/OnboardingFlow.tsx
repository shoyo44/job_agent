import React from 'react';

interface OnboardingFlowProps {
  linkedinEmail: string;
  setLinkedinEmail: (val: string) => void;
  linkedinPassword: string;
  setLinkedinPassword: (val: string) => void;
  resumeFileName: string;
  onResumeFileChange: (file: File | null) => Promise<void>;
  completeOnboarding: () => void;
  onLogout: () => Promise<void>;
  loading: boolean;
  message: string;
}

export const OnboardingFlow: React.FC<OnboardingFlowProps> = ({
  linkedinEmail,
  setLinkedinEmail,
  linkedinPassword,
  setLinkedinPassword,
  resumeFileName,
  onResumeFileChange,
  completeOnboarding,
  onLogout,
  loading,
  message,
}) => {
  return (
    <main className="login-shell">
      <section className="login-card">
        <p className="eyebrow">Step 2 of 2</p>
        <h1 className="brand">Ready to Start</h1>
        <p className="subtitle">
          Provide your transient credentials. We never store these permanently; they are used only for the current active run.
        </p>
        
        {message && <p className="muted small">{message}</p>}
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: '1rem' }}>
          <label>
            LinkedIn Email
            <input 
              value={linkedinEmail} 
              onChange={(e) => setLinkedinEmail(e.target.value)} 
              placeholder="operator@example.com" 
            />
          </label>
          
          <label>
            LinkedIn Password
            <input 
              type="password" 
              value={linkedinPassword} 
              onChange={(e) => setLinkedinPassword(e.target.value)} 
              placeholder="Enter LinkedIn password" 
            />
          </label>
          
          <label>
            Resume (PDF/DOCX)
            <div style={{ position: 'relative' }}>
              <input 
                type="file" 
                accept=".pdf,.doc,.docx" 
                onChange={(e) => onResumeFileChange(e.target.files?.[0] ?? null)} 
                style={{ paddingRight: '2rem' }}
              />
              {resumeFileName && (
                <p className="muted small" style={{ marginTop: '0.4rem' }}>
                  ✓ {resumeFileName}
                </p>
              )}
            </div>
          </label>
          
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
            <button className="primary" onClick={completeOnboarding} disabled={loading}>
              Enter Dashboard
            </button>
            <button className="secondary" onClick={onLogout} disabled={loading}>
              Log out
            </button>
          </div>
        </div>
      </section>
    </main>
  );
};
