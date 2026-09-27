> 附录来源：竞品调研 scratchpad `competitors.md`（gh api / iTunes lookup / AppBrain 实时抓取），抓取日期 2026-09-27；以下正文逐字复制，未改动。

# Reader3 Pro: competitive landscape

Numbers fetched on **2026-09-27**. Every GitHub star, fork, push, and license figure comes from a live `gh api repos/OWNER/NAME` call made on that date. None is from memory.

Reader3 Pro baseline (from `docs/feature-ledger.md`, F-001..F-041):
- **Formats and ingest:** EPUB only. PDF is a stub (F-038), and books are ingested through the CLI; in-app import is a stub (F-034).
- **Library:** a 3-pane library with collections.
- **Search:** keyword plus semantic/hybrid search using ChromaDB.
- **AI:** RAG Q&A and summaries over 5 providers, per-book conversation threads with export, and library-panel chat. All-books scope for that chat is a stub.
- **Notes:** annotations and notes (partial).
- **Themes:** light and dark.
- **Missing:** sync, OPDS, TTS, and PWA.

---

## (a) Ranked tables

### Open source, sorted by GitHub stars

| Rank | Product | Link | Stars | Forks | Last push | License | Category | One-liner |
|---|---|---|---|---|---|---|---|---|
| 1 | Open Notebook | https://github.com/lfnovo/open-notebook | 39,544 | 4,583 | 2026-09-20 | MIT | AI "chat with sources" (NotebookLM clone) | Open-source NotebookLM: multi-provider RAG over uploaded sources, notes, and podcasts. Not a reader. |
| 2 | KOReader | https://github.com/koreader/koreader | 29,945 | 1,925 | 2026-09-27 | AGPL-3.0 | E-ink / Android reader app | Reader for Kindle, Kobo, PocketBook, and Android covering PDF, DjVu, EPUB, FB2, and more. It has an AI plugin ecosystem (row 17). |
| 3 | Koodo Reader | https://github.com/koodo-reader/koodo-reader | 28,317 | 2,116 | 2026-09-27 | AGPL-3.0 | Cross-platform reader (desktop, mobile, web/Docker) | Ebook manager and reader with sync, backup, and custom-model AI (translate, dictionary, summarize, Ask AI, AI Chat). |
| 4 | Readest | https://github.com/readest/readest | 24,640 | 1,619 | 2026-09-27 | AGPL-3.0 | Cross-platform reader (Tauri: desktop, mobile, web) | Modern foliate-js-based reader. Its AI reading assistant (merged Jan 2026) does hybrid BM25+vector RAG with spoiler-safe context. |
| 5 | Calibre-Web | https://github.com/janeczku/calibre-web | 18,255 | 1,866 | 2026-09-20 | GPL-3.0 | Self-hosted library server | Web app for browsing, reading, and downloading books from a Calibre DB. Has OPDS, shelves, and Kobo sync. |
| 6 | Audiobookshelf | https://github.com/advplyr/audiobookshelf | 14,463 | 1,183 | 2026-09-26 | GPL-3.0 | Self-hosted audiobook/podcast server (ebook side is secondary) | Audiobook and podcast server that also has an EPUB/PDF web reader and collections. |
| 7 | Kavita | https://github.com/Kareadita/Kavita | 11,754 | 674 | 2026-09-27 | GPL-3.0 | Self-hosted reading server | Fast, multi-user reading server for manga, comics, and books. Has EPUB highlights and annotations, OPDS, collections, and reading lists. |
| 8 | bilingual_book_maker | https://github.com/yihong0618/bilingual_book_maker | 9,811 | 1,287 | 2026-09-27 | MIT | AI + EPUB tool (CLI) | Uses LLMs to translate EPUBs into bilingual editions. On-point for AI+EPUB but not a reader. |
| 9 | Foliate | https://github.com/johnfactotum/foliate | 8,764 | 419 | 2026-04-08 | GPL-3.0 | Linux desktop reader (GTK) | "Read e-books in style". Its foliate-js engine also powers Readest and paper-one. |
| 10 | Komga | https://github.com/gotson/komga | 6,696 | 415 | 2026-09-25 | MIT | Self-hosted media server | Server for comics, manga, and ebooks with an API, OPDS v1/v2, Kobo sync, and KOReader sync. |
| 11 | Calibre-Web-Automated | https://github.com/crocodilestick/Calibre-Web-Automated | 6,334 | 528 | 2026-09-26 | GPL-3.0 | Self-hosted library server | Calibre-Web fork with auto-ingest, rule-based "Magic Shelves", KOReader and Kobo sync, and send-to-eReader. |
| 12 | karpathy/reader3 (our upstream) | https://github.com/karpathy/reader3 | 3,872 | 486 | 2025-11-18 | none | AI + EPUB reader (minimal) | "Quick illustration of how one can easily read books together with LLMs." Copy-paste workflow with no built-in AI. Unmaintained since its creation day. |
| 13 | Thorium Reader | https://github.com/edrlab/thorium-reader | 2,883 | 238 | 2026-09-25 | BSD-3-Clause | Desktop reader (Readium, EDRLab) | Accessibility-first EPUB/PDF/audiobook reader with OPDS, LCP DRM, and TTS/read-aloud. |
| 14 | BookLore | https://github.com/booklore-app/booklore | 1,251 | 91 | 2026-09-25 | AGPL-3.0 | Self-hosted library server | Multi-user library with smart shelves, auto metadata, Kobo and KOReader sync, BookDrop imports, OPDS, and an EPUB/PDF/comic reader. The old `adityachandelgit/BookLore` path redirects here. The count is for the current repo (created 2024-12-13). |
| 15 | assistant.koplugin (KOReader AI) | https://github.com/omer-faruq/assistant.koplugin | 622 | 74 | 2026-09-26 | GPL-3.0 | AI plugin for a reader | Ask Claude, GPT, Gemini, DeepSeek, or Ollama about highlighted text in KOReader. A sibling, zeeyado/koassistant.koplugin, has 243★. |
| 16 | taylorren/ai-reader (reader3 fork) | https://github.com/taylorren/ai-reader | 12 | 2 | 2026-09-20 | none | AI + EPUB reader (reader3 fork) | reader3 fork with AI analysis, fact-check, and discussion. Supports Ollama and OpenAI-compatible APIs and exports highlights to Markdown. It is the top-starred reader3 fork. |
| 17 | xiaolai/paper-one ("Paper") | https://github.com/xiaolai/paper-one | 8 | 5 | 2026-09-27 | MIT | Desktop/mobile reader (Tauri 2 + React + Rust) | Personal, pre-release EPUB (foliate-js fork) and PDF (pdf.js) reader. It has anchored marks and notes, an optional on-device LLM "gloss" for words and phrases, and optional P2P sync. Created 2026-08-24; another agent is deep-diving it. |

