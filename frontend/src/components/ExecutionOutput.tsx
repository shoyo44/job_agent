import React from "react";
import type { RunResponse } from "../types/api";
import { deriveAgentFlow, describeRunOutcome } from "../utils/runWorkflow";

interface ExecutionOutputProps {
  latestRun: RunResponse | null;
}

type RunResult = {
  job?: { title?: string; company?: string; location?: string; url?: string };
  result?: string;
  notes?: string;
};

type CoverLetterEntry = {
  job_id?: string;
  title?: string;
  company?: string;
  content?: string;
};

export const ExecutionOutput: React.FC<ExecutionOutputProps> = ({ latestRun }) => {
  const payload = (latestRun?.payload as Record<string, any> | undefined) ?? {};
  const results = (payload.results as RunResult[] | undefined) ?? [];
  const counts = (payload.counts as Record<string, number> | undefined) ?? {};
  const coverLetters = (payload.cover_letters as CoverLetterEntry[] | undefined) ?? [];
  const agentFlow = deriveAgentFlow(latestRun);
  const runOutcome = describeRunOutcome(latestRun);

  return (
    <div className="results-layout">
      <article className="panel results-hero">
        <header className="panel-header">
          <div>
            <p className="eyebrow">Run Outcome</p>
            <h2>Submission ladder and generated cover letters</h2>
          </div>
          <span className={`badge ${latestRun?.status === "completed" ? "ok" : "warn"}`}>{latestRun?.status || "idle"}</span>
        </header>

        {latestRun ? (
          <>
            <div className="results-hero-grid">
              <div className="story-stat"><span>Run ID</span><strong>{latestRun.run_id}</strong></div>
              <div className="story-stat"><span>Scraped</span><strong>{counts.raw_jobs ?? 0}</strong></div>
              <div className="story-stat"><span>Approved</span><strong>{counts.approved_jobs ?? 0}</strong></div>
              <div className="story-stat"><span>Cover Letters</span><strong>{counts.cover_letters_generated ?? coverLetters.length}</strong></div>
            </div>
            <p className="muted" style={{ marginTop: "1rem" }}>{runOutcome}</p>
          </>
        ) : (
          <div className="empty-story">
            <p className="strong">No run output yet</p>
            <p className="muted">Start a sync or async run to see the fallback attempts and generated writing here.</p>
          </div>
        )}
      </article>

      <article className="panel">
        <header className="panel-header">
          <div>
            <p className="eyebrow">Workflow Mirror</p>
            <h2>Frontend view of the backend agent path</h2>
          </div>
        </header>
        <div className="agent-flow">
          {agentFlow.map((step, index) => (
            <div key={`${step.agent}-${index}`} className={`agent-card agent-${step.status || "ready"}`}>
              <div className="agent-card-top">
                <span className="agent-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="badge">{step.status || "ready"}</span>
              </div>
              <h3>{step.agent || "Agent"}</h3>
              <p className="strong">{step.title || "Working"}</p>
              <p className="muted">{step.summary || "Waiting for backend details."}</p>
            </div>
          ))}
        </div>
      </article>

      <article className="panel">
        <header className="panel-header">
          <div>
            <p className="eyebrow">Submission Ladder</p>
            <h2>Which jobs were attempted in fallback order</h2>
          </div>
        </header>
        {results.length ? (
          <div className="attempt-ladder">
            {results.map((res, idx) => (
              <div key={`${res.job?.title}-${idx}`} className="attempt-card">
                <div className="attempt-rank">{idx + 1}</div>
                <div className="attempt-main">
                  <p className="strong">{res.job?.title || "Untitled role"}</p>
                  <p className="muted">{res.job?.company || "Unknown company"}{res.job?.location ? ` | ${res.job.location}` : ""}</p>
                  {res.notes ? <p className="attempt-note">{res.notes}</p> : null}
                </div>
                <div className={`badge ${(res.result === "Applied" || res.result === "DryRun") ? "ok" : "warn"}`}>{res.result || "Unknown"}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-story">
            <p className="strong">No submission attempts recorded</p>
            <p className="muted">Once the submission agent starts, each attempted job will appear here in order.</p>
          </div>
        )}
      </article>

      <article className="panel">
        <header className="panel-header">
          <div>
            <p className="eyebrow">Generated Writing</p>
            <h2>Tailored cover letters for approved roles</h2>
          </div>
        </header>
        {coverLetters.length ? (
          <div className="cover-letter-stack">
            {coverLetters.map((letter, idx) => (
              <section key={`${letter.job_id}-${idx}`} className="cover-letter-card">
                <div className="cover-letter-head">
                  <div>
                    <p className="strong">{letter.title || "Untitled role"}</p>
                    <p className="muted">{letter.company || "Unknown company"}</p>
                  </div>
                  <span className="badge">Letter {idx + 1}</span>
                </div>
                <pre className="cover-letter-body">{letter.content || "No generated content available."}</pre>
              </section>
            ))}
          </div>
        ) : (
          <div className="empty-story">
            <p className="strong">No generated cover letters yet</p>
            <p className="muted">This area will populate once approved jobs move through the cover letter agent.</p>
          </div>
        )}
      </article>

    </div>
  );
};
