# ATS & Scoring Rules — for tailored resumes and application answers

Governs every resume the jobs profile produces. Based on how major ATS parsers (Workday, Greenhouse, Lever, Taleo, iCIMS) actually read documents.

## File rules
- Format: .docx, single column, no text boxes, no headers/footers carrying contact info (parsers skip them), no tables for layout, no images/icons/graphics, no columns.
- Fonts: Calibri, Arial, or Georgia. 10.5–12pt body. Standard bullet characters (• or -).
- Filename: `FirstName-LastName-Company-Role.docx`. Recruiters see it; it should look deliberate.
- Contact block: name, NYC, email, phone, LinkedIn — as plain first-page text.

## Keyword rules
- Extract the JD's recurring exact phrases (e.g. "go-to-market strategy", "cross-functional", "roadmap prioritization") and mirror them verbatim where truthfully applicable. ATS scores exact matches; synonyms lose.
- Include both the spelled-out form and acronym once (e.g. "Search Engine Marketing (SEM)") when the JD uses the acronym.
- Match section headers the parser expects: Experience, Education, Skills. No creative headers ("My Journey").
- Never keyword-stuff invisibly (white text, repeated blocks) — instant rejection risk and a fabrication signal.

## Content rules
- Every bullet: verb + what + quantified outcome where the master resume has real numbers. No invented metrics — pull from master-resume.md only.
- Reorder bullets per role: the most JD-relevant experience leads each section.
- Trim anything irrelevant to the target role; a tailored resume is shorter, not padded.
- Education line includes expected graduation and relevant coursework only if JD-relevant. Certifications earned pre-MBA (e.g. FastTrack, 2023) go in an ADDITIONAL/Certifications section, not education.
- One page for 8 yrs experience + MBA is acceptable; hard cap 2 pages.
- Run an AI-tell scan before shipping: recruiters increasingly discount resumes that read machine-written. Check for tell-words (delve, showcase, leverage, seamless, pivotal, testament, underscore, foster), identical bullet rhythms, -ing tails stacked on consecutive bullets, and repeated stems. Humanize while keeping ATS keyword coverage — the two goals are compatible: exact JD phrases live in skills/tools lines, natural voice lives in the bullets.

## Learning loop (feeds weekly calibration)
- After each submission outcome (`intel`), log which resume variant (bullet choices, keyword sets) correlates with interview vs rejection in the tracker notes.
- When the candidate edits a tailored resume before submitting, diff those edits — changed emphasis and rewording are the strongest signal of what he considers truthful and strong.
- Calibration rewrites the bullet-formulation patterns in the job-hunter skill Lessons section; never edits master-resume.md content itself (truth source stays fixed; only emphasis changes).