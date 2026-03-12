# Changelog

All notable changes to SafeClaw will be documented in this file.

Every huge milestone, we add something new. We just hit **250 stars!**

---

## [0.4.0] - 2026-03-12 — 250-Star Milestone

### Added
- **Real Research Sources** — Research now searches actual academic and knowledge databases
  - arXiv API integration (academic papers, free, no API key)
  - Semantic Scholar integration (academic papers with citation counts, free)
  - Wolfram Alpha integration (computational knowledge, factual answers)
  - RSS feeds remain as supplementary sources
  - New commands: `research arxiv <query>`, `research scholar <query>`, `research wolfram <query>`

- **Super Simple AI Setup** — Enter your key and go
  - `setup ai sk-ant-...` — Auto-detects Anthropic, configures everything
  - `setup ai sk-...` / `setup ai AI...` / `setup ai gsk_...` — OpenAI, Google, Groq
  - `setup ai local` — Auto-installs Ollama, downloads model, configures SafeClaw
  - `setup ai local coding/writing/small` — Model presets for different use cases
  - `setup ai status` — Check what's configured
  - No YAML editing needed — the command handles config.yaml for you

- **Auto-Learning from User Mistakes** — Parser gets smarter over time
  - Word-to-number conversion: "select one two three" → "select 1 2 3"
  - Ordinals: "first", "second", "third" → 1, 2, 3
  - Common typo auto-correction: "remaind" → "remind", "summerize" → "summarize"
  - Shorthand expansion: "tmrw" → "tomorrow", "hrs" → "hours"
  - Auto-learns corrections: when a failed command is followed by a successful one, SafeClaw remembers the mapping for next time

### Changed
- Version bump to 0.4.0
- Research action now searches arXiv + Semantic Scholar by default instead of just RSS feeds
- Parser now auto-normalizes all input before matching
- CLI banner updated for 250-star milestone
- Config.yaml now includes wolfram_alpha API key option

---

## [0.3.0] - 2026-03-11 — 100-Star Milestone

### Added
- **Fuzzy Learning (Writing Style Profiler)** — Deterministic AI that learns HOW you write
  - Analyzes sentence length, vocabulary, punctuation habits, tone, structure
  - Builds a writing profile from your actual blog posts and text samples
  - Auto-generates system prompt instructions matching your voice
  - No LLM required — pure statistical text analysis
  - Profile grows more accurate with each sample

- **Non-Deterministic System Prompts** — Context-aware prompt builder
  - Combines learned writing style + task type + topic + user preferences
  - Different prompts for blog, research, coding, and general tasks
  - Time-of-day context awareness
  - Visual system architecture flow diagram (`flow` command)

- **Cron Auto-Blogging (No LLM)** — Schedule blog posts on cron
  - Fetches content from RSS feeds and crawled URLs
  - Summarizes with sumy (extractive, zero AI cost)
  - Three post templates: digest, single, curated
  - Publishes to any configured target on schedule
  - Configure via `auto_blogs` in config.yaml

- **Two-Phase Research Pipeline**
  - Phase 1 (Non-LLM, $0): Search RSS feeds, crawl URLs, summarize with sumy
  - Phase 2 (LLM, optional): User selects favorite sources, LLM analyzes in depth
  - Full session management: gather → select → analyze → results
  - Uses research-specific LLM provider (per-task routing)

- **Per-Task LLM Routing** — Different LLMs for different jobs
  - Configure separate providers for blog, research, coding, and general
  - `task_providers` section in config.yaml
  - Fall back to default provider when task-specific not configured

- **Coding Action** — Code tools with non-LLM and LLM modes
  - Non-LLM (always free): templates, stats, search, diff, regex testing
  - LLM (optional): generate, explain, review, refactor, document
  - 7 built-in code templates (Python, FastAPI, HTML, Dockerfile, GitHub Action)
  - Language detection for 40+ languages