Other on-point reader3 forks are all tiny: lsunay/reader3-docker (10★), jooonkim/reader (5★, local LLM), and yongkangc/llmreader (4★).

Found but left out of the ranking, because they are adjacent rather than readers (stars fetched the same day):
- calibre (desktop, 26,022★).
- Generic "chat with documents" RAG tools: kotaemon (25,778★), LocalGPT (22,198★), PrivateGPT (57,544★), AnythingLLM (66,515★), RAGFlow (91,348★), and paper-qa (9,251★).
- Zotero AI plugins: zotero-gpt (7,439★) and zotero-pdf-translate (11,927★).
- hectorqin/reader (11,024★), a Chinese web-novel/OPDS web reader.
- Omnivore (16,264★), whose read-it-later service has shut down.

Searches for "chat with epub" and "epub reader llm" turned up only repos with 0–1★.

### Closed / commercial, ranked by popularity proxy

| Rank | Product | Link | Popularity proxy | Forks | Last push | License | Category | One-liner |
|---|---|---|---|---|---|---|---|---|
| 1 | Amazon Kindle (+ "Ask this Book") | https://apps.apple.com/us/app/amazon-kindle/id302584613 | iOS US: 4.86★ from **5,854,143 ratings** (iTunes lookup API) | n/a | n/a | Proprietary | Store + reader app, AI Q&A | Since Dec 2025, "Ask this Book" gives spoiler-free RAG answers in the iOS app (US) on thousands of bestsellers. Readers and Android are due in 2026. Sources: [9to5Mac](https://9to5mac.com/2025/12/15/kindle-ask-this-book-ai-powered-feature-launches-in-ios-app/), [Authors Guild](https://authorsguild.org/news/statement-on-amazon-kindle-ask-this-book-ai-feature/). |
| 2 | Gemini Notebook (formerly NotebookLM) | https://en.wikipedia.org/wiki/NotebookLM | **30M+ users** as of Jul 2026 (up from about 17M MAU at end of 2025). Stated figure, per [ppc.land](https://ppc.land/google-kills-notebooklm-name-moving-30-million-users-to-gemini-notebook/) | n/a | n/a | Proprietary | AI "chat with sources" used as a book companion | Upload a book (PDF/text) to get cited Q&A, summaries, and audio overviews. Renamed on 2026-07-16. |
| 3 | 微信读书 WeRead (+ AI问书) | https://apps.apple.com/cn/app/id952059546 | iOS CN: 4.86★ from **1,697,700 ratings** (iTunes lookup, country=cn). About 210M cumulative users, a 2020 figure ([36kr](https://www.36kr.com/p/1577794035436295)). | n/a | n/a | Proprietary | Store + reader app, AI Q&A | Launched "AI问书" on 2024-04-23: long-press to get a Perplexity-style answer with book citations and follow-up questions. |
| 4 | Apple Books | https://apps.apple.com/us/app/apple-books/id364709193 | iOS US: 4.46★ from **93,679 ratings**. It is preinstalled, so this badly undercounts real usage. | n/a | n/a | Proprietary | Store + reader app | Mainstream EPUB/PDF reader with highlights, collections, and iCloud sync. There is no book Q&A feature I could confirm. |
| 5 | Moon+ Reader | https://www.appbrain.com/app/moon-reader/com.flyersoft.moonreader | Android: **~28M downloads**, 3.53★ from ~230K ratings (free edition). Pro has 4.27★ from ~76K. Third-party estimate from AppBrain. | n/a | n/a | Proprietary (freemium) | Android reader app | Heavyweight Android reader with TTS, annotations, OPDS, and sync via Dropbox/WebDAV. No AI Q&A confirmed. |
| 6 | 得到 Dedao (+ AI学习助手) | https://apps.apple.com/cn/app/id1016323413 | iOS CN: 4.45★ from **32,453 ratings**. The company states **65M+ platform users** ([dedao.cn](https://www.dedao.cn/)). | n/a | n/a | Proprietary | Courses + ebooks + audio, AI assistant | Its AI learning assistant answers questions and links back to Dedao books and courses. Q&A covers the platform's content, not your own files. |
| 7 | Glasp | https://glasp.co/ | **2M+ users** (stated on the site). Browser extension, so no store rating is comparable. | n/a | n/a | Proprietary (freemium) | Web/PDF highlighter + AI | Social web and PDF highlighter that builds an AI summary and "AI clone" from your highlights. It does not read EPUB. |
| 8 | Readwise Reader (+ Ghostreader) | https://apps.apple.com/us/app/readwise-reader/id1567599761 | iOS US: 4.61★ from **584 ratings** (iTunes lookup). Paid-only, so the rating count understates usage. | n/a | n/a | Proprietary (subscription) | Read-it-later + EPUB/PDF + AI | Ghostreader answers questions with links to the cited passage, defines and simplifies text, and is position-aware. Has TTS and exports highlights to Obsidian and Notion. |

