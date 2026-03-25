# Writing Style Guide

This is the voice. Follow it exactly.

---

## The voice

Direct. Confident. No hedging. No hype.

Write like you're explaining something to a smart friend who has ten minutes and zero patience for filler. Get to the point in the first sentence. If the first sentence could be deleted without losing anything, delete it.

The reader already knows "AI is everywhere" and "the world is changing fast." Skip all of that. Start with the thing.

---

## What this sounds like

**Good:**
> The zero-cost alternative to OpenClaw. No LLM required, though it is optional. No required API bills.

> SafeClaw delivers 90% of the functionality using traditional programming — rule-based parsing, ML pipelines, and local-first tools. The result: deterministic, predictable, private, and completely free to run.

> Yeah, you'll have a bill, but you can also do all of that without a language model.

**Bad:**
> In today's rapidly evolving AI landscape, developers are increasingly looking for solutions that seamlessly integrate cutting-edge technology while maintaining cost efficiency.

The bad version says nothing. The good version says everything in half the words.

---

## Sentence rhythm

Mix short and medium sentences. Never write three long sentences in a row. After a long explanation, hit it with a short one.

> SafeClaw uses VADER, spaCy, sumy, YOLO, Whisper, Piper, and other battle-tested ML techniques instead of generative AI. The result: deterministic, predictable, private, and completely free to run.

The colon before a short payoff is a go-to move. Use it.

---

## Numbers and specifics

Be specific. Not "many feeds" — "50+ feeds." Not "supports several algorithms" — "LexRank, TextRank, LSA, Luhn."

Put numbers in bold when they're the whole point: **$0**, **100 stars**, **90%**.

Put sizes and costs in parentheses when they're context, not the headline: (~50MB), (free, no API key).

---

## Em-dashes

Use em-dashes for asides and to separate a thing from what it does:

> **Real Research Sources** — Research now searches actual academic and knowledge databases

> **Privacy-first** — Your data stays local unless you explicitly request external info

Not a colon. Not a comma. The em-dash.

---

## Arrows

Use → for cause-effect and before-after:

> "remaind me" → "remind me"

> select one two three → select 1 2 3

---

## Honest about limitations

Don't pretend something works when it doesn't. If there's a tradeoff, say it plainly:

> **Minimal prompt injection surface** — Core features use rule-based parsing with zero LLM, so they're immune to prompt injection. Research and deep analysis *can* optionally use an LLM — when enabled, content from external sources is fed to the LLM, which carries a minimal risk. We're transparent about this tradeoff.

Admitting a limitation builds more trust than hiding it.

---

## Technical terms

Name the actual tools. Don't say "a speech recognition library" — say "Whisper STT." Don't say "a text-to-speech engine" — say "Piper TTS."

Readers who know the tool will trust you. Readers who don't will look it up. Both outcomes are good.

---

## Second person

Write to the reader directly: "your data," "you're done," "enter your key."

Not "users can configure" — "you can configure."

---

## What to never write

These phrases are banned:

- "In today's fast-paced world" / "In the rapidly evolving landscape"
- "seamlessly", "effortlessly", "powerful" (as a throwaway adjective)
- "cutting-edge", "state-of-the-art", "next-generation"
- "leverage" (use "use"), "utilize" (use "use"), "facilitate" (use "help")
- "game-changer", "revolutionary", "paradigm shift", "disruptive"
- "This post will explore...", "In this article we will look at..."
- "As we can see...", "It is important to note that..."
- "In conclusion", "To summarize", "To wrap things up"
- Rhetorical questions as section headers ("But what does this mean for you?")
- Fake enthusiasm: "Amazing!", "Incredible!", "Exciting news!"

If any of these appear in a draft, delete them and rewrite the sentence from scratch.

---

## Section headers

Short. Factual. No punctuation at the end.

Good: `## Real Research Sources`, `## Why SafeClaw?`, `## Setup`

Bad: `## Revolutionizing the Way You Think About AI-Powered Blogging Solutions`

---

## Lists

Parallel. Concise. Lead with the outcome, not the mechanism.

Good:
- **arXiv** — Search academic papers across CS, math, physics, biology (free, no API key)
- **Semantic Scholar** — Papers with citation counts and author info (free, no API key)
- **Wolfram Alpha** — Computational knowledge for factual answers

Bad:
- The arXiv integration allows users to search for and retrieve academic papers from a wide variety of scientific disciplines including computer science and mathematics.

---

## Code and commands

Show real commands. No placeholders like `<your-api-key>` unless there's genuinely no sensible default.

> `setup ai sk-ant-your-key` — Auto-detects Anthropic, configures everything

> `flatblog bot` — starts the bot

Keep examples short. One command per line. Explain what it does inline, not in a separate paragraph.

---

## The opener

Never start with a question. Never start with a definition ("Webster's defines X as..."). Never start with a statistic you're about to immediately contradict.

Start with the thing. State it plainly. Then explain why it matters.

> **The zero-cost alternative to OpenClaw.** No LLM required, though it is optional.

That's it. That's how you open.

---

## Length

Write until you've said everything that needs saying. Stop there.

If a section is padding — if it restates something said earlier, or fills space without adding information — cut it. A 600-word post that says everything is better than an 1,100-word post that repeats itself.

Target: 600–900 words for most posts. Go longer only if the topic genuinely requires it.
