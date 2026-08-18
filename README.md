# webextension

Build "Cognivue" — a professional, sophisticated analytics dashboard for an

AI-powered learning companion (a Chrome extension overlay for MOOC platforms

like Udemy, Coursera, and edX). The extension silently captures learning

activity, runs it through a RAG + LLM pipeline, and returns personalized

quizzes, mastery scores, and next-step recommendations. This app is the

web dashboard the extension talks to — plus an in-app simulated extension

popup so the full experience can be demoed without installing anything.

## PRODUCT CONTEXT

Problem: learners on MOOC platforms consume video passively. Completion

% is tracked, but actual comprehension is not. Cognivue closes that gap

by converting DOM signals (transcripts, progress, dwell time, revisits)

into per-topic mastery scores, adaptive quizzes, and a spaced-repetition

study plan — without requiring any platform APIs.

## TECH STACK

- React + TypeScript + Vite

- Tailwind CSS + shadcn/ui components

- Recharts for all data visualization

- Supabase for auth, database, and edge functions (this is the backend

  that will later receive events from the real Chrome extension)

- Framer Motion for micro-interactions and transitions

## INFORMATION ARCHITECTURE

Build these screens, connected via a persistent left sidebar (collapsible,

icon + label):

1. **Overview** (default landing page)

2. **Courses** (list → course detail)

3. **Topic Mastery** (radar + breakdown)

4. **Quizzes** (history + review)

5. **Study Plan** (spaced-repetition calendar view)

6. **Recommendations**

7. **Extension Simulator** (see below)

8. **Settings** (connected accounts: Google Calendar, platform connections)

## DESIGN DIRECTION — read carefully, this is the most important section

This must NOT look like a generic AI-generated SaaS template. Design for

a technical, data-dense, "control room" feel — the audience is students

and self-directed learners who want to trust the numbers.

- **Visual identity**: dark-mode-first (with a light mode toggle), deep

  charcoal/near-black background (avoid pure #000 and avoid default

  slate-900 — pick a custom near-black with a very slight warmth or

  cool tint), a single confident accent color (pick an electric indigo

  or teal — not the generic Tailwind blue-600), and a muted secondary

  accent for warnings/gaps (amber, not red, since "low mastery" isn't

  an error state).

- **Typography**: a distinct display font for headings (something with

  character — not Inter for everything). Use a monospace font for all

  numeric data (scores, percentages, timestamps) to reinforce the

  "instrumentation" feel — this is a strong differentiator, use it

  consistently on every score/stat.

- **Data density done well**: real dashboards feel information-rich but

  organized — use tight grid systems, small-multiple charts, and clear

  visual hierarchy rather than large empty cards with one number in them.

- **No decorative accent bars or edge stripes** on cards. Use subtle

  elevation (soft shadows, 1px borders at low opacity) and background

  tint to differentiate sections instead.

- **Motion**: subtle count-up animations on mastery scores, smooth chart

  entrance transitions, and a gentle pulse on "live capture" indicators

  — nothing gimmicky.

- **Empty/loading states**: design real skeleton loaders and empty states

  for every chart, not blank white boxes.

## CORE FEATURES BY SCREEN

### 1. Overview

- Top row: 4 stat cards — Active Courses, Overall Mastery (avg across

  topics, 0–100), Quizzes Completed This Week, Next Scheduled Review.

- "Completion vs. Mastery Gap" chart: grouped/paired bar chart per

  course showing video completion % next to actual mastery score — this

  is the headline insight of the whole product, make it visually strong.

- Recent activity feed: quiz completions, topic revisits, calendar

  events created — timestamped, compact list.

- "Learn Next" card: top 3 LLM-ranked recommendations with estimated

  time-to-completion, pulled from the Recommendations engine.

### 2. Courses

- Grid/list of courses (mock: 3–5 Udemy/Coursera-style courses) with

  platform badge, completion %, mastery %, last activity date.

- Course detail page: module/chapter breakdown, per-module mastery

  score, time-on-section chart, revisit frequency indicator.

### 3. Topic Mastery