For reference, these apps' iOS numbers came from the same lookups: Readest iOS has 4.51★ from 179 ratings, and Koodo Reader iOS has 3.0★ from 2 ratings (it launched in 2025). WeRead's US storefront shows only 27,656 ratings; the CN figure is the one used above.

---

## (b) Capability matrix

Legend: ✓ = present, partial = limited or plugin-based, ✗ = absent, ? = could not confirm. The "AI Q&A/RAG" column means Q&A grounded in the book's own text, not generic chat.

| Product | EPUB | PDF | Self-host | AI Q&A / RAG | Semantic search | Annotations / highlights | Sync | Multi-device / PWA | OPDS | TTS | Import / export | Collections / shelves |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Reader3 Pro (us)** | ✓ | ✗ (stub) | ✓ | ✓ (5 providers, per-book threads) | ✓ (ChromaDB, hybrid) | partial | ✗ | partial (browser on LAN, no PWA) | ✗ | ✗ | partial (CLI import, conversation export; library export stub) | ✓ |
| Open Notebook | partial (as a source) | ✓ | ✓ | ✓ | ✓ | ✗ (notes only) | ✗ | partial (web) | ✗ | ✓ (podcast audio) | partial | partial (notebooks) |
| KOReader | ✓ | ✓ | n/a (on-device) | partial (plugin) | ✗ | ✓ | ✓ (kosync, cloud) | ✓ (many devices) | ✓ | partial | ✓ | ✓ |
| Koodo Reader | ✓ | ✓ | ✓ (Docker web) | partial (Ask AI + AI chat on selection, custom models; no confirmed vector RAG) | ✗ | ✓ | ✓ (OneDrive, Google Drive, WebDAV, KOReader) | ✓ | ✓ (client + server) | ✓ | ✓ (notes to CSV/MD; Readwise, Notion, Anki) | ✓ |
| Readest | ✓ | ✓ | partial (self-host web possible; cloud-first) | ✓ (hybrid BM25+vector RAG, spoiler-safe, Ollama/AI Gateway; X-Ray WIP) | ✓ (vector index for AI) | ✓ | ✓ (Readest Cloud, KOReader) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Calibre-Web | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ (Kobo) | ✓ (web) | ✓ | ✗ | ✓ | ✓ |
| Audiobookshelf | ✓ | ✓ | ✓ | ✗ | ✗ | ? | ✓ (progress) | ✓ (apps + web) | ? | n/a (audio) | ✓ | ✓ |
| Kavita | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ (EPUB) | ✓ (progress) | ✓ (web) | ✓ | ? | partial | ✓ (collections, reading lists) |
| bilingual_book_maker | ✓ (in/out) | ✗ | ✓ (CLI) | ✗ (translation only) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ |
| Foliate | ✓ | ✓ | n/a (desktop) | ✗ | ✗ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | partial |
| Komga | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ (Kobo, KOReader) | ✓ (web) | ✓ (v1+v2) | ✗ | partial | ✓ |
| Calibre-Web-Automated | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ (Kobo, KOReader) | ✓ (web) | ✓ | ✗ | ✓ (auto-ingest) | ✓ (Magic Shelves) |
| karpathy/reader3 | ✓ | ✗ | ✓ | ✗ (manual copy-paste) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Thorium Reader | ✓ | ✓ | n/a (desktop) | ✗ | ✗ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | partial |
| BookLore | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ (Kobo, KOReader) | ✓ (web) | ✓ | ? | ✓ (BookDrop) | ✓ (smart shelves) |
| assistant.koplugin | ✓ (via KOReader) | ✓ | n/a | partial (selection-scoped prompts, no RAG) | ✗ | via host | via host | via host | via host | via host | partial | via host |
| taylorren/ai-reader | ✓ | ✗ | ✓ | partial (AI analysis of selection) | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ (MD export) | ✗ |
| paper-one | ✓ | ✓ | n/a (desktop) | partial (on-device "gloss" only) | ✗ | ✓ | ✓ (P2P, optional) | partial (macOS; iOS/Android WIP) | ✗ | ? | ? | ? |
| Kindle | ✗ (proprietary; EPUB via Send-to-Kindle) | ✓ | ✗ | ✓ (Ask this Book) | ? | ✓ | ✓ | ✓ | ✗ | ✓ | partial | ✓ |
| Gemini Notebook / NotebookLM | partial (upload) | ✓ | ✗ | ✓ (cited) | ✓ | ✗ | ✓ (cloud) | ✓ | ✗ | ✓ (audio overviews) | partial | ✓ (notebooks) |
| WeRead 微信读书 | ✓ (import) | ✓ | ✗ | ✓ (AI问书, cited) | ? | ✓ (social) | ✓ | ✓ | ✗ | ✓ | partial | ✓ |
| Apple Books | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ (iCloud) | ✓ | ✗ | partial (system) | partial | ✓ |
| Moon+ Reader | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ (Dropbox/WebDAV) | partial (Android) | ✓ | ✓ | ✓ | ✓ |
| Dedao 得到 | ✗ (own store) | ✗ | ✗ | partial (platform-content Q&A) | ? | ✓ | ✓ | ✓ | ✗ | ✓ (audio) | ✗ | ✓ |
| Glasp | ✗ | ✓ | ✗ | partial (AI over highlights) | ? | ✓ | ✓ | ✓ (browser + iOS) | ✗ | ✗ | ✓ | ✓ |
| Readwise Reader | ✓ | ✓ | ✗ | ✓ (Ghostreader, cited) | ? | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ (Obsidian, Notion, etc.) | ✓ (tags, views) |

