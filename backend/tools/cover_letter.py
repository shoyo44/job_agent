"""
cover_letter.py
---------------
Generates a personalized cover letter for each job listing
using the Cloudflare Workers AI LLM.
"""

import config
from agent.base_agent import BaseAgent
from agent.planner_agent import JobListing


class CoverLetterAgent(BaseAgent):
    """Produce tailored, job-specific cover letters."""

    SYSTEM_PROMPT = (
        "You are an expert career coach and professional writer. "
        "Write concise, compelling cover letters tailored to the exact job. "
        "Never invent qualifications. Use only details present in the resume summary "
        "and job posting context. Return only the final cover letter text."
    )

    def __init__(self, run_config=None):
        super().__init__("CoverLetterAgent", run_config=run_config)

    def generate(self, job: JobListing, resume_summary: str = "") -> str:
        """Generate a personalized cover letter for a single job."""
        resume_context = resume_summary or "Experienced AI/ML professional seeking impact-focused engineering roles."
        description_excerpt = (job.description or "").strip()[:1200]
        hint_text = (job.cover_letter_hint or "").strip()

        prompt = f"""
Candidate Information:
- Name: {config.USER_NAME}
- Location: {config.USER_LOCATION}
- Phone: {config.USER_PHONE}
- Resume Summary:
{resume_context}

Target Job:
- Title: {job.title}
- Company: {job.company}
- Location: {job.location}
- Work Mode: {job.work_mode}
- Planner Talking Points: {hint_text or 'Use strongest role-fit points from resume summary.'}
- Job Description (first 1200 chars):
{description_excerpt or 'Description unavailable. Use title, company, and planner talking points.'}

Write a professional cover letter (3-4 short paragraphs, max 280 words) that is specific to this role.
Hard requirements:
1. Start with "Dear Hiring Manager,".
2. Mention the exact job title and company in the opening paragraph.
3. Use 2-3 concrete, role-relevant strengths from the resume summary and connect them to this job.
4. Reference at least two job-specific requirements/signals from the job description or planner talking points.
5. Keep the tone confident and concise. No bullet points. No placeholders.
"""

        self.log.info(f"Generating cover letter for: {job.title} @ {job.company}")
        cover_letter = self.ask_llm(
            prompt,
            system=self.SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=520,
        ).strip()
        self.log.debug(f"Cover letter preview: {cover_letter[:120]}...")
        return cover_letter

    def generate_batch(
        self,
        jobs: list[JobListing],
        resume_summary: str = "",
    ) -> dict[str, str]:
        """Generate cover letters for a list of jobs."""
        letters: dict[str, str] = {}
        for job in jobs:
            letters[job.job_id] = self.generate(job, resume_summary)
            self.human_pause(0.5)
        self.log.info(f"Generated {len(letters)} cover letters.")
        return letters

    def run(self, jobs: list[JobListing], resume_summary: str = "") -> dict[str, str]:
        return self.generate_batch(jobs, resume_summary)
