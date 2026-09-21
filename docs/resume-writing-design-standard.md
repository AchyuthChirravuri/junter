# Resume Design & Writing Standard — PDF output (v2)

Governs every tailored resume. Two layers: WRITING (STAR, positioning) and DESIGN (layout tokens).

## Writing rules

**Bullet formula (learned from PM resume writing standards — Google XYZ + Yale OCS Action-Project-Result):**
- Structure: **[Strong action verb] + [what you accomplished/delivered] + [quantified or concrete result]**. Outcome-first. Every bullet answers "so what?".
- NEVER use a repeated sentence template across bullets. Vary the syntax: lead with the verb, lead with the number, or lead with the scope — but never the same stem twice in a row, and never a gimmick stem ("When X happened...") anywhere.
- Action verbs: Led, Directed, Built, Owned, Converted, Delivered, Drove, Launched, Scaled, Advised, Designed, Negotiated, Turned around. Past tense for past roles, present tense for current role.
- "I" or "my team" never appears; the verb implies the actor. Team size/agency context goes in the CONTEXT line, not inside every bullet.
- Every bullet ends in a number, a named outcome, or a clear business state change. No result = don't include the bullet.
- Numbers come from master-resume.md only. Never invent, never round up.
- Bullets within one job must vary in rhythm: not all three-part sentences, not all starting with the same part of speech. Read them aloud test: if five bullets in a row sound identical, rewrite.

**Positioning for the role.**
- Re-read the JD before writing. Identify: the role's core mandate (what success looks like), its 5–8 recurring keyword phrases, and the level expectations.
- Summary (2–3 lines max) is rewritten per role: position the candidate as the answer to THIS mandate, not a generalist. Truthfully framed, never re-titled.
- Select the strongest-matching bullets per role (8–20 total depending on depth of relevance); reorder so the closest match leads. Cut everything irrelevant — density beats completeness on one page.
- The gap the JD will notice: address it implicitly by leading with the nearest transferable proof, never by hiding it.

**Length.** Exactly 1 page, filled (the generator auto-scales). If content overflows even at minimum scale: cut bullets.

**Humanizer pass (mandatory before any resume ships).** LLM-drafted bullets carry tells that scream AI. Scan final text programmatically: tell-words (delve, showcase, leverage, seamless, pivotal, testament, underscore, foster, landscape, robust, streamline, empower, unlock, transformative), mechanical rhythm (every bullet the same "verb + participial -ing tail" shape), -ing clause stacking (highlighting/translating/ensuring/symbolizing), numbers buried mid-sentence, stems repeated 3+ times. Fix pattern: vary grammar per bullet (result-colon constructions like "premium commuter share, up 14 points in two years", short declaratives, ownership verbs: Ran, Owned, Took, Moved, Signed, Hired), put numbers at the END of the bullet where they land hardest, active voice throughout. Keep every metric traced to master-resume.md and stay within the character budget of the line being replaced (~same length, or the fixed layout breaks).

**Layout verification for docx deliverables (template-based builds).** Render via soffice → `pdftotext -bbox`, group words into lines by y-coordinate, then check: (1) no ink past the right text edge, (2) left starts at exactly the expected indent levels (e.g. 20.6/25.4/36.4pt), (3) header rules drawn as w:drawing shapes clear the first content line by ≥4pt, (4) exactly 1 page. Section-header "rules" in Fordham/Gabelli templates are anchored drawing rectangles, not paragraph borders — a pBdr scan finds nothing; locate them via `w:drawing` in the header or adjacent spacer paragraph.

## Design tokens (make-resume-pdf implements these)

**CANONICAL TEMPLATE (user-approved 2026-09-20, from ~/Downloads/Your Name Resume_Sep26.pdf — matches this spec exactly):**
- Layout: name RIGHT-aligned top, contact line right-aligned beneath, tagline right-aligned bold caps. Sections start with a full-width horizontal rule, header caps left-aligned above it.
- Section order: EDUCATION first, then EXPERIENCE, then ADDITIONAL (internships + Technical/AI bullets). No summary paragraph, no tagline rule.
- Job header: COMPANY NAME bold caps left, city right-aligned same line; title bold left, dates right-aligned same line beneath.
- Education entries: SCHOOL caps + city right; degree bold + date right; sub-lines (GA role, clubs) plain.
- ADDITIONAL section: labeled bullets — Early Experience / Technical / AI & Automation — dense, comma-packed.
- Bullets: round dots, tight leading, numbers land at bullet ends. Fonts: bold serif-adjacent name, clean sans body (Calibri-class).
- All-black text, no accent color, no rules except section dividers. Dense, filled page.

**Generator mapping (make-resume-pdf.py implements this style when `TEMPLATE: gabelli` in src):**
- Name 17pt bold right-aligned; contact 8.5pt gray right; tagline 9pt bold caps right.
- Section headers: 9.5pt bold caps + 0.3pt full-width black rule beneath.
- Company: 9.8pt bold caps left + city right (gray); Title: 9.3pt bold + dates right.
- Bullets 9pt, standard dot glyph, 3.8mm leading. Everything ink-black (#111); no teal.
- Education section before Experience; ADDITIONAL labeled-bullet block at end.

## Output
- `make-resume-pdf <src.md> <out.pdf>` — src format: `NAME:`, `CONTACT:`, `TAGLINE:`, `SUMMARY:`, `SECTION <name>`, `JOB: company | title | dates`, `CONTEXT: optional`, `- bullet`, `GROUP: label | items`.
- One-page enforcement: auto-scale loop (body 9.2 → 8.9 → 8.6pt) and a hard error if content still exceeds one page (means writing must be cut, not squeezed).
- Filename: `FirstName-LastName-Company-Role.pdf`.