---

## (c) Features we don't have, and who has them

1. **Spoiler-safe, position-limited RAG.** The AI's context is capped at what you have read so far.
   - Readest filters its context per page (about 1,500 characters per page).
   - Kindle's Ask this Book is spoiler-free by default, with a "whole book" toggle.
   - Readwise Ghostreader knows your reading position.
   - Our RAG retrieves from the whole book.
2. **Answers that link to the cited passage in the reader.** Readwise Ghostreader and WeRead AI问书 both do this, and WeRead also suggests follow-up questions. Readest X-Ray (WIP) navigates to cited evidence. Gemini Notebook cites its sources.
3. **X-Ray-style entity extraction:** characters, timelines, relationships, and claims with evidence. Readest X-Ray is WIP (PR #3119); Kindle has classic X-Ray.
4. **AI on a selection, inside the reader.** Examples are define, simplify, translate, and gloss in context.
   - Koodo has AI dictionary, translation, and encyclopedia, plus movable or pinnable popups.
   - paper-one has an on-device LLM gloss.
   - assistant.koplugin works on KOReader highlights.
   - WeRead lets you long-press and ask.
5. **Whole-book AI translation or bilingual output.** bilingual_book_maker produces bilingual EPUBs. Readest translates with DeepL and Yandex, and Koodo offers AI translation.
6. **TTS and read-along.** Readest does multilingual TTS and plays EPUB3 Media Overlays. Thorium, Koodo, Moon+, and Readwise also have TTS. Audio overviews are available in Gemini Notebook and Open Notebook.
7. **Cross-device sync.** This includes progress sync with KOReader and Kobo devices.
   - Koodo syncs through OneDrive, Google Drive, and WebDAV.
   - Readest uses Readest Cloud.
   - Komga, CWA, and BookLore support Kobo and KOReader sync.
   - paper-one does P2P sync.
8. **OPDS, as a server or a client.** Calibre-Web, Kavita, Komga, CWA, BookLore, Koodo, Readest, Thorium, and KOReader all have it. We have none.
9. **Highlight and note export to PKM tools.** Koodo sends to Readwise, Notion, and Anki. Readwise Reader sends to Obsidian and Notion. taylorren/ai-reader and KOReader export Markdown.
10. **More formats.** EPUB, PDF, MOBI, AZW3, FB2, CBZ, and Markdown are covered by Readest, Koodo, and KOReader. Kavita and Komga add comics and manga.
11. **Smart or rule-based shelves** that fill themselves from filters: CWA "Magic Shelves" and BookLore smart shelves.
12. **Import and ingest from the UI.** In-app upload is common. Folder auto-ingest exists in CWA and BookLore's BookDrop. Send-to-eReader by email is in CWA and Calibre-Web. For us, both in-app import (F-034) and book delete (F-035) are open.
13. **Multi-user accounts with per-user progress and shelves:** Kavita, Komga, Calibre-Web, and BookLore.
14. **Parallel or split-screen reading of two books:** Readest.
15. **Native mobile, desktop, or PWA clients:** Readest, Koodo, KOReader, and all the commercial apps.
16. **Web clipping or read-it-later ingest into the same library:** Readest (web page clipping) and Readwise Reader.

Where we are still differentiated:
- Among readers, we are the only self-hosted one with a Python backend and all of the following:
  - five first-class providers, including Anthropic, Gemini, and OpenRouter;
  - persistent **per-book conversation threads with export**;
  - **library-level chat**;
  - hybrid keyword+semantic search as a user-facing feature, not just AI plumbing.
- Readest is the closest overlap. Its AI is Ollama plus Vercel AI Gateway and is cloud-first, and its RAG index serves the chat only.

---

## (d) Method and date

- **Date fetched:** 2026-09-27, for all figures.
- **GitHub:** One live `gh api repos/OWNER/NAME` call per repo, reading stargazers_count, forks_count, pushed_at, license.spdx_id, language, archived, and description. Candidates came from several places:
  - The seed list in the task.
  - `gh search repos` for "chat with epub", "epub reader llm", "ebook reader AI", "reader3", "epub ai assistant", "book RAG chat", "read books with LLM", and "pdf reader ai chat".
  - `repos/karpathy/reader3/forks?sort=stargazers`.
  - Web search, which is how the KOReader AI plugins came up.
- **Capabilities:** Taken from each repo's README via `gh api repos/X/readme` and a keyword grep. For Readest I read the merged AI-assistant PR ("phase 2", merged 2026-01-24) through `gh`, and the ledger for our own product. A "?" means I could not confirm the feature, not that it is absent.
- **Closed products:**
  - iOS rating counts come from the iTunes lookup API (`itunes.apple.com/lookup?id=…`): US storefront for Kindle, Apple Books, and Readwise; CN storefront for WeRead and Dedao.
  - Moon+ Reader's download and rating counts are AppBrain's third-party estimate.
  - User numbers for NotebookLM, Glasp, Dedao, and WeRead (cumulative) are company or press statements, cited inline. These are estimates, not audited numbers.
  - Direct curl to the app stores was blocked in this environment. I did not use the gstack browse binary, because the API endpoints were enough.
- **Caveats:**
  - Stars measure GitHub attention, not usage.
  - Rating counts across storefronts and closed apps are not comparable to stars. That is why the two tables are kept separate.