### Changed
- Version bump to 0.3.0
- Updated config.yaml with per-task routing, auto-blog, and new feature sections
- Engine now initializes blog scheduler from config on startup
- Blog action feeds user writing into style profiler automatically
- Parser extended with research, code, style, autoblog, and flow intents

## [0.2.2] - 2026-02-24

### Added
- **Blogging Guide in README** — full setup and usage documentation for both deterministic and AI blogging
  - Step-by-step AI provider setup (local and cloud)
  - Publishing target configuration (WordPress, Joomla, SFTP, API)
  - Command reference tables for all blog operations
  - Deterministic vs AI comparison table
- Updated architecture diagram with AI Writer, Blog Publisher, and provider details
- Updated comparison table with AI blog and publishing rows
- Added setup pointers in `config/config.yaml` comments

## [0.2.1] - 2026-02-17

### Added
- **Blog without a language model** (50-star milestone feature)
  - Write blog news with natural language commands
  - Crawl websites for title, body, or non-title content
  - Auto-generate blog titles using extractive summarization — the most repeated, most representative content becomes the headline
  - Publish as plain .txt files
- 50-star celebration banner on CLI startup
- `safeclaw blog` CLI subcommand
- Blog intent patterns in command parser
- Next milestone (100 stars) noted in CLI banner and README

## [0.2.0] - 2026-02-17

### Added
- Social media monitor plugin (Twitter/X via Nitter, Mastodon, Bluesky)

### Fixed
- Ruff linting errors in social monitor plugin

## [0.1.9] - 2026-02-17

### Fixed
- CI: resolved all ruff lint errors
- Added security test suite

## [0.1.8] - 2026-02-17

### Fixed
- Critical security vulnerabilities across multiple modules (SSRF protection, shell sandboxing, crawl redirect validation)

### Added
- macOS support with platform-aware audio handling
- CI configuration

## [0.1.7] - 2026-02-17

### Added
- Device discovery plugin (Bluetooth scanning, network device discovery)

## [0.1.6] - 2026-02-17

### Added
- Easter eggs plugin (love, marriage, valentine responses with animated hearts)
- Piper TTS plugin for local text-to-speech
- Whisper STT plugin for local speech-to-text

## [0.1.5] - 2026-02-17

### Changed
- Removed false claim about LLM/Ollama integration

## [0.1.4] - 2026-02-17

### Added
- Plugin system for extending SafeClaw (official + community plugin directories, auto-loading)

## [0.1.3] - 2026-02-17

### Added
- Weather action using free APIs (no signup required)
- Weather API and command chaining docs in README

### Changed
- Switched to free weather APIs that need no signup

## [0.1.2] - 2026-02-17

### Added
- `__main__.py` for `python -m safeclaw` support
- Natural language understanding with user-learned patterns
- Command chaining with pipes (`|`, `->`) and sequences (`;`, `and then`)

## [0.1.1] - 2026-02-17

### Fixed
- HTTP client closed prematurely in crawl action
- Datetime overflow and HTTP client lifecycle bugs

### Added
- SQLite prepared statements for SQL injection safety
- `.gitignore` for Python artifacts and IDE files

## [0.1.0] - 2026-02-17

### Added
- Initial release of SafeClaw
- Rule-based command parser (keyword, regex, fuzzy matching, dateparser)
- Core actions: files, shell, summarize, crawl, reminder, briefing, news, email, calendar
- Multi-channel support (CLI, Telegram, webhooks)
- SQLite-based memory (history, preferences, reminders, cache)
- RSS news aggregation with 50+ preset feeds across 8 categories
- Extractive summarization (LexRank, TextRank, LSA, Luhn, Edmundson)
- VADER sentiment analysis, keyword extraction, readability scoring
- PDF/DOCX/HTML/Markdown document reading
- Cross-platform desktop notifications
- Scheduler with APScheduler
- Optional NLP (spaCy NER), vision (YOLO), and OCR (Tesseract)
