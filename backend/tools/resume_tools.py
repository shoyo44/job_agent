"""
resume_tools.py
---------------
Extracts and caches a text summary of the user's resume PDF for use
by the Planner and Cover Letter agents.
"""

import re
from pathlib import Path


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extracts raw text from a PDF using PyMuPDF (fitz).
    Returns an empty string if the file doesn't exist or fails to parse.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        return "\n".join(page.get_text() for page in doc)
    except ImportError:
        print("[resume_tools] PyMuPDF not installed. Run: pip install pymupdf")
        return ""
    except Exception as e:
        print(f"[resume_tools] Error reading PDF: {e}")
        return ""


def summarise_resume(pdf_path: Path, llm_caller=None) -> str:
    """
    Returns a short (3-5 sentence) summary of the candidate's background
    from their resume PDF.

    Args:
        pdf_path   : Path to the resume PDF
        llm_caller : Optional callable — a bound method like agent.ask_llm().
                     If None, returns a trimmed raw extraction.
    """
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        return "Experienced AI/ML professional with a strong background in Python and deep learning."

    if llm_caller is None:
        # Return first ~500 chars as a fallback "summary"
        return text[:500].strip()

    prompt = f"""
Extract a concise 3-5 sentence professional summary from this resume text.
Focus on: years of experience, key skills, notable achievements, and the type of roles they are best suited for.

Resume text (first 2000 chars):
{text[:2000]}

Return ONLY the summary paragraph, nothing else.
"""
    return llm_caller(prompt, system="You are a professional resume writer. Be concise.")


def extract_resume_intelligence(pdf_path: Path, llm_caller=None) -> str:
    """
    Extract structured, role-relevant resume highlights for downstream prompts.
    This is designed to be appended into cover-letter context.
    """
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        return ""

    if llm_caller is None:
        fallback = "Resume highlights:\n- Strong software/AI background\n- Hands-on project delivery\n- Problem solving and collaboration"
        return fallback

    prompt = f"""
Extract concise resume intelligence for job applications.
Return plain text using this exact shape:

Resume highlights:
- Core skills: <comma-separated technical strengths>
- Experience snapshot: <years/domain summary>
- Notable achievements: <1-2 measurable outcomes>
- Projects/tools: <relevant stack and project themes>
- Target role fit: <why this profile fits AI/ML engineering roles>

Rules:
- Use only facts from resume text.
- Do not invent numbers, employers, or certifications.
- Keep total output under 140 words.

Resume text (first 3000 chars):
{text[:3000]}
"""
    return llm_caller(
        prompt,
        system=(
            "You are a strict resume analyst. Extract only grounded facts from the resume. "
            "Be concise and application-focused."
        ),
        temperature=0.1,
        max_tokens=220,
    ).strip()


def extract_skills(pdf_path: Path) -> list[str]:
    """
    Returns a list of technical skill keywords found in the resume.
    Uses simple regex keyword extraction — no LLM needed.
    """
    text = extract_text_from_pdf(pdf_path).lower()

    # A broad list of common tech/AI skills to scan for
    skill_patterns = [
        r"\bpython\b", r"\bjava\b", r"\bc\+\+\b", r"\bjavascript\b",
        r"\btensorflow\b", r"\bpytorch\b", r"\bkeras\b", r"\bscikit.learn\b",
        r"\bhugging\s*face\b", r"\btransformer\b", r"\bllm\b", r"\bgpt\b",
        r"\bnlp\b", r"\bcomputer\s*vision\b", r"\bdeep\s*learning\b",
        r"\bmachine\s*learning\b", r"\bdata\s*science\b", r"\bmlops\b",
        r"\bdocker\b", r"\bkubernetes\b", r"\bfastapi\b", r"\bflask\b",
        r"\bsql\b", r"\bmongodb\b", r"\baws\b", r"\bazure\b", r"\bgcp\b",
        r"\bgit\b", r"\blangchain\b", r"\bvector\s*database\b", r"\brag\b",
    ]

    found = set()
    for pattern in skill_patterns:
        if re.search(pattern, text):
            # Clean up the pattern to get a readable skill name
            skill = re.sub(r"\\b|\\s\*|\\.| ", "", pattern).replace("+", "++")
            found.add(skill.strip())

    return sorted(found)
