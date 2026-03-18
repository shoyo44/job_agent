import React from "react";
import type { RunResponse, RunResult, SubmissionPlanFinalist } from "../types/api";
import { deriveAgentFlow, describeRunOutcome } from "../utils/runWorkflow";
import { getCoverLetters, getRunCounts, getRunPayload, getRunResults, getSubmissionFinalists, getSubmissionPlan } from "../utils/runPayload";

interface ExecutionOutputProps {
  latestRun: RunResponse | null;
}

export const ExecutionOutput: React.FC<ExecutionOutputProps> = ({ latestRun }) => {
  const payload = getRunPayload(latestRun);
  const results = getRunResults(payload);
  const counts = getRunCounts(payload);
  const coverLetters = getCoverLetters(payload);
  const submissionPlan = getSubmissionPlan(payload);
  const submissionFinalists = getSubmissionFinalists(submissionPlan);
  const agentFlow = deriveAgentFlow(latestRun);
  const runOutcome = describeRunOutcome(latestRun);
  const successfulResults = results.filter((res) => res.result === "Applied" || res.result === "DryRun");

  function getResultForFinalist(job: SubmissionPlanFinalist): RunResult | undefined {
    return results.find((result) => {
      const resultJob = result.job;
      if (job.job_id && resultJob?.job_id) {
        return job.job_id === resultJob.job_id;
      }
      return job.title === resultJob?.title && job.company === resultJob?.company;
    });
  }

  function getPlanBadge(result?: RunResult): { label: string; tone: string } {
    if (!result) return { label: "Queued", tone: "neutral" };
    if (result.result === "Applied" || result.result === "DryRun") return { label: result.result, tone: "ok" };
    if (result.result === "Skipped") return { label: "Skipped", tone: "neutral" };
    return { label: result.result || "Attempted", tone: "warn" };
  }

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
              <div className="story-stat"><span>Attempted</span><strong>{results.length}</strong></div>
              <div className="story-stat"><span>Cover Letters</span><strong>{counts.cover_letters_generated ?? coverLetters.length}</strong></div>
              <div className="story-stat"><span>Successful</span><strong>{successfulResults.length}</strong></div>
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
            <p className="eyebrow">Submission Strategy</p>
            <h2>The exact backend fallback order for the submission agent</h2>
          </div>
        </header>
        {submissionFinalists.length ? (
          <>
            <div className="submission-live-grid">
              <div className="story-stat">
                <span>Target Successes</span>
                <strong>{submissionPlan?.target_successes ?? 1}</strong>
              </div>
              <div className="story-stat">
                <span>Jobs To Try</span>
                <strong>{submissionPlan?.jobs_to_try ?? submissionFinalists.length}</strong>
              </div>
            </div>
            <div className="submission-plan-stack">
              {submissionFinalists.map((job, index) => {
                const result = getResultForFinalist(job);
                const badge = getPlanBadge(result);
                return (
                  <div key={`${job.job_id || job.title}-${index}`} className="submission-plan-card">
                    <div>
                      <p className="strong">{job.title || "Untitled role"}</p>
                      <p className="muted">{job.company || "Unknown company"}{job.location ? ` | ${job.location}` : ""}</p>
                    </div>
                    <div className="submission-plan-meta">
                      <span className={`badge ${badge.tone}`}>{badge.label}</span>
                      <span>Queue {index + 1}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <div className="empty-story">
            <p className="strong">No submission strategy captured yet</p>
            <p className="muted">Once the backend finalizes the approved finalists, the exact fallback order will appear here.</p>
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
                <div className={`badge ${(res.result === "Applied" || res.result === "DryRun") ? "ok" : res.result === "Skipped" ? "neutral" : "warn"}`}>{res.result || "Unknown"}</div>
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
            <p className="eyebrow">Successful Applications</p>
            <h2>Applied jobs with company details</h2>
          </div>
        </header>
        {successfulResults.length ? (
          <div className="attempt-ladder">
            {successfulResults.map((res, idx) => (
              <div key={`${res.job?.job_id || res.job?.title}-${idx}`} className="attempt-card">
                <div className="attempt-rank">{idx + 1}</div>
                <div className="attempt-main">
                  <p className="strong">{res.job?.title || "Untitled role"}</p>
                  <p className="muted">{res.job?.company || "Unknown company"}</p>
                  <p className="muted">
                    Critic Score: {res.job?.confidence_score ?? 0}/100
                    {res.job?.location ? ` | ${res.job.location}` : ""}
                    {res.job?.work_mode ? ` | ${res.job.work_mode}` : ""}
                    {res.job?.salary ? ` | ${res.job.salary}` : ""}
                  </p>
                  <p className="muted">
                    Platform: {res.job?.platform || "linkedin"}
                    {res.job?.url ? " | " : ""}
                    {res.job?.url ? <a href={res.job.url} target="_blank" rel="noreferrer">Open job</a> : null}
                  </p>
                </div>
                <div className="badge ok">{res.result || "Applied"}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-story">
            <p className="strong">No successful applications yet</p>
            <p className="muted">Once a job is applied successfully, it will appear here with company and role details.</p>
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