- Radar chart: topic-wise strength/weakness across all subtopics in a

  selected course — this is a signature visualization, make it the

  centerpiece of this page.

- Below it: sortable table of topics with mastery score, the three

  weighted signal contributions (Quiz Performance 40%, Time-on-Section

  35%, Revisit Frequency 25%) shown as a small stacked bar per row, and

  trend arrow (improving/declining week over week).

- Clicking a topic opens a drawer with the mastery score formula

  breakdown for that specific topic.

### 4. Quizzes

- List of past quizzes grouped by course/module, each showing score,

  question type breakdown (MCQ vs short-answer), and date.

- Quiz review view: question, learner's answer, correct answer, LLM

  explanation — styled like a clean assessment report, not a chat log.

- "Generate practice quiz" button that shows the LLM prompt structure

  being assembled (context chunks retrieved, difficulty calibration) as

  a nice technical animation/step-through before showing mock generated

  questions — this visualizes the RAG pipeline for the viewer.

### 5. Study Plan

- Calendar view (week/month toggle) showing auto-generated events:

  Review Reminders, Quiz Sessions, Study Blocks — color-coded by type.

- Explain the forgetting-curve logic inline: a small interactive chart

  showing retention decay over time with review points marked, tied to

  a specific topic's actual mastery score.

- "Connected to Google Calendar" status card with a sync indicator

  (mock the OAuth connection state — a toggle for connected/disconnected

  is enough, no real OAuth needed unless Supabase auth makes it trivial).

### 6. Recommendations

- Ranked list of "Learn Next" suggestions (revisit weak topic / start

  related skill / proceed to next module), each with impact score,

  estimated time, and reasoning shown on hover/expand.

### 7. Extension Simulator

- This screen simulates what the Chrome extension overlay looks like

  injected into a MOOC video page. Build a mock "Udemy-style" video

  player frame (just a static dark player mock, doesn't need real

  video) with the extension's floating overlay UI docked to the side:

  - Live capture indicator (pulsing dot, "Capturing transcript...")

  - Real-time mastery score for the current section

  - A "Quiz me on this" button that triggers the same quiz-generation

    step-through animation as in Quizzes

  - Collapsible mini version (icon-only) vs expanded panel

- This is the most important screen for a demo — make the overlay itself

  look like a genuinely well-designed browser extension UI: compact,

  high information density, minimal chrome, floating card with strong

  shadow, doesn't feel like a website widget.

### 8. Settings

- Connected platforms (Udemy, Coursera, edX — toggle mock connections)

- Google Calendar connection status

- Notification preferences for review reminders

- Data/privacy note: "No video or audio is stored — only extracted

  transcript text and interaction signals."

## DATA MODEL (set up in Supabase)

- `courses`: id, title, platform, thumbnail_url, completion_pct,

  overall_mastery, created_at

- `topics`: id, course_id, title, mastery_score, quiz_perf_pct,

  time_on_section_pct, revisit_frequency_pct, last_updated

- `quizzes`: id, topic_id, course_id, question_type, questions (jsonb),

  score, completed_at

- `study_events`: id, topic_id, event_type (review/quiz/study_block),

  scheduled_at, status

- `recommendations`: id, topic_id, type, impact_score,

  estimated_minutes, reasoning, created_at

- `activity_log`: id, course_id, event_type, metadata (jsonb),

  created_at

Seed each table with realistic mock data across 3–5 courses (e.g.

"Machine Learning A-Z", "React - The Complete Guide", "Data Structures

& Algorithms") so every chart renders with real-looking numbers on

first load — don't leave any chart empty by default.

## WHAT NOT TO DO

- Don't use a generic blue/purple SaaS gradient theme

- Don't put an accent stripe or colored bar on any card or panel edge

- Don't leave any chart, table, or stat card without seeded mock data

- Don't make the Extension Simulator look like a regular dashboard

  panel — it must read as a floating browser overlay

- Don't use Inter (or a lookalike) for every single text element —

  differentiate headings from numeric data from body text

Build this as a fully working, navigable app with all seeded data wired

up — I want to click through every screen and see real charts, not

placeholders. pls see that u use suitable tech stack and for ai/ml use python with backend in python

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
