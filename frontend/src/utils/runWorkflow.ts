import type { RunResponse } from "../types/api";

export type AgentStep = {
  agent: string;
  title: string;
  status: string;
  summary: string;
};

const BASE_STEPS: AgentStep[] = [
  {
    agent: "ManagerAgent",
    title: "Understood your goal",
    status: "ready",
    summary: "Turns your prompt into a search profile with roles, locations, and work preferences.",
  },
  {
    agent: "PlannerAgent",
    title: "Built queries and scored jobs",
    status: "ready",
    summary: "Scrapes LinkedIn jobs, scores them, and keeps the strongest candidates.",
  },
  {
    agent: "CriticAgent",
    title: "Selected the strongest jobs",
    status: "ready",
    summary: "Chooses the best jobs from the scored shortlist.",
  },
  {
    agent: "CoverLetterAgent",
    title: "Prepared tailored cover letters",
    status: "ready",
    summary: "Generates role-aware writing for the final shortlisted jobs.",
  },
  {
    agent: "SubmissionAgent",
    title: "Tried final applications",
    status: "ready",
    summary: "Attempts the final selected jobs and stops after the first successful apply.",
  },
  {
    agent: "TrackerAgent",
    title: "Stored the final outcome",
    status: "ready",
    summary: "Saves the run outcome to the tracker backend.",
  },
];

const AGENT_ORDER = BASE_STEPS.map((step) => step.agent);

function cloneBaseSteps(): AgentStep[] {
  return BASE_STEPS.map((step) => ({ ...step }));
}

function applyProgress(steps: AgentStep[], currentAgent: string | undefined, currentMessage: string | undefined) {
  if (!currentAgent) return steps;
  const currentIndex = AGENT_ORDER.indexOf(currentAgent);
  if (currentIndex === -1) return steps;

  return steps.map((step, index) => {
    if (index < currentIndex) {
      return { ...step, status: "completed" };
    }
    if (index === currentIndex) {
      return {
        ...step,
        status: "running",
        summary: currentMessage || step.summary,
      };
    }
    return step;
  });
}

export function deriveAgentFlow(latestRun: RunResponse | null): AgentStep[] {
  const steps = cloneBaseSteps();
  if (!latestRun) return steps;

  const payload = (latestRun.payload as Record<string, any> | undefined) ?? {};
  const backendFlow = payload.agent_flow as AgentStep[] | undefined;
  if (backendFlow?.length) {
    return backendFlow.map((step) => ({
      agent: step.agent || "Agent",
      title: step.title || "Working",
      status: step.status || "ready",
      summary: step.summary || "",
    }));
  }

  const currentProgress = (payload.current_progress as Record<string, any> | undefined) ?? {};
  const currentAgent = typeof currentProgress.agent === "string" ? currentProgress.agent : undefined;
  const currentMessage = typeof currentProgress.message === "string" ? currentProgress.message : undefined;
  let derived = applyProgress(steps, currentAgent, currentMessage);

  const counts = (payload.counts as Record<string, number> | undefined) ?? {};
  const appliedCount = counts.applications_processed ?? 0;
  const scoredCount = counts.scored_jobs ?? 0;
  const approvedCount = counts.approved_jobs ?? 0;
  const coverLetters = counts.cover_letters_generated ?? 0;

  if (latestRun.status === "completed") {
    derived = derived.map((step) => ({ ...step, status: "completed" }));
    if (appliedCount === 0) {
      derived[4] = {
        ...derived[4],
        status: "partial",
        summary: "Submission ran but no successful application was recorded.",
      };
    }
    return derived;
  }

  if (latestRun.status === "no_jobs") {
    derived[0].status = "completed";
    derived[1] = {
      ...derived[1],
      status: "blocked",
      summary: latestRun.message || "Scraping finished without any matching jobs.",
    };
    return derived;
  }

  if (latestRun.status === "no_scored_jobs") {
    derived[0].status = "completed";
    derived[1] = {
      ...derived[1],
      status: "blocked",
      summary: latestRun.message || "Jobs were scraped, but none survived scoring.",
    };
    return derived;
  }

  if (latestRun.status === "no_approved_jobs") {
    derived[0].status = "completed";
    derived[1].status = scoredCount > 0 ? "completed" : derived[1].status;
    derived[2] = {
      ...derived[2],
      status: "blocked",
      summary: latestRun.message || "Critic did not select any jobs for submission.",
    };
    return derived;
  }

  if (latestRun.status === "failed") {
    if (approvedCount > 0) {
      derived[2].status = "completed";
    }
    if (coverLetters > 0) {
      derived[3].status = "completed";
    }
    return derived.map((step) => {
      if (step.status === "running") {
        return {
          ...step,
          status: "blocked",
          summary: latestRun.message || step.summary,
        };
      }
      return step;
    });
  }

  return derived;
}

export function describeRunOutcome(latestRun: RunResponse | null): string {
  if (!latestRun) return "Start the pipeline to mirror the backend workflow here.";
  if (latestRun.status === "running") return latestRun.message || "Backend pipeline is still running.";
  return latestRun.message || `Run finished with status: ${latestRun.status}`;
}
