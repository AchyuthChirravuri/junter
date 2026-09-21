# Architecture

The system is a single-operator pipeline: three cron-triggered runs on a Hermes Agent profile, connected by files on disk (tracker, cache, drafts) and a Telegram command interface. The human is a component — deliberately in the loop at every decision point.

```mermaid
flowchart TB
    subgraph TRIGGERS["Scheduled Triggers (cron, jobs profile)"]
        T1["Daily 7:30am ET<br/>Sourcing Run"]
        T2["9am + 6pm ET<br/>Account Backgrounder"]
        T3["Sunday 8pm ET<br/>Weekly Calibration"]
    end

    subgraph SOURCING["Sourcing Run (time-boxed: 25 queries max)"]
        S1["Tier 1: HN Who's Hiring,<br/>Built In NYC, Wellfound,<br/>seeded career pages"]
        S2["Tier 2: keyword expansion +<br/>new-grad program pages"]
        S3["Tier 3: adjacent boards<br/>(YC, Remotive, WeWorkRemotely)"]
        S1 -->|"fewer than 10 roles score 6+"| S2 -->|"still short"| S3
        S1 & S2 & S3 --> D1
    end

    subgraph SCORE["Scoring"]
        D1["Dedupe vs tracker.csv<br/>(never re-track)"]
        R1["role-rubric.md<br/>weighted 0-10 with hard caps<br/>(stale > 21 days caps at 5)"]
        D1 --> R1
    end

    R1 -->|"9+ full package"| P2
    R1 -->|"7-8.5 ping"| DIG
    R1 -->|"< 7 tracker only"| TRK

    subgraph DELIVER["Delivery"]
        DIG["Telegram digest<br/>top 10 ranked, watchlist pinned<br/>(role, fit, angle, URL)"]
        TRK["tracker.csv<br/>(status, notes, outcome)"]
    end

    H["Human: the candidate<br/>~3 min/day"] -->|"int / go / skip"| DIG
    H -->|"intel outcome"| TRK

    subgraph BG["Backgrounder Run (per interested role)"]
        B1["Company research<br/>cache 30-day reuse"]
        B2["One-pager per template<br/>(mission, news, funding,<br/>what you'd work on)"]
        B1 --> B2
    end

    H -->|"'go id' or queued"| B1

    subgraph BUILD["Package Builder"]
        C1["cover-letter-templates.md<br/>(3 angles, anti-patterns)"]
        C2["master-resume.md<br/>TRUTH SOURCE - never edited per role"]
        C3["ats-rules.md<br/>+ resume-style.md<br/>+ humanizer scan"]
        C4["Tailored ATS .docx<br/>+ cover letter"]
        C1 & C2 & C3 --> C4
        C2 -.->|"every bullet traces here"| C4
    end

    B2 --> C4
    C4 -->|"Telegram: resume doc + letter"| H
    C4 -.->|"waits - NEVER auto-submits"| H2["Manual submission<br/>(portals are the human's)"]

    subgraph CAL["Weekly Calibration"]
        W1["Read outcome data:<br/>replies, edit-diffs, intel"]
        W2["Rubric vN+1<br/>(rationale stated, versioned)"]
        W3["Weekly metrics digest"]
        W1 --> W2 --> W3 --> H
    end

    T1 --> S1
    T2 --> B1
    T3 --> W1

    style H fill:#f9f9f9,stroke:#333,stroke-width:2px
    style C2 fill:#eef6e9,stroke:#4a7c3a
    style C4 fill:#eef6e9,stroke:#4a7c3a
    style DIG fill:#e8f0fe,stroke:#3a6bb4
```

## Component notes

**File bus, not a database.** The tracker CSV, company cache, and drafts folder are the integration layer. Boring on purpose: inspectable, greppable, and diffable by the human at any time.

**Truth-source discipline.** `master-resume.md` is the only source of resume facts. Tailored drafts draw from it exclusively — the system never writes new claims, only re-selects and re-orders. This is the anti-hallucination control.

**Guardrails as first-class components.** "Never auto-submit," "never pad the digest," "no LinkedIn scraping," and the mandatory humanizer scan are encoded in the operating spec and enforced in the run, not aspirational values.

**The learning loop.** Weekly calibration reads real signals: reply rates by tier, edit-diffs on drafts (what the human changed is what they consider truthful), and recorded outcomes. It reweights the rubric only with stated rationale, keeping a version trail.

**Why cron + agent, not a server.** One operator, one laptop, near-zero cost. The failure mode (asleep Mac = missed run, no catch-up) is accepted for v1 rather than adding infrastructure.