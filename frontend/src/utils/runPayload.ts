import type {
  AgentStep,
  CoverLetterEntry,
  RunPayload,
  RunProgress,
  RunResponse,
  RunResult,
  SubmissionPlan,
  SubmissionPlanFinalist,
} from "../types/api";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isAgentStep(value: unknown): value is AgentStep {
  return (
    isRecord(value) &&
    typeof value.agent === "string" &&
    typeof value.title === "string" &&
    typeof value.status === "string" &&
    typeof value.summary === "string"
  );
}

function isRunResult(value: unknown): value is RunResult {
  return isRecord(value);
}

function isCoverLetterEntry(value: unknown): value is CoverLetterEntry {
  return isRecord(value);
}

function isSubmissionPlanFinalist(value: unknown): value is SubmissionPlanFinalist {
  return isRecord(value);
}

function isSubmissionPlan(value: unknown): value is SubmissionPlan {
  return isRecord(value);
}

export function getRunPayload(latestRun: RunResponse | null): RunPayload {
  return isRecord(latestRun?.payload) ? (latestRun.payload as RunPayload) : {};
}

export function getRunCounts(payload: RunPayload): Record<string, number> {
  return isRecord(payload.counts) ? (payload.counts as Record<string, number>) : {};
}

export function getCurrentProgress(payload: RunPayload): RunProgress | null {
  return isRecord(payload.current_progress) ? (payload.current_progress as RunProgress) : null;
}

export function getProgressExtra(progress: RunProgress | null): Record<string, unknown> {
  return isRecord(progress?.extra) ? progress.extra : {};
}

export function getAgentFlow(payload: RunPayload): AgentStep[] {
  return Array.isArray(payload.agent_flow) ? payload.agent_flow.filter(isAgentStep) : [];
}

export function getRunResults(payload: RunPayload): RunResult[] {
  return Array.isArray(payload.results) ? payload.results.filter(isRunResult) : [];
}

export function getCoverLetters(payload: RunPayload): CoverLetterEntry[] {
  return Array.isArray(payload.cover_letters) ? payload.cover_letters.filter(isCoverLetterEntry) : [];
}

export function getSubmissionPlan(payload: RunPayload): SubmissionPlan | null {
  return isSubmissionPlan(payload.submission_plan) ? payload.submission_plan : null;
}

export function getSubmissionFinalists(plan: SubmissionPlan | null): SubmissionPlanFinalist[] {
  return Array.isArray(plan?.finalists) ? plan.finalists.filter(isSubmissionPlanFinalist) : [];
}

export function getSubmissionPlanFromProgress(progress: RunProgress | null): SubmissionPlan | null {
  const extra = getProgressExtra(progress);
  return isSubmissionPlan(extra) ? (extra as SubmissionPlan) : null;
}
