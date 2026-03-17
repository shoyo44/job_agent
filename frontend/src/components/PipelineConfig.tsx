import React from 'react';
import type { RunRequest } from '../types/api';

interface PipelineFormProps {
  form: Partial<RunRequest>;
  setField: (field: keyof RunRequest, value: any) => void;
  onRunSync: () => Promise<void>;
  loading: boolean;
  linkedinEmail: string;
  resumeFileName: string;
  currentProgress?: Record<string, any> | null;
  runStatus?: string;
}

export const PipelineForm: React.FC<PipelineFormProps> = ({
  form,
  setField,
  onRunSync,
  loading,
  linkedinEmail,
  resumeFileName,
  currentProgress,
  runStatus,
}) => {
  return (
    <article className="panel staggered">
      <header className="panel-header">
        <div>
          <p className="eyebrow">Simple Run Setup</p>
          <h2>Tell the agent what to apply for</h2>
        </div>
      </header>

      {currentProgress ? (
        <div className="run-action-bar current-phase-bar">
          <div>
            <p className="strong">Backend is currently in progress</p>
            <p className="muted small">
              {currentProgress.agent || 'Agent'} | {currentProgress.phase || 'phase'}
            </p>
            <p className="muted small">{currentProgress.message || 'Working on the pipeline.'}</p>
          </div>
          <span className={`badge ${runStatus === 'running' ? 'warn' : 'ok'}`}>{runStatus || 'idle'}</span>
        </div>
      ) : null}

      <div className="run-action-bar">
        <div>
          <p className="strong">Ready to start?</p>
          <p className="muted small">Use this button to run the same backend flow: score top 5, critic picks top 3, submission stops after 1 success.</p>
        </div>
        <button className="primary run-button" onClick={onRunSync} disabled={loading || runStatus === 'running'}>
          {loading ? 'Starting...' : runStatus === 'running' ? 'Pipeline Running' : 'Start Pipeline'}
        </button>
      </div>

      <div className="setup-summary">
        <p className="small color-text-muted">
          Active Operator: <strong>{linkedinEmail}</strong> | Resume: <strong>{resumeFileName}</strong>
        </p>
      </div>

      <div className="form-grid">
        <label className="span-2">
          Job Goal
          <input 
            value={form.goal} 
            onChange={(e) => setField('goal', e.target.value)} 
            placeholder='e.g., "Data engineer in Bangalore easy apply only"'
          />
        </label>

        <label>
          Work Mode
          <select
            value={form.work_mode_preference ?? 'any'}
            onChange={(e) => setField('work_mode_preference', e.target.value)}
          >
            <option value="any">Any</option>
            <option value="remote">Remote</option>
            <option value="onsite">Onsite</option>
            <option value="hybrid">Hybrid</option>
          </select>
        </label>

        <label>
          Jobs To Search
          <input 
            type="number" 
            value={form.max_scraped_jobs} 
            onChange={(e) => setField('max_scraped_jobs', Number(e.target.value))} 
          />
        </label>

        <label>
          Submission Mode
          <select 
            value={form.dry_run ? 'yes' : 'no'} 
            onChange={(e) => setField('dry_run', e.target.value === 'yes')}
          >
            <option value="yes">Dry run only</option>
            <option value="no">Live apply</option>
          </select>
        </label>

        <label>
          Easy Apply Filter
          <select 
            value={form.easy_apply_only ? 'yes' : 'no'} 
            onChange={(e) => setField('easy_apply_only', e.target.value === 'yes')}
          >
            <option value="yes">Only Easy Apply jobs</option>
            <option value="no">Any LinkedIn jobs</option>
          </select>
        </label>
      </div>

      <div className="setup-note">
        <p className="muted">
          The frontend now mirrors the backend workflow: scrape matching jobs, score and keep the top 5, let the critic select the top 3, generate cover letters for those finalists, and stop after the first successful submission.
        </p>
      </div>
    </article>
  );
};
