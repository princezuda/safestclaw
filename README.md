# SafeClaw 🐾

**The zero-cost alternative to OpenClaw. No LLM required, though it is optional. No required API bills. Minimal attack surface. Runs on any machine.**

> **ONE HUNDRED STARS** — We hit ONE HUNDRED stars on GitHub! This milestone is our biggest update since our original release. It brings: **Real Research, Simple AI Setup, and Smart Learning.** Research now searches arXiv and Semantic Scholar for real academic papers, asks Wolfram Alpha for computational answers. `setup ai sk-ant-your-key` instantly configures Anthropic (or any provider) — or `setup ai local` for free Ollama. The parser auto-corrects typos, converts word-numbers ("one" → 1), and learns from your mistakes automatically. [See the new features below.](#-real-research-sources) Previous milestone: [Fuzzy Learning & Personalization.](#-writing-style-profiler)
While OpenClaw users are burning [$200/day](https://www.notebookcheck.net/Free-to-use-AI-tool-can-burn-through-hundreds-of-Dollars-per-day-OpenClaw-has-absurdly-high-token-use.1219925.0.html) and [$3,600/month](https://dev.to/thegdsks/i-tried-the-free-ai-agent-with-124k-github-stars-heres-my-500-reality-check-2885) on API tokens, SafeClaw delivers 90% of the functionality using traditional programming — rule-based parsing, ML pipelines, and local-first tools. **Your API bill: $0. Forever.** If you choose to use the language models for blogging, coding and research, then yeah, you'll have a bill, but you can also do all of that without a language model on safeclaw. We simply provide both options. 

SafeClaw uses VADER, spaCy, sumy, YOLO, Whisper, Piper, and other battle-tested ML techniques instead of generative AI. The result: deterministic, predictable, private, and completely free to run.

---

## Why SafeClaw?

| | SafeClaw | OpenClaw |
|---|---|---|
| **Monthly cost by default** | **$0** | $100–$3,600+ | 
| **Requires LLM** | No (optional for AI blogging, coding, and research all have no LLM options) | yes 
| **Prompt injection risk** | **Minimal** (only if a url you go to is malicious) | Yes (everywhere) |
| **Works offline** | **Yes** all default features, except weather | No |
| **Runs on any machine** | **Yes** (Linux, macOS, Windows) | Needs powerful hardware or cloud APIs |
| **Deterministic output** | **Yes** | No (LLM responses vary) |
| **Privacy** | **Local by default** (external only when you ask or setup an llm, e.g. weather) | Data always sent to API providers |


## Full Comparison: SafeClaw vs OpenClaw

| Feature | SafeClaw | OpenClaw |
|---|---|---|
| Self-hosted | ✅ | ✅ |
| Cross-platform (Linux, macOS, Windows) | ✅ | ✅ |
| No AI/LLM required | ✅ | ❌ |
| Offline capable | ✅ | ❌ |
| Zero API cost | ✅ | ❌ |
| Prompt injection risk | **Minimal** (only LLM research) | Everywhere |
| Privacy-first | ✅ (local by default) | ✅ |
| Voice (STT/TTS) | ✅ (Whisper + Piper, local) | ✅ (ElevenLabs, paid API) |
| Smart home control | ✅ | ✅ (via skills) |
| Bluetooth control | ✅ | ❌ |
| Network scanning | ✅ | ❌ |
| Social media summaries | ✅ (Twitter, Mastodon, Bluesky) | ❌ (requires separate skills) |
| Multi-channel | ✅ (CLI, Telegram, Webhooks) | ✅ (13+ platforms) |
| Web crawling | ✅ | ✅ |
| Summarization | ✅ (extractive) | ✅ (AI-generated) |
| RSS/News feeds | ✅ (50+ feeds) | ✅ (via skills) |
| Sentiment analysis | ✅ (VADER) | ✅ (AI) |
| Email integration | ✅ | ✅ |
| Calendar support | ✅ | ✅ |
| Document reading | ✅ | ✅ |
| Desktop notifications | ✅ | ✅ |
| Object detection | ✅ (YOLO) | ❌ |
| OCR | ✅ (Tesseract) | ❌ |
| Cron jobs | ✅ | ✅ |
| Webhooks | ✅ | ✅ |
| Plugin system | ✅ | ✅ (5,700+ skills) |
| Free-form chat | ❌ | ✅ | 
| Blog with and without  LLM  | ✅ no llm (extractive titles) with LLM, AI blogging | ❌ (always requires AI) |   
Blog publishing (WordPress, Joomla, SFTP) | ✅ | ❌ (requires plugins) |
| Writing style learning | ✅ (statistical profiling) | ❌ |
| Academic research (arXiv, Scholar) | ✅ (free, no API key) | ❌ |
| Wolfram Alpha | ✅ (computational knowledge) | ❌ |
| Simple  setup (enter key or local) simple telegram and blogging setup | ✅ (one command) | ❌ |
| Auto-learning from mistakes | ✅ (word-to-number, typo correction) | ❌ |
| Research pipeline | ✅ (two-phase, LLM optional) | ✅ (AI only) |
| Code templates & tools | ✅ (7 templates, offline utils) | ❌ (requires AI) |
| Auto-blog scheduling | ✅ (cron-based) | ❌ |
| Task-aware prompts | ✅ (per-task LLM routing) | ✅ |
| Command chaining | ✅ ("read email and remind me at 3pm") | ✅ |
| Autonomous multi-step tasks | ❌ | ✅ |
| Self-writing skills | ❌ | ✅ |
| Browser automation | ❌ | ✅ |

---

## Features

### 🗣️ Voice Control
* **Speech-to-Text** — Whisper STT runs locally, no cloud transcription
* **Text-to-Speech** — Piper TTS for natural voice output, completely offline
* **Voice-first workflow** — Talk to SafeClaw like you would any assistant

### 🏠 Smart Home & Device Control
* **Smart home integration** — Control your connected devices
* **Bluetooth device control** — Discover and manage Bluetooth devices
* **Network scanning** — Device discovery on your local network

### 📱 Social Media Intelligence
* **Twitter/X summarization** — Add accounts, get summaries of their activity
* **Mastodon summarization** — Follow and summarize fediverse accounts
* **Bluesky summarization** — Track and summarize Bluesky feeds
* No API tokens needed for public content

### 📰 RSS News Aggregation
* **50+ preset feeds** — Hacker News, Ars Technica, BBC, Reuters, Nature, and more
* **8 categories** — Tech, World, Science, Business, Programming, Security, Linux, AI
* **Custom feeds** — Import any RSS/Atom feed
* **Auto-summarization** — Extractive summaries with sumy (no AI)
* **Per-user preferences** — Customize your news sources

### 🔒 Privacy & Security
* **Self-hosted by default** — Your data stays local unless you explicitly request external info (like weather)
* **No API keys required** — Core features work completely offline
* **No cloud AI dependencies** — No tokens sent to OpenAI, Anthropic, or Google
* **Minimal prompt injection surface** — Core features (blogging, coding, commands) use rule-based parsing with zero LLM, so they're immune to prompt injection. Research and deep analysis *can* optionally use an LLM to synthesize sources — when enabled, content from external sources (arXiv abstracts, web pages) is fed to the LLM, which carries a minimal prompt injection risk. Phase 1 research (gathering/summarizing) never uses an LLM and is safe. We're transparent about this tradeoff.

### 📡 Multi-Channel
* **CLI** — Interactive command line with Rich formatting
* **Telegram** — Full bot integration
* **Discord** — Coming soon
* **Slack** — Coming soon
* **Webhooks** — Inbound and outbound support

### ⚡ Automation
* **Command chaining** — Combine actions naturally: "read my email and remind me at 3pm"
* **Web crawling** — Async crawling with depth limits and domain filtering
* **Summarization** — LexRank, TextRank, LSA, Luhn algorithms
* **Reminders** — Natural language time parsing with dateparser
* **Shell commands** — Sandboxed command execution
* **File operations** — Search, list, read files
* **Cron jobs** — Scheduled task automation
* **Daily briefings** — Weather, reminders, news from your feeds

### 📊 Text Analysis
* **VADER Sentiment** — Lexicon-based sentiment analysis
* **Keyword Extraction** — TF-IDF style extraction
* **Readability Scoring** — Flesch-Kincaid metrics

### 📧 Email Integration
* **IMAP Support** — Read emails from Gmail, Outlook, Yahoo
* **SMTP Support** — Send emails
* **Standard protocols** — No API keys required

### 📅 Calendar Support
* **ICS Files** — Import and parse .ics calendar files
* **CalDAV** — Connect to Google Calendar, iCloud (optional)
* **Event filtering** — Today, upcoming, by date range

### 📄 Document Reading
* **PDF** — Text extraction with PyMuPDF
* **DOCX** — Microsoft Word documents
* **HTML/Markdown/TXT** — Plain text formats

### 🔔 Notifications
* **Desktop notifications** — Cross-platform (macOS, Windows, Linux)
* **Priority levels** — Low, normal, high, urgent
* **Rate limiting** — Prevent notification spam

### 👁️ Optional ML Features
* **NLP** — spaCy named entity recognition (~50MB)
* **Vision** — YOLO object detection + OCR (~2GB)
* **OCR** — Tesseract text extraction from images (lightweight)

### 🔬 Real Research Sources
* **arXiv** — Search academic papers across CS, math, physics, biology, and more (free, no API key)
* **Semantic Scholar** — Academic papers with citation counts and author info (free, no API key)
* **Wolfram Alpha** — Computational knowledge engine for factual answers and calculations
* **Smart routing** — `research <topic>` searches all sources at once, or use `research arxiv`, `research scholar`, `research wolfram` individually
* **Two-phase pipeline** — Phase 1 gathers from real research sources ($0), Phase 2 does optional LLM deep analysis

### 🤖 Super Simple AI Setup
* **Just enter your key** — `setup ai sk-ant-your-key` and you're done. Auto-detects Anthropic, OpenAI, Google, Groq
* **Or go local** — `setup ai local` auto-installs Ollama, downloads a model, configures SafeClaw
* **Model presets** — `setup ai local small` (1.3GB), `setup ai local coding`, `setup ai local writing`
* **Status check** — `setup ai status` shows what's configured
* **Zero config files** — No YAML editing needed, the command does it for you

### 🧠 Smart Input Learning
* **Word-to-number** — Type "research select one two three" and SafeClaw understands "1 2 3"
* **Typo auto-correction** — "remaind me" → "remind me", "summerize" → "summarize"
* **Shorthand** — "tmrw" → "tomorrow", "hrs" → "hours", "mins" → "minutes"
* **Auto-learns from mistakes** — If a command fails and you retype it correctly, SafeClaw remembers the mapping for next time
* **No AI needed** — All corrections are rule-based and deterministic

### 💬 Optional LLM Command Understanding (NLU)
Don't want to memorise command syntax? Enable the NLU bridge and just talk naturally:

```
# Without NLU — you have to know the exact phrase:
remind me tomorrow at 9am to call the dentist

# With NLU enabled — any phrasing works:
hey, can you remind me to call the dentist tomorrow morning at 9?
I need a reminder for tomorrow at 9 to call the dentist
put a 9am reminder tomorrow: dentist call
```

The NLU bridge uses your configured LLM (any provider) as a **pure translator**:
it converts what you typed into the closest matching SafeClaw command string,
which then goes through the same rule-based parser as always. The LLM never
executes anything directly — it only re-words your input.

Enable in `config/config.yaml`:

```yaml
safeclaw:
  nlu:
    enabled: true
    provider: my-claude        # optional — uses active provider if omitted
    temperature: 0.0           # deterministic output
    show_translation: true     # shows "_(understood as: remind me ...)_" prefix
```

**Privacy note:** When NLU is enabled, unrecognised commands are sent to your
configured LLM provider. Recognised commands (the vast majority) are still
handled entirely locally with zero tokens consumed.

### ✍️ Writing Style Profiler
* **Learn your voice** — Feed SafeClaw your writing and it builds a 35-metric profile (sentence length, vocabulary, formality, contractions, structure, favorite words, etc.)
* **Persistent memory** — Your profile is stored in SQLite and improves with every sample
* **LLM prompt generation** — Profile converts to writing style instructions for any LLM provider
* **No AI required** — All analysis uses NLTK, VADER, and statistical methods locally

### 🔬 Research Pipeline
* **Two-phase workflow** — Phase 1 gathers and summarizes sources (no LLM, $0). Phase 2 does optional LLM deep analysis
* **Source gathering** — Searches RSS feeds and crawls URLs, auto-summarizes with Sumy
* **Source selection** — You pick which sources matter before spending any tokens
* **Deep analysis** — Optional LLM analyzes selected sources with structured output

### 💻 Coding Toolbox
* **7 templates** — python-script, python-class, python-test, fastapi-endpoint, html-page, dockerfile, github-action
* **Code stats** — Lines of code by language for any directory
* **Regex tester** — Test and explain regex patterns with match highlighting
* **Code search** — Regex search across code files
* **File diff** — Compare two files side by side
* **LLM-powered (optional)** — Generate, explain, review, refactor, document code

### 📅 Auto Blog Scheduler
* **Cron scheduling** — Schedule recurring blog generation with cron expressions
* **Source categories** — Pull from specific RSS categories automatically
* **Async-safe** — Detects scheduler type mismatches and warns clearly instead of silently failing

### 🧠 Smart Prompt Builder
* **Task-aware prompts** — Generates optimized prompts for blog, research, and coding tasks
* **Writing profile integration** — Automatically injects your writing style into blog prompts
* **Provider routing** — Each task type can use a different LLM provider
* **Flow diagram** — `show me the flow` displays the full architecture as ASCII art

### 🥚 Easter Eggs
* Built-in personality and hidden surprises — because tools should be fun

### 📝 Blogging — Two Modes

**Deterministic Blog (No AI, No Cost):**
* **Write blog news** — Add entries with natural language: "write blog news We shipped faster crawling today."
* **Crawl sites for content** — "crawl https://example.com for title content", "crawl example.com for body content"
* **Auto-generated titles** — Extractive summarization picks the most representative content as your headline. No LLM, just math.
* **Plain .txt output** — Your blog is a simple text file you can share anywhere

**AI Blog (Optional, Multi-Provider):**
* **Generate full posts from a topic** — "ai blog generate about sustainable technology"
* **Rewrite, expand, polish** — "ai rewrite blog", "ai expand blog"
* **AI headlines and SEO** — "ai headlines", "ai blog seo"
* **11 providers** — 5 local (Ollama, LM Studio, llama.cpp, LocalAI, Jan) + 6 cloud (OpenAI, Anthropic, Google, Mistral, Groq, custom)
* **Local AI = free + private** — Run Ollama or LM Studio and pay nothing

**Multi-Platform Publishing:**
* **WordPress** — REST API v2 with Application Passwords, JWT, or Basic Auth
* **Joomla** — Web Services API (Joomla 4+)
* **SFTP** — Upload HTML to any server
* **Generic API** — POST JSON to any endpoint
* **Front page management** — Set which post is the home page on any target

---


---

## Installation

### Using pipx (recommended)

```bash
# Install pipx if needed
# Linux:
sudo apt install pipx
# macOS:
brew install pipx

pipx ensurepath

# Install SafeClaw
pipx install safeclaw
```

### Using pip with virtual environment

```bash
# Create and activate venv
python3 -m venv ~/.safeclaw-venv
source ~/.safeclaw-venv/bin/activate

# Install SafeClaw
pip install safeclaw
```

### From source

```bash
git clone https://github.com/princezuda/safeclaw.git
cd safeclaw
pip install -e .
```

### Optional ML Features

```bash
# NLP - spaCy named entity recognition (~50MB)
pip install safeclaw[nlp]

# Vision - YOLO object detection + OCR (~2GB, requires PyTorch)
pip install safeclaw[vision]

# OCR only - text extraction from images (lightweight, requires Tesseract)
pip install safeclaw[ocr]

# All ML features
pip install safeclaw[ml]
```

**Requirements:** Python 3.11+, ~50MB disk (base), ~2GB additional for vision features. Runs on Linux, macOS, and Windows.

---

## Quick Start

```bash
# Start interactive mode
safeclaw

# Or with verbose logging
safeclaw --verbose
```

### Example Commands

```
> news                              # Get headlines from enabled feeds
> news tech                         # Get tech news only
> news categories                   # See all available categories
> news enable science               # Enable science feeds
> add feed https://blog.example.com/rss  # Add custom feed
> summarize https://news.ycombinator.com
> crawl https://example.com
> remind me to call mom tomorrow at 3pm
> morning briefing                  # Includes news from your feeds!
> check my email                    # View inbox (requires setup)
> read my email and remind me at 3pm # Chain commands naturally
> calendar today                    # Today's events from .ics
> analyze sentiment of this text    # VADER sentiment analysis
> read document.pdf                 # Extract text from documents
> write blog news We shipped a new feature today.  # Blog entry (no AI)
> crawl https://example.com for title content      # Crawl for blog
> blog title                        # Generate title from entries
> publish blog                      # Save blog as .txt
> blog                              # Interactive blog menu (AI or manual)
> ai blog generate about home automation            # AI writes a full post
> ai rewrite blog                   # AI polishes your draft
> publish blog to wp://mysite.com admin pass  # Publish inline — no config needed
> publish blog to my-wordpress               # Or use a saved target from config
> style learn I write concise, punchy posts.        # Teach SafeClaw your style
> style profile                     # View your writing profile
> research WebAssembly performance  # Search arXiv + Scholar + Wolfram
> research arxiv quantum computing  # Search arXiv papers directly
> research scholar machine learning # Search Semantic Scholar
> research wolfram integrate x^2   # Ask Wolfram Alpha
> research select 1,2,3             # Pick sources to analyze
> setup ai sk-ant-your-key-here      # Enter your Anthropic key, done
> setup ai local                    # Or auto-install Ollama (free!)
> setup ai status                   # Check what's configured
> code template python-class UserAuth Auth handler  # Generate boilerplate
> code templates                    # List all 7 templates
> code stats src/                   # Lines of code by language
> code regex \d{3}-\d{4} test 555-1234  # Test regex
> auto blog list                    # View scheduled auto-blogs
> show me the flow                  # Architecture diagram
> help
```

### CLI Commands

```bash
# News
safeclaw news                       # Headlines from enabled categories
safeclaw news tech                  # Tech news only
safeclaw news --categories          # List all categories
safeclaw news world -n 20           # 20 world news headlines
safeclaw news --add https://blog.example.com/rss --name "My Blog"
safeclaw news -s                    # With auto-summarization

# Summarize
safeclaw summarize https://example.com/article -n 5

# Crawl
safeclaw crawl https://example.com --depth 2

# Text analysis
safeclaw analyze "This product is amazing! I love it."
safeclaw analyze document.txt --no-readability

# Documents
safeclaw document report.pdf
safeclaw document paper.docx --summarize -n 5
safeclaw document notes.md --output extracted.txt

# Calendar
safeclaw calendar import --file calendar.ics
safeclaw calendar today
safeclaw calendar upcoming --days 14

# Blog — Deterministic (no AI)
safeclaw blog help                 # Blog feature guide
safeclaw blog write "New crawling features shipped today."
safeclaw blog show                 # View draft and published posts
safeclaw blog title                # Generate title from entries
safeclaw blog publish              # Save blog as .txt
safeclaw blog publish "My Custom Title"  # Publish with custom title

# Blog — AI-powered (requires ai_providers in config)
safeclaw blog                      # Interactive menu (AI or manual)
# ai blog generate about <topic>   # AI writes a full blog post
# ai rewrite blog                  # AI polishes your draft
# ai expand blog                   # AI makes it longer
# ai headlines                     # AI generates headline options
# ai blog seo                      # AI generates SEO metadata

# Publishing (requires publish_targets in config)
# publish blog to my-wordpress     # Publish to a specific target
# publish blog to all              # Publish to all targets
# set front page 123 on my-wp     # Set home page on a target

# Writing Style
safeclaw style learn "I write short, punchy sentences. No fluff."
safeclaw style profile             # View your writing profile

# Research (arXiv, Semantic Scholar, Wolfram Alpha)
safeclaw research "quantum computing"       # Search all sources
safeclaw research arxiv "transformer models" # arXiv papers
safeclaw research scholar "deep learning"   # Semantic Scholar
safeclaw research wolfram "integrate x^2"   # Wolfram Alpha
safeclaw research sources          # View gathered sources
safeclaw research select 1,2,3     # Pick sources for deep analysis
safeclaw research analyze          # LLM deep dive (optional)

# AI Setup (super simple)
safeclaw setup ai sk-ant-your-key  # Enter Anthropic key, done
safeclaw setup ai sk-your-key      # Or OpenAI key
safeclaw setup ai local            # Or auto-install Ollama (free)
safeclaw setup ai local coding     # Install coding-optimized model
safeclaw setup ai status           # Check your setup

# Coding Toolbox
safeclaw code templates            # List available templates
safeclaw code template python-class UserAuth "Auth handler"
safeclaw code stats src/           # Lines of code by language
safeclaw code search "TODO" src/   # Regex search code files
safeclaw code regex "\d{3}-\d{4}" test "555-1234"
safeclaw code diff file1.py file2.py

# Auto Blog
safeclaw auto blog setup           # Interactive setup wizard
safeclaw auto blog list            # View scheduled auto-blogs
safeclaw auto blog remove my-blog  # Remove a schedule

# Flow
safeclaw flow                      # Architecture diagram

# Webhooks
safeclaw webhook --port 8765

# Initialize config
safeclaw init
```

---

## Configuration

SafeClaw looks for configuration in `config/config.yaml`:

```yaml
safeclaw:
  name: "SafeClaw"
  language: "en"
  timezone: "UTC"

channels:
  cli:
    enabled: true
  webhook:
    enabled: true
    port: 8765
  telegram:
    enabled: false
    token: "YOUR_BOT_TOKEN"

actions:
  shell:
    enabled: true
    sandboxed: true
    timeout: 30
  files:
    enabled: true
    allowed_paths:
      - "~"
```

---

## Writing Style & Research Guide

### Writing Style Profiler

SafeClaw learns how you write by analyzing text samples. It builds a statistical profile — no AI needed.

```
> style learn I've been thinking about this for a while. The tech industry
  loves to overcomplicate things. Simple solutions work better.
  Profile updated (1 sample analyzed).

> style learn Here's what I learned from shipping 50 side projects: most
  of them failed. And that's completely fine!
  Profile updated (2 samples analyzed).

> style profile
  Writing Style Profile (2 samples analyzed)
  Tone: casual, neutral
  Avg sentence: 7 words
  Vocabulary: advanced (richness: 72%)
  Structure: conversational
  Uses contractions, first person, em-dashes
  Favorite words: easier, simple, something, learn
```

Your profile persists across sessions and automatically shapes AI blog prompts so generated posts sound like you.

**Commands:**

| Command | Description |
|---|---|
| `style learn <text>` | Feed SafeClaw a writing sample |
| `style profile` | View your current writing profile |

### Research Pipeline

Two-phase research: gather first (free), then optionally analyze with AI.

```
> research WebAssembly performance
  Found 8 sources. Use 'research sources' to view.

> research sources
  1. [HN] WebAssembly 2.0 Performance Benchmarks (4 sentences)
  2. [RSS] Wasm vs Native: A Deep Dive (3 sentences)
  ...

> research select 1,2,5
  Selected 3 sources for deep analysis.

> research analyze
  [LLM analyzes your selected sources with structured output]
```

**Commands:**

| Command | Description |
|---|---|
| `research <topic>` | Search feeds & crawl for sources (no LLM) |
| `research url <url>` | Add a specific URL as a source |
| `research sources` | View gathered sources with summaries |
| `research select 1,2,3` | Pick sources for deep analysis |
| `research analyze` | LLM deep dive on selected sources |
| `research results` | View analysis results |
| `research help` | Show all research commands |

### Coding Toolbox

Offline coding utilities plus optional LLM-powered features.

```
> code templates
  python-script, python-class, python-test, fastapi-endpoint,
  html-page, dockerfile, github-action

> code template python-class UserAuth Authentication handler
  @dataclass
  class UserAuth:
      """Authentication handler"""
      ...

> code stats src/
  python  ████████████████████ 19,348 lines (55 files) 100%

> code regex \d{3}-\d{4} test 555-1234
  \d — digit (0-9)
  Match: 555-1234
```

**Commands:**

| Command | Description |
|---|---|
| `code templates` | List all 7 available templates |
| `code template <type> [Name] [desc]` | Generate boilerplate code |
| `code stats <path>` | Lines of code by language |
| `code search <pattern>` | Regex search across code files |
| `code read <file>` | Display file with syntax info |
| `code diff <f1> <f2>` | Compare two files |
| `code regex <pattern> [test]` | Test and explain regex patterns |
| `code generate <desc>` | LLM generates code (optional) |
| `code explain <file>` | LLM explains code (optional) |
| `code review <file>` | LLM finds bugs (optional) |
| `code help` | Show all coding commands |

### Auto Blog Scheduler

Schedule recurring blog generation with cron expressions.

```
> auto blog setup
  [Interactive wizard]

> auto blog add weekly-tech "0 9 * * 1" tech,ai
  Auto-blog 'weekly-tech' scheduled: 0 9 * * 1

> auto blog list
  weekly-tech: 0 9 * * 1 (tech, ai)

> auto blog remove weekly-tech
  Removed.
```

### Task-Aware Prompt Builder

Each task type (blog, research, coding) gets optimized prompts. Configure per-task LLM providers:

```yaml
task_providers:
  blog: "local-ollama"       # Blog posts use local Ollama
  research: "openai"         # Research uses OpenAI for quality
  coding: "local-lmstudio"   # Code tasks use LM Studio
```

Run `show me the flow` to see the full architecture diagram.

---

## Blogging Guide

SafeClaw has two blogging modes. You can use either or both.

### Mode 1: Deterministic Blog (No AI)

Write entries manually, crawl websites for content, and let SafeClaw generate titles using extractive summarization (LexRank, TextRank, LSA, Luhn). No API keys, no cost, fully offline.

**Setup:** None — works out of the box.

```
> write blog news We shipped faster crawling today.
  Added entry (1 total).

> crawl https://example.com for title content
  Extracted 3 titles, added to draft.

> blog title
  Generated: "Faster Crawling Ships Today"

> publish blog
  Saved: 2026-02-24-faster-crawling-ships-today.txt
```

**Commands:**

| Command | Description |
|---|---|
| `write blog news <content>` | Add a manual entry to your draft |
| `crawl <url> for title content` | Extract page headings into draft |
| `crawl <url> for body content` | Extract main body text into draft |
| `crawl <url> for non-title content` | Extract non-heading text into draft |
| `blog title` | Generate a title using extractive summarization |
| `show blog` | View your draft and published posts |
| `edit blog <new content>` | Replace draft content |
| `publish blog` | Save as `.txt` locally |
| `publish blog My Custom Title` | Save with a custom title |

### Mode 2: AI Blog (Optional)

AI generates full blog posts from a topic. You can rewrite, expand, generate headlines, and produce SEO metadata. Supports 11 providers — 5 local (free) and 6 cloud (API key required).

**Setup:**

1. **Choose a provider.** For free/private, use a local provider. For quality/speed, use a cloud provider.

2. **Configure it in `config/config.yaml`** under `ai_providers`. Uncomment and fill in one or more:

**Local AI (free, private, no API key):**

```yaml
ai_providers:
  # Ollama — easiest local option
  - label: "local-ollama"
    provider: "ollama"
    model: "llama3.1"
    endpoint: "http://localhost:11434/api/chat"

  # LM Studio — GUI app with model browser
  # - label: "local-lmstudio"
  #   provider: "lm_studio"
  #   model: "local-model"
  #   endpoint: "http://localhost:1234/v1/chat/completions"

  # llama.cpp — high-performance C++ inference
  # - label: "local-llamacpp"
  #   provider: "llamacpp"
  #   model: "local-model"
  #   endpoint: "http://localhost:8080/v1/chat/completions"

  # Jan — user-friendly desktop app
  # - label: "local-jan"
  #   provider: "jan"
  #   model: "llama3.1-8b"
  #   endpoint: "http://localhost:1337/v1/chat/completions"
```

**Cloud AI (API key required):**

```yaml
ai_providers:
  # OpenAI
  - label: "openai"
    provider: "openai"
    api_key: "sk-..."              # https://platform.openai.com/api-keys
    model: "gpt-4o"

  # Anthropic (Claude)
  # - label: "anthropic"
  #   provider: "anthropic"
  #   api_key: "sk-ant-..."        # https://console.anthropic.com/settings/keys
  #   model: "claude-sonnet-4-20250514"

  # Google Gemini
  # - label: "google"
  #   provider: "google"
  #   api_key: "AI..."             # https://aistudio.google.com/apikey
  #   model: "gemini-1.5-flash"

  # Mistral
  # - label: "mistral"
  #   provider: "mistral"
  #   api_key: "..."               # https://console.mistral.ai/api-keys
  #   model: "mistral-large-latest"

  # Groq (fast inference)
  # - label: "groq"
  #   provider: "groq"
  #   api_key: "gsk_..."           # https://console.groq.com/keys
  #   model: "llama-3.1-70b-versatile"
```

3. **Install the local AI server** (if using local):

```bash
# Ollama (recommended — one command)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1

# LM Studio — download from https://lmstudio.ai
# Jan — download from https://jan.ai
# llama.cpp — git clone https://github.com/ggerganov/llama.cpp && make
```

4. **Use it:**

```
> blog
  1. AI Blog for You (Recommended) [ollama/llama3.1]
  2. Manual Blogging (No AI)

> 1
  What should the blog post be about?

> sustainable technology trends in 2026
  AI-Generated Blog Post
  Provider: ollama/llama3.1 (847 tokens)
  ---
  [full article here]
  ---
  What would you like to do?
    edit blog <changes>                      - Replace with your edits
    ai rewrite blog                          - Have AI polish/rewrite it
    ai expand blog                           - Have AI make it longer
    publish blog                             - Save as .txt locally
    publish blog to wp://mysite.com u pass   - Publish (shows preview first)
    publish blog to <saved-target>           - Publish to configured target

> publish blog to wp://mysite.com admin mypassword
  Ready to Publish

    Title:  Sustainable Technology Trends in 2026
    Words:  847
    Target: wp-mysite.com

  Preview:
  The clean energy revolution is accelerating...
  ... [truncated]

  ---
    confirm                    - Publish now
    change title <new title>   - Rename before publishing
    edit blog <new content>    - Edit content first
    cancel                     - Abort

> change title The Green Tech Surge: What's Coming in 2026
  Title updated.

    Title:  The Green Tech Surge: What's Coming in 2026
    Target: wp-mysite.com

  Type confirm to publish or cancel to abort.

> confirm
  Blog Published

    wp-mysite.com (wordpress): Post published successfully
    URL: https://mysite.com/the-green-tech-surge
```

**AI Commands:**

| Command | Description |
|---|---|
| `blog` | Interactive menu — choose AI or manual |
| `ai blog generate about <topic>` | Generate a full blog post from a topic |
| `ai rewrite blog` | Rewrite/polish your current draft |
| `ai expand blog` | Expand short content into a longer article |
| `ai headlines` | Generate 5 headline options for your draft |
| `ai blog seo` | Generate SEO metadata (title, description, keywords, slug) |
| `ai options` | Show local AI providers and install instructions |
| `ai providers` | Show cloud AI providers and API key links |
| `switch ai provider <label>` | Switch between configured providers at runtime |

**Multiple providers:** You can configure several providers at once. The first enabled one becomes the default. Switch at runtime with `switch ai provider <label>`.

### Publishing to Remote Platforms

Publish your blog (from either mode) to WordPress, Joomla, any SFTP server, or a generic API endpoint.

**No config needed — publish inline:**

```
publish blog to sftp://192.168.1.1 myuser mypassword
publish blog to sftp://host:2222 myuser mypassword /var/www/html
publish blog to wp://mysite.com admin myapppassword
publish blog to wordpress://mysite.com admin myapppassword
publish blog to joomla://mysite.com admin mypassword
publish blog to api://mysite.com/endpoint myapikey
```

Every publish command shows a **pre-publish preview** first — title, word count, content snippet, and target. You can then:

| Reply | Effect |
|---|---|
| `confirm` | Publish with the current title |
| `change title <new title>` | Rename and re-preview |
| `edit blog <content>` | Edit draft (cancels pending publish) |
| `cancel` | Abort without publishing |

Inline targets are remembered for the session under an auto-generated label (e.g. `wp-mysite.com`), so `publish blog to wp-mysite.com` works for subsequent posts without re-typing credentials.

**Permanent targets** (optional — add to `config/config.yaml` under `publish_targets`):

```yaml
publish_targets:
  # WordPress (REST API v2)
  - label: "my-wordpress"
    type: "wordpress"
    url: "https://mysite.com"
    username: "admin"
    password: "xxxx xxxx xxxx xxxx"   # Application Password (WP Admin > Users > Profile)
    wp_status: "publish"              # publish, draft, pending, private

  # Joomla (Web Services API, Joomla 4+)
  - label: "my-joomla"
    type: "joomla"
    url: "https://myjoomla.com"
    api_key: "your-joomla-api-token"  # Joomla Admin > Users > API Token
    joomla_category_id: 2

  # SFTP (any server)
  - label: "my-server"
    type: "sftp"
    sftp_host: "myserver.com"
    sftp_user: "deploy"
    sftp_key_path: "~/.ssh/id_rsa"
    sftp_remote_path: "/var/www/html/blog"

  # Generic API (POST JSON to any endpoint)
  - label: "my-api"
    type: "api"
    url: "https://api.mysite.com/posts"
    api_key: "your-bearer-token"
```

**Publishing commands:**

| Command | Description |
|---|---|
| `publish blog to wp://site.com user pass` | Publish to WordPress inline (no config) |
| `publish blog to sftp://host user pass` | Publish via SFTP inline |
| `publish blog to joomla://site.com user pass` | Publish to Joomla inline |
| `publish blog to api://endpoint key` | Publish to generic API inline |
| `publish blog to <saved-label>` | Publish to a target saved in config |
| `publish blog to all` | Publish to all enabled saved targets |
| `confirm` | Confirm a staged publish |
| `change title <new title>` | Change the title before confirming |
| `cancel` | Cancel a staged publish |
| `list publish targets` | Show configured targets |
| `set front page <id> on <target>` | Set which post is the home page |
| `show front page` | Show current front page setting |
| `list pages for <target>` | List available pages/posts on a target |

### Deterministic vs AI: Quick Comparison

| | Deterministic | AI-Powered |
|---|---|---|
| **Cost** | $0 | $0 (local) or pay-per-token (cloud) |
| **Privacy** | Fully local | Local AI = local; cloud = data sent to provider |
| **Titles** | Extractive summarization | LLM-generated |
| **Content** | Manual writing + crawling | LLM generates from topic |
| **Speed** | Instant | Seconds (local) to seconds (cloud) |
| **Determinism** | 100% reproducible | Varies by model/temperature |
| **Setup** | None | Install local AI or add cloud API key |

---

## Architecture

> Tip: Run `show me the flow` or `flow` inside SafeClaw to see the full interactive architecture diagram.

```
┌───────────────────────────────────────────────────────────────────────────┐
│                               SAFECLAW                                    │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌────────────┐       │
│  │  CHANNELS   │  │   ACTIONS   │  │  TRIGGERS    │  │    CORE    │       │
│  ├─────────────┤  ├─────────────┤  ├──────────────┤  ├────────────┤       │
│  │ • CLI       │  │ • Blog ──────────────────────────▸ AI Writer  │       │
│  │ • Telegram  │  │ • Research  │  │ • Cron       │  │ • Analyzer │       │
│  │ • Webhooks  │  │ • Code      │  │ • Webhooks   │  │ • Documents│       │
│  │ • Discord   │  │ • Style     │  │ • Auto Blog  │  │ • Notify   │       │
│  └─────────────┘  │ • Files     │  │ • Watchers   │  │ • Feeds    │       │
│                   │ • Shell     │  │ • Events     │  │ • Crawler  │       │
│  ┌─────────────┐  │ • Crawl     │  └──────────────┘  │ • Summary  │       │
│  │   VOICE     │  │ • Summarize │                    │ • Voice    │       │
│  ├─────────────┤  │ • Reminder  │  ┌──────────────┐  │ • Social   │       │
│  │ • Whisper   │  │ • Briefing  │  │  DEVICES     │  └────────────┘       │
│  │ • Piper TTS │  │ • News/RSS  │  ├──────────────┤                       │
│  └─────────────┘  │ • Email     │  │ • Bluetooth  │    ┌────────────┐     │
│                   │ • Calendar  │  │ • Network    │    │PERSONALIZE │     │
│  ┌─────────────┐  │ • Social    │  │ • Smart Home │    ├────────────┤     │
│  │ PROMPT      │  └──────┬──────┘  └──────────────┘    │ • Style    │     │
│  │ BUILDER     │         │                             │   Profiler │     │
│  ├─────────────┤         ▼                             │ • Writing  │     │
│  │ • Task-     │  ┌───────────────────────────────┐    │   Profile  │     │
│  │   aware     │  │       BLOG PUBLISHER          │    │ • 35+      │     │
│  │ • Style     │  │  WordPress • Joomla • SFTP    │    │   metrics  │     │
│  │   inject    │  │  Generic API • Auto Schedule  │    └────────────┘     │
│  │ • Provider  │  └───────────────────────────────┘                       │
│  │   routing   │                                      ┌────────────┐      │
│  └─────────────┘  ┌──────────────────────────────┐    │ AI WRITER  │      │
│                   │        COMMAND PARSER        │    ├────────────┤      │
│                   │  Keyword + Regex + Fuzzy     │    │ Local:     │      │
│                   │  + Date Parser + Specificity │    │ • Ollama   │      │
│                   │  Weighted Phrase Matching    │    │ • LM Studio│      │
│                   └──────────────────────────────┘    │ • llama.cpp│      │
│                                                       │ Cloud:     │      │
│  ┌─────────────────────────────────────────────────┐  │ • OpenAI   │      │
│  │                MEMORY (SQLite)                  │  │ • Anthropic│      │
│  │  History • Preferences • Reminders • Cache      │  │ • Google   │      │
│  │  Events • Blog Drafts • Writing Profiles        │  │ • Mistral  │      │
│  │  Research Sessions                              │  │ • Groq     │      │
│  └─────────────────────────────────────────────────┘  └────────────┘      │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## How It Works (No AI!)

### Command Parsing

Instead of burning tokens on LLMs, SafeClaw uses:

1. **Keyword matching** — Fast lookup of command keywords
2. **Regex patterns** — Structured extraction of parameters
3. **Fuzzy matching** — Typo tolerance with rapidfuzz
4. **Specificity-weighted phrase matching** — Longer, more specific phrases win over short keyword collisions
5. **Date parsing** — Natural language dates with dateparser

```
# Example: "remind me to call mom tomorrow at 3pm"
# → intent: "reminder"
# → params: {task: "call mom", time: "tomorrow at 3pm"}
# → entities: {datetime: 2024-01-16 15:00:00}
```

### Voice Pipeline

Fully local voice processing — no cloud APIs, no per-minute billing:

* **Whisper STT** — OpenAI's Whisper model running locally for speech recognition
* **Piper TTS** — Fast, high-quality text-to-speech with multiple voice options

### Summarization

Uses [sumy](https://github.com/miso-belica/sumy)'s extractive algorithms:

* **LexRank** — Graph-based, like PageRank for sentences
* **TextRank** — Word co-occurrence graphs
* **LSA** — Latent Semantic Analysis
* **Luhn** — Statistical word frequency

No neural networks, no API calls — pure math.

### Social Media Summarization

Add Twitter, Mastodon, or Bluesky accounts and get extractive summaries of their recent posts. No API tokens needed for public content. Useful for tracking industry voices, news accounts, or competitors without doomscrolling.

### Web Crawling

Async crawling with httpx + BeautifulSoup:

* Single page link extraction
* Multi-page crawling with depth limits
* Domain filtering and pattern matching
* Built-in caching

---

## Extending SafeClaw

### Custom Actions

```python
from safeclaw.actions.base import BaseAction

class MyAction(BaseAction):
    name = "myaction"

    async def execute(self, params, user_id, channel, engine):
        # Your logic here
        return "Action completed!"

# Register it
engine.register_action("myaction", MyAction().execute)
```

### Custom Intent Patterns

Add to `config/intents.yaml`:

```yaml
intents:
  deploy:
    keywords: ["deploy", "release", "ship"]
    patterns:
      - "deploy to (production|staging)"
    examples:
      - "deploy to production"
    action: "webhook"
```

### Plugin System

Plugins are automatically loaded from the plugins directory:

```
src/safeclaw/plugins/
├── official/          # Curated, tested plugins
│   └── smarthome.py
├── community/         # User-contributed plugins
│   └── your_plugin.py
├── base.py            # BasePlugin class
└── loader.py          # Plugin loader
```

---

## Who Is SafeClaw For?

**SafeClaw is for you if:**
* You want automation without API bills
* You're tired of unpredictable OpenClaw costs
* Privacy matters to you — your data stays local by default
* You prefer deterministic, predictable behavior
* You want voice control without paying for ElevenLabs
* You need social media monitoring without the doomscroll
* You want smart home and Bluetooth control in one tool
* You want AI blogging with your choice of provider (or no AI at all)
* You want to publish to WordPress, Joomla, or any server from the CLI
* You want an assistant that learns how you write and adapts to your style
* You want a research pipeline that gathers before it spends tokens
* You need code templates and utilities without spinning up an LLM
* You don't need free-form AI conversation

**Stick with OpenClaw if:**
* You need autonomous multi-step reasoning
* Free-form conversation is essential
* You want the AI to write its own skills
* Browser automation is a core need

---

## Development

```bash
# Clone the repo
git clone https://github.com/princezuda/safeclaw.git
cd safeclaw

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/safeclaw

# Linting
ruff check src/safeclaw
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Areas we'd love help with:

* More channel adapters (Discord, Slack, Matrix)
* Smart home integrations (Home Assistant, Philips Hue)
* Better intent patterns
* Additional social media platforms
* Documentation improvements
* Tests and CI/CD

## Acknowledgments

* [Whisper](https://github.com/openai/whisper) — Local speech-to-text
* [Piper](https://github.com/rhasspy/piper) — Local text-to-speech
* [sumy](https://github.com/miso-belica/sumy) — Extractive summarization
* [VADER](https://github.com/cjhutto/vaderSentiment) — Sentiment analysis
* [feedparser](https://github.com/kurtmckee/feedparser) — RSS/Atom feed parsing
* [dateparser](https://github.com/scrapinghub/dateparser) — Natural language date parsing
* [rapidfuzz](https://github.com/maxbachmann/RapidFuzz) — Fast fuzzy matching
* [httpx](https://github.com/encode/httpx) — Async HTTP client (AI providers, publishing)
* [FastAPI](https://fastapi.tiangolo.com/) — Webhook server
* [Rich](https://github.com/Textualize/rich) — Beautiful CLI output
* [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF parsing
* [python-docx](https://python-docx.readthedocs.io/) — DOCX parsing
* [icalendar](https://icalendar.readthedocs.io/) — ICS calendar parsing
* [desktop-notifier](https://github.com/samschott/desktop-notifier) — Cross-platform notifications
* [spaCy](https://spacy.io/) — Named entity recognition
* [YOLO](https://github.com/ultralytics/ultralytics) — Object detection
* [NLTK](https://www.nltk.org/) — Natural language toolkit (writing style analysis)
* [Ollama](https://ollama.com/) — Local AI inference (optional, for AI blogging)
* [LM Studio](https://lmstudio.ai/) — Desktop AI model runner (optional)

---

**SafeClaw** — Because your assistant shouldn't cost more than your rent. 🐾




