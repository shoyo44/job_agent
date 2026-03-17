import React from 'react';

interface LoginScreenProps {
  onGoogleLogin: () => Promise<void>;
  loading: boolean;
  message: string;
  firebaseSetupError: string;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({
  onGoogleLogin,
  loading,
  message,
  firebaseSetupError,
}) => {
  return (
    <main className="login-shell">
      <section className="login-card">
        <p className="eyebrow">Job Agent</p>
        <h1 className="brand">Sign in</h1>
        <p className="subtitle">
          Professional job application automation. Securely managed by your Google Identity.
        </p>
        
        {firebaseSetupError && (
          <div className="alert warn">
            <p className="warn-text">Firebase Setup: {firebaseSetupError}</p>
          </div>
        )}
        
        {message && <p className="muted small">{message}</p>}
        
        <button 
          className="primary" 
          onClick={onGoogleLogin} 
          disabled={loading || Boolean(firebaseSetupError)}
        >
          {loading ? 'Authenticating...' : 'Continue with Google'}
        </button>
      </section>
    </main>
  );
};
