---
title: "TrailMate AI: A Local Gemma Companion That Gets You Off the Screen"
published: false
tags: devchallenge, hf26challenge, ai, python
# TODO: cover_image: <add a screenshot or illustration URL>
---

*This is my submission for the Hacktoberfest 2026 DEV Open-Source AI Challenge, Week 1: "Touch Grass."* #devchallenge #hf26challenge

## 1. The problem

"Go outside more" is the easiest advice to give and one of the hardest to follow. The hurdle is rarely willpower alone. It's the small question of *what do I actually do* with twenty free minutes in a park. And most apps that promise to help add another screen, another account, or another service that wants your data.

I wanted to build the opposite: a tool whose success is measured by how quickly you stop using it.

## 2. What TrailMate AI does

TrailMate AI turns the intention to go outside into a small mission. You pick:

- how much time you have (10 to 60 minutes),
- what you're curious about (nature discovery, birds, plants, mindfulness, photography, walking),
- where you'll be (garden, campus, a park, or your own description),
- and how adventurous you feel.

A local AI model writes a short mission with three to five concrete tasks. You press Start, lock your phone, and go. Afterwards you tick off what you did, mark the mission complete, and write a journal entry about what you saw, heard or felt. Everything is stored in a SQLite file on your own computer.

> TODO: add a screenshot of the mission screen and one of the journal.

## 3. How it nudges you outside

A few deliberate design choices:

- **The "Go outside" screen.** After you start a mission, a dark, quiet screen says "Lock your phone. Go be here." with an optional countdown and a peek at your tasks if you need one.
- **The timer never decides for you.** When the countdown ends, the app says "Time's up" and waits. A mission is only complete when *you* say so and tick at least one task. The server enforces the same rule, so it isn't just a UI trick.
- **Reflection happens after, not during.** The journal invitation appears once the mission is done.
- **Honest numbers.** The dashboard says "self-reported" everywhere. TrailMate has no GPS or sensors, so it shows `0` verified minutes and explains why rather than pretending.

## 4. Why local, open-weight AI matters here

A nature journal is personal. It records where you go, when, and how you feel. Sending that to a cloud service felt wrong for this app. With an open-weight model running locally:

- your journal and your location descriptions stay on your machine,
- there is no account, no API key and no per-request cost,
- it keeps working offline after the one-time model download,
- and anyone can inspect, swap or improve the model and the code.

## 5. Why Gemma and Ollama

I chose **Gemma 3 (4B)** because it's small enough to run on an ordinary laptop while still being good at short, structured writing. **Ollama** makes running it a single install and a single HTTP endpoint on `localhost`, which is a gift for a beginner-friendly project.

> TODO: add your real machine (CPU/RAM/GPU), how long the model download took, and how long a mission actually took to generate on your computer. Only include numbers you measured.

## 6. Architecture and technical decisions

```text
Browser (HTML/CSS/vanilla JS)
   -> FastAPI routers (HTTP only)
      -> services (mission logic, journal logic, Ollama client)
         -> SQLite   and   -> Ollama (Gemma 3) on localhost
```

The decisions I care most about:

**Treat model output as untrusted.** Ollama is asked for JSON that matches a schema, but I never assume it complied. The reply is parsed, validated with Pydantic (3 to 5 tasks, length limits), and screened by a conservative safety filter that rejects talk of trespassing, climbing, swimming, tasting plants or approaching wildlife.

**A labelled fallback instead of an error.** If Ollama isn't installed, the model isn't downloaded, the request times out, or the output is unusable, the app uses hand-written mission templates. Each mission stores whether it came from `"ai"` or `"fallback"`, and the UI badge says so. The app never claims Gemma wrote something Gemma didn't write.

**No pretend knowledge.** The prompt tells the model it has no weather, maps, trail conditions or wildlife data, and the interface says the same.

**Local-first by construction.** SQLite from the standard library, no external fonts or scripts, and a Content-Security-Policy that blocks any request that leaves the app.

**Prompt injection hygiene.** The user's place description is passed as delimited data, and the system prompt tells the model to ignore instructions inside it. This reduces the risk but isn't a guarantee.

## 7. Challenges and trade-offs

- **Slow, blocking AI calls.** A local model can take many seconds. I used plain synchronous routes so FastAPI runs them in worker threads and the server stays responsive.
- **Safety by keywords is blunt.** The filter can reject harmless sentences (like "never eat wild plants") and could miss subtle unsafe advice. I chose over-rejection plus a fallback, and I say so in the README.
- **Small models are uneven.** A 4B model can be repetitive or odd. Validation catches malformed output, not mediocre output.
- **Self-reported progress.** Verifying someone was outside would need GPS or sensors, which would cost privacy. I chose honesty over a more impressive-looking dashboard.
- **Scope.** I skipped weather, maps and plant identification on purpose. I'd rather ship fewer features that are real than many that aren't.

## 8. Tests and honest results

The automated tests use a temporary database and mock the AI layer, so they need no Ollama and no internet. They cover health, mission creation and persistence, the fallback generator, completion rules, journal CRUD, invalid input, missing records and statistics.

> TODO: run `python -m pytest -v` and paste the real summary line here (for example, "N passed"). Do not write a number until you've seen it.

What the tests do *not* cover: the quality of real Gemma output. 

> TODO: manually generate a handful of missions with Gemma and note honestly what you saw: how many were good, how many fell back and why, and any oddities. Report only what actually happened.

## 9. Demo and real outdoor test

> TODO: add a demo GIF or short video, and a link to the repository: `https://github.com/<your-username>/TrailMate-AI`.

> TODO: **do a real outdoor test and write about it truthfully.** Suggested notes to capture:
> - Where you went and for how long, and which mission settings you chose.
> - Whether the mission was AI-written or a template.
> - Which tasks you completed, which felt awkward, and which you skipped.
> - Whether locking your phone was easy, and whether the app helped or got in the way.
> - One moment you noticed that you'd have missed otherwise (only if it's true).
> - What you'd change about the mission or the interface.

I'm not including any user feedback or deployment link because there isn't any yet. TrailMate runs locally on your own computer.

## 10. What I learned and what's next

> TODO: edit this section so it reflects what *you* actually learned. These are the technical lessons the design points to:

- Designing for an unreliable model, with validation, a safety filter and a labelled fallback, matters more than prompt cleverness.
- "Honest by default" is a design constraint you have to build into data models (a `source` field, a zero for verified minutes), not just into copy.
- A strict Content-Security-Policy is a cheap way to enforce a privacy promise.

Next on my list: journal export, opt-in weather (clearly labelled as a network feature), richer mission history, and PWA offline support.

## Try it

The code is open source (MIT): TODO repository link. Setup instructions for Windows, Ollama and Gemma are in the README.

*Read the mission. Lock your phone. Go be here.*