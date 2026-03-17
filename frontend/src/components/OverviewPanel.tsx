import type { RunResponse, TrackerHistoryResponse, TrackerStatsResponse } from "../types/api";

interface OverviewPanelProps {
  latestRun: RunResponse | null;
  tracker: TrackerStatsResponse | null;
  trackerHistory: TrackerHistoryResponse | null;
}

type AgentStep = {
  agent?: string;
  title?: string;
  status?: string;
  summary?: string;
};

type JobSummary = {
  title?: string;
  company?: string;
  confidence_score?: number;
  work_mode?: string;
};

const fallbackSteps: AgentStep[] = [
  { agent: "ManagerAgent", title: "Interprets the goal", status: "ready", summary: "Turns the job request into a search profile with roles, locations, and preferences." },
  { agent: "PlannerAgent", title: "Finds and scores jobs", status: "ready", summary: "Builds search queries, scrapes LinkedIn jobs, and ranks them by fit." },
  { agent: "CriticAgent", title: "Filters quality", status: "ready", summary: "Rejects weaker matches and keeps the strongest jobs for submission." },
  { agent: "CoverLetterAgent", title: "Writes tailored pitch", status: "ready", summary: "Generates a resume-aware cover letter for each approved job." },
  { agent: "SubmissionAgent", title: "Executes fallback apply flow", status: "ready", summary: "Tries jobs one by one until one Easy Apply submission succeeds." },
  { agent: "TrackerAgent", title: "Stores outcomes", status: "ready", summary: "Saves the run result so the next session knows what already happened." },
];

export const OverviewPanel: React.FC<OverviewPanelProps> = ({ latestRun, tracker, trackerHistory }) => {
  const payload = (latestRun?.payload as Record<string, any> | undefined) ?? {};
  const counts = (payload.counts as Record<string, number> | undefined) ?? {};
  const profile = (payload.profile as Record<string, any> | undefined) ?? {};
  const agentFlow = ((payload.agent_flow as AgentStep[] | undefined) ?? fallbackSteps);
  const approvedJobs = ((payload.approved_jobs as JobSummary[] | undefined) ?? []).slice(0, 4);
  const historyRecords = trackerHistory?.records ?? [];
  const backend = trackerHistory?.backend;
  const currentProgress = ((latestRun?.payload as Record<string, any> | undefined)?.current_progress as Record<string, any> | undefined) ?? null;

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
            <strong>{profile.goal || "No run yet"}</strong>
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
                  </div>
                  <div className="job-meta">
                    <span>{job.confidence_score ?? 0}/100</span>
                    <span>{job.work_mode || "unknown"}</span>
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
