import type {
  RunJobSummary,
  SubmissionPlanFinalist,
  DocsSummaryResponse,
  FeatureResponse,
  RunResponse,
  TrackerHistoryResponse,
  TrackerStatsResponse,
} from "../types/api";
import { deriveAgentFlow, describeRunOutcome } from "../utils/runWorkflow";
import { getCurrentProgress, getProgressExtra, getRunCounts, getRunPayload, getSubmissionFinalists, getSubmissionPlan, getSubmissionPlanFromProgress } from "../utils/runPayload";

interface OverviewPanelProps {
  latestRun: RunResponse | null;
  tracker: TrackerStatsResponse | null;
  trackerHistory: TrackerHistoryResponse | null;
  apiFeatures: FeatureResponse | null;
  docsSummary: DocsSummaryResponse | null;
}

export const OverviewPanel: React.FC<OverviewPanelProps> = ({ latestRun, tracker, trackerHistory, apiFeatures, docsSummary }) => {
  const payload = getRunPayload(latestRun);
  const counts = getRunCounts(payload);
  const profile = payload.profile ?? {};
  const agentFlow = deriveAgentFlow(latestRun);
  const approvedJobs = (payload.approved_jobs ?? []).slice(0, 4) as RunJobSummary[];
  const historyRecords = trackerHistory?.records ?? [];
  const backend = trackerHistory?.backend;
  const currentProgress = getCurrentProgress(payload);
  const progressExtra = getProgressExtra(currentProgress);
  const submissionPlan = getSubmissionPlan(payload) ?? getSubmissionPlanFromProgress(currentProgress);
  const submissionFinalists = getSubmissionFinalists(submissionPlan);
  const featureGroups = Object.entries(apiFeatures?.features ?? {});
  const docsSections = Object.entries(docsSummary?.sections ?? {});
  const runOutcome = describeRunOutcome(latestRun);

  function renderProgressValue(value: unknown): string {
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
    if (Array.isArray(value)) {
      return `${value.length} item${value.length === 1 ? "" : "s"}`;
    }
    if (value && typeof value === "object") {
      return "Attached";
    }
    return "Unknown";
  }

  return (
    <div className="pipeline-overview">
      <article className="panel pipeline-hero">
        <div>
          <p className="eyebrow">Agent Pipeline</p>
          <h2>Watch each agent contribute to the application run</h2>
          <p className="subtitle">The dashboard now focuses on what the agents decided, what they generated, and where the submission flow ended.</p>
        </div>
        <div className="pipeline-hero-grid">
          <div className="story-stat">
            <span>Goal</span>
            <strong>{typeof profile.goal === "string" ? profile.goal : "No run yet"}</strong>
          </div>
          <div className="story-stat">
            <span>Run Status</span>
            <strong>{latestRun?.status || "Waiting"}</strong>
          </div>
          <div className="story-stat">
            <span>Applications</span>
            <strong>{counts.applications_processed ?? 0}</strong>
          </div>
          <div className="story-stat">
            <span>Applied Today</span>
            <strong>{String(tracker?.applied_today ?? 0)}</strong>
          </div>
        </div>
        <p className="muted" style={{ marginTop: "1rem" }}>{runOutcome}</p>
      </article>

      <article className="panel current-progress-panel">
        <header className="panel-header">
          <div>
            <p className="eyebrow">Live Backend Phase</p>
            <h2>What the backend is doing right now</h2>
          </div>
          <span className={`badge ${latestRun?.status === "running" ? "warn" : "ok"}`}>{latestRun?.status || "idle"}</span>
        </header>
        {currentProgress ? (
          <>
            <div className="current-progress-grid">
              <div className="story-stat">
                <span>Current Agent</span>
                <strong>{currentProgress.agent || "Unknown"}</strong>
              </div>
              <div className="story-stat">
                <span>Phase</span>
                <strong>{currentProgress.phase || "Unknown"}</strong>
              </div>
              <div className="story-stat current-progress-message story-stat-wide">
                <span>Task</span>
                <strong>{currentProgress.message || "Waiting for progress update"}</strong>
              </div>
            </div>

            {currentProgress.agent === "SubmissionAgent" && submissionPlan ? (
              <div className="submission-insight-block">
                <div className="submission-live-grid">
                  <div className="story-stat">
                    <span>Submission Target</span>
                    <strong>{submissionPlan.target_successes ?? 1} success</strong>
                  </div>
                  <div className="story-stat">
                    <span>Fallback Jobs</span>
                    <strong>{submissionPlan.jobs_to_try ?? submissionFinalists.length}</strong>
                  </div>
                </div>

                {submissionFinalists.length ? (
                  <div className="submission-plan-stack">
                {submissionFinalists.map((job: SubmissionPlanFinalist, index) => (
                  <div key={`${job.job_id || job.title}-${index}`} className="submission-plan-card">
                    <div>
                      <p className="strong">{job.title || "Untitled role"}</p>
                      <p className="muted">{job.company || "Unknown company"}{job.location ? ` | ${job.location}` : ""}</p>
                      <p className="muted">Critic Score: {job.confidence_score ?? 0}/100</p>
                    </div>
                    <div className="submission-plan-meta">
                      <span className="badge neutral">Queue {index + 1}</span>
                      <span>{job.platform || "linkedin"}</span>
                    </div>
                  </div>
                ))}
              </div>
                ) : null}
              </div>
            ) : null}

            {Object.keys(progressExtra).length && currentProgress.agent !== "SubmissionAgent" ? (
              <div className="progress-extra-grid">
                {Object.entries(progressExtra).slice(0, 4).map(([key, value]) => (
                  <div key={key} className="story-stat">
                    <span>{key.replace(/_/g, " ")}</span>
                    <strong>{renderProgressValue(value)}</strong>
                  </div>
                ))}
              </div>
            ) : null}
          </>
        ) : (
          <div className="empty-story">
            <p className="strong">No live phase available</p>
            <p className="muted">Start the pipeline to see which backend agent is currently running.</p>
          </div>
        )}
      </article>

      <article className="panel">
        <header className="panel-header">
          <div>
            <p className="eyebrow">Pipeline Story</p>
            <h2>How the agents moved the run forward</h2>
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
              <p className="strong">{step.title}</p>
              <p className="muted">{step.summary}</p>
            </div>
          ))}
        </div>
      </article>

      <div className="content-grid">
        <article className="panel">
          <header className="panel-header">
            <div>
              <p className="eyebrow">Approved Jobs</p>
              <h2>Best candidates currently in the run</h2>
            </div>
          </header>
          {approvedJobs.length ? (
            <div className="job-stack">
              {approvedJobs.map((job, index) => (
                <div key={`${job.title}-${index}`} className="job-stack-card">
                  <div>
                    <p className="strong">{job.title || "Untitled role"}</p>
                    <p className="muted">{job.company || "Unknown company"}</p>
                    <p className="muted">Critic Score: {job.confidence_score ?? 0}/100</p>
                  </div>
                  <div className="job-meta">
                    <span>{job.work_mode || "unknown"}</span>
                    <span>{job.location || "unknown location"}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-story">
              <p className="strong">No approved jobs yet</p>
              <p className="muted">Run the pipeline and this section will show the strongest jobs passed by the critic.</p>
            </div>
          )}
        </article>

        <article className="panel">
          <header className="panel-header">
            <div>
              <p className="eyebrow">Tracker Backend</p>
              <h2>MongoDB history connection</h2>
            </div>
          </header>
          <div className="story-stat-grid">
            <div className="story-stat">
              <span>Backend</span>
              <strong>{backend?.type || "Unavailable"}</strong>
            </div>
            <div className="story-stat">
              <span>Connection</span>
              <strong>{backend?.connected ? "Connected" : "Not connected"}</strong>
            </div>
            <div className="story-stat">
              <span>Database</span>
              <strong>{backend?.db || backend?.path || "Unknown"}</strong>
            </div>
            <div className="story-stat">
              <span>Collection</span>
              <strong>{backend?.collection || "N/A"}</strong>
            </div>
          </div>
        </article>
      </div>

      <div className="content-grid capability-grid">
        <article className="panel">
          <header className="panel-header">
            <div>
              <p className="eyebrow">FastAPI Features</p>
              <h2>What the backend exposes today</h2>
            </div>
          </header>
          {featureGroups.length ? (
            <div className="capability-list">
              {featureGroups.map(([group, items]) => (
                <div key={group} className="capability-card">
                  <p className="strong capability-title">{group}</p>
                  {Object.entries(items).map(([label, route]) => (
                    <div key={label} className="capability-row">
                      <span>{label}</span>
                      <code>{route}</code>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-story">
              <p className="strong">API feature map unavailable</p>
              <p className="muted">The frontend will show backend capability groups after authenticated API discovery loads.</p>
            </div>
          )}
        </article>

        <article className="panel">
          <header className="panel-header">
            <div>
              <p className="eyebrow">Backend Docs Summary</p>
              <h2>Frontend-ready capability notes</h2>
            </div>
          </header>
          {docsSections.length ? (
            <div className="capability-list">
              {docsSections.map(([section, details]) => {
                const lists = [details.flow, details.entrypoints, details.outputs, details.read, details.write, details.readiness, details.notes].filter(Boolean) as string[][];
                return (
                  <div key={section} className="capability-card">
                    <p className="strong capability-title">{section}</p>
                    {lists.flat().slice(0, 8).map((item) => (
                      <div key={item} className="capability-row">
                        <span>{item}</span>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="empty-story">
              <p className="strong">Docs summary unavailable</p>
              <p className="muted">This area will mirror the grouped backend capability summary from FastAPI.</p>
            </div>
          )}
        </article>
      </div>

      <article className="panel">
        <header className="panel-header">
          <div>
            <p className="eyebrow">Application History</p>
            <h2>Recent tracked jobs from the backend</h2>
          </div>
        </header>
        {historyRecords.length ? (
          <div className="history-list">
            {historyRecords.map((record, index) => (
              <div key={`${record.job_id || record.title}-${index}`} className="history-card">
                <div>
                  <p className="strong">{record.title || "Untitled role"}</p>
                  <p className="muted">{record.company || "Unknown company"}{record.location ? ` | ${record.location}` : ""}</p>
                </div>
                <div className="history-meta">
                  <span className="badge">{record.status || "Unknown"}</span>
                  <span>{record.date_applied || "Unknown date"}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-story">
            <p className="strong">No history available yet</p>
            <p className="muted">Once the tracker saves records to MongoDB, the recent application history will appear here.</p>
          </div>
        )}
      </article>
    </div>
  );
};
