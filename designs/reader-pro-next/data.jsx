/* Mock data for the Reader3 Pro "next" prototype.
   Shapes mirror designs/reader-pro-next/spec/reader-pro-spec.md §7.1 so the prototype
   can be read as a contract, not just a picture. Nothing here is fetched. */

const BOOKS = [
  {
    id: "the-art-of-spending-money_data",
    book_uuid: "b1f0c2a4-0001-4a10-9f11-2c9a51d0e001",
    title: "The Art of Spending Money",
    author: "Morgan Housel",
    cover: "assets/the-art-of-spending-money-cover.jpg",
    format: "epub",
    section_count: 32,
    index_status: "not_indexed",
    chunk_count: 0,
    progress: 20,
    collections: ["finance"]
  },
  {
    id: "psychology-of-money_data",
    book_uuid: "b1f0c2a4-0002-4a10-9f11-2c9a51d0e002",
    title: "The Psychology of Money",
    author: "Morgan Housel",
    cover: null,
    format: "epub",
    section_count: 24,
    index_status: "indexed",
    chunk_count: 812,
    progress: 68,
    collections: ["finance"]
  },
  {
    id: "thinking-in-systems_data",
    book_uuid: "b1f0c2a4-0003-4a10-9f11-2c9a51d0e003",
    title: "Thinking in Systems",
    author: "Donella H. Meadows",
    cover: null,
    format: "epub",
    section_count: 19,
    index_status: "indexing",
    chunk_count: 0,
    progress: 0,
    collections: []
  },
  {
    id: "the-timeless-way_data",
    book_uuid: "b1f0c2a4-0004-4a10-9f11-2c9a51d0e004",
    title: "The Timeless Way of Building",
    author: "Christopher Alexander",
    cover: null,
    format: "epub",
    section_count: 27,
    index_status: "error",
    chunk_count: 0,
    progress: 4,
    collections: []
  }
];

const PARAGRAPHS = [
  "If you’re confused about what a better life would look like, “one with more money” is an easy assumption. It’s such a simple idea that influences so many people. “Living a good life” is one of the most complicated topics that philosophers have debated for thousands of years. And “more money” is such an easy and quantifiable thing to chase.",
  "But the desire for more money and the things it can buy often obscures what you actually want: respect and admiration from other people.",
  "An easy connection to make is that if you had more money, you could buy a nicer car and a bigger house, and if you had a nicer car and a bigger house, people would respect and admire you more.",
  "Sometimes they will. But let me share my personal take.",
  "I’ve written letters to both of my kids hoping to pass along a few financial lessons I’ve learned in life. Something I wrote to both of them is that you might think you want a nicer car and a bigger house, but I’m telling you, you don’t. What you actually want is respect and admiration from other people, and you think that having nice stuff will bring it.",
  "But it rarely does—at least as much as you expected—especially from the people you want respect and admiration from.",
  "I love the idea of something called the reverse obituary. Most obituaries are written after a life has already been spent. The reverse obituary asks you to write it first, while every choice is still in front of you, and then work backwards from the sentences you would be proud to have read aloud.",
  "Try this: Write down what you want your obituary to say, then figure out how to live up to it. Almost nobody writes “he owned a very fast car” or “she kept up with her neighbors.” The things people actually want said about them are cheap to buy and expensive to fake.",
  "There is a version of this that applies to spending. Every purchase is a small vote for the kind of life you are trying to have. Most of those votes are cast without any deliberation at all, which is how people end up somewhere they never chose.",
  "The uncomfortable part is that the alternative is not frugality. Spending less is not the same as spending well. Plenty of people underspend their way into a life just as unexamined as the one they were trying to avoid, and they call it discipline.",
  "What separates the two is whether the money bought something you would defend out loud, to someone whose opinion you actually care about, on a day when you were being honest.",
  "That test is unglamorous and it works. It costs nothing to apply and it survives every change in income, which is more than can be said for almost any other rule about money."
];

window.ReaderProData = {
  books: BOOKS,
  book: BOOKS[0],

  collections: [
    { id: "col-finance", name: "finance", created_at: "2026-07-02T09:14:00Z", book_ids: ["the-art-of-spending-money_data", "psychology-of-money_data"] },
    { id: "col-systems", name: "systems & design", created_at: "2026-08-01T16:40:00Z", book_ids: ["thinking-in-systems_data", "ghost-book_data"], stale: 1 }
  ],

  stats: [
    { label: "Books", value: "4", note: "In this library" },
    { label: "Indexed", value: "1", note: "25% indexed" },
    { label: "Sections", value: "102", note: "Across all books" },
    { label: "Chunks", value: "812", note: "Semantic search" }
  ],

  /* Library search results, grouped by book (spec §6.5). Each book carries more
     than three hits so the "Show more" 3 -> 10 expansion is demonstrable. */
  libraryResults: [
    {
      book_id: "the-art-of-spending-money_data",
      book_title: "The Art of Spending Money",
      total: 6,
      hits: [
        { section: 3, section_title: "Copyright", score: 0.41, snippet: "The Art of Spending <mark>Money</mark>: simple choices for a richer life." },
        { section: 8, section_title: "May I Have Your Attention Please", score: 0.88, snippet: "the desire for more <mark>money</mark> and the things it can buy often obscures what you actually want" },
        { section: 8, section_title: "May I Have Your Attention Please", score: 0.84, snippet: "“more <mark>money</mark>” is such an easy and quantifiable thing to chase" },
        { section: 14, section_title: "Wealth Without Independence", score: 0.79, snippet: "<mark>Money</mark> is most useful when it gives you control over your time." },
        { section: 19, section_title: "Utility vs. Status", score: 0.66, snippet: "spending <mark>money</mark> on status is the most expensive way to buy the cheapest thing" },
        { section: 25, section_title: "Risk and Regret", score: 0.58, snippet: "the <mark>money</mark> you did not spend is the only kind you can still change your mind about" }
      ]
    },
    {
      book_id: "psychology-of-money_data",
      book_title: "The Psychology of Money",
      total: 4,
      hits: [
        { section: 2, section_title: "Luck & Risk", score: 0.81, snippet: "nothing is as good or as bad as it seems, and <mark>money</mark> amplifies both" },
        { section: 7, section_title: "Freedom", score: 0.77, snippet: "the highest dividend <mark>money</mark> pays is control over your own time" },
        { section: 11, section_title: "Reasonable > Rational", score: 0.63, snippet: "you are not a spreadsheet, and neither is your <mark>money</mark>" },
        { section: 16, section_title: "You & Me", score: 0.52, snippet: "people playing different games with <mark>money</mark> should not take each other's cues" }
      ]
    }
  ],

  /* Reader (in-book) search results (spec §5.5). */
  readerResults: [
    { section: 3, section_title: "Copyright", occurrence: 1, snippet: "The Art of Spending <mark>Money</mark>: simple choices for a richer life." },
    { section: 8, section_title: "May I Have Your Attention Please", occurrence: 1, snippet: "the desire for more <mark>money</mark> and the things it can buy often obscures" },
    { section: 8, section_title: "May I Have Your Attention Please", occurrence: 2, snippet: "“more <mark>money</mark>” is such an easy and quantifiable thing to chase" },
    { section: 14, section_title: "Wealth Without Independence", occurrence: 1, snippet: "<mark>Money</mark> is most useful when it gives you control over your time." }
  ],

  toc: [
    { title: "Cover", section: 0, depth: 0 },
    { title: "Title Page", section: 1, depth: 0 },
    { title: "Copyright", section: 2, depth: 0 },
    { title: "Contents", section: 3, depth: 0 },
    { title: "Introduction: The Quest of the Simple Life", section: 4, depth: 0 },
    { title: "Part One · What You Actually Want", section: 5, depth: 0 },
    { title: "All Behavior Makes Sense with Enough Information", section: 6, depth: 1 },
    { title: "May I Have Your Attention Please", section: 8, depth: 1, active: true },
    { title: "The Reverse Obituary", section: 9, depth: 2 },
    { title: "The Happiest People I Know", section: 10, depth: 1 },
    { title: "Part Two · What It Costs", section: 12, depth: 0 },
    { title: "Everything You Don’t See", section: 13, depth: 1 },
    { title: "Wealth Without Independence", section: 14, depth: 1 },
    { title: "The Most Valuable Financial Asset Is Not Needing to Impress Anyone", section: 16, depth: 1 },
    { title: "What Makes You Happy", section: 17, depth: 1 },
    { title: "The Rich and the Wealthy", section: 18, depth: 1 },
    { title: "Utility vs. Status", section: 19, depth: 1 },
    { title: "Risk and Regret", section: 25, depth: 1 },
    { title: "Look at Them", section: 28, depth: 1 }
  ],

  chapter: {
    index: 8,
    total: 32,
    number: "SECTION 8 OF 32",
    title: "May I Have Your Attention Please",
    deck: "You think you want nice stuff, but what you really want is respect, admiration, and attention.",
    paragraphs: PARAGRAPHS
  },

  /* Seeded annotations (spec §5.4 / §7.1). Offsets are character indexes into
     the paragraph's text, which is how the prototype re-renders them. */
  annotations: [
    {
      id: "note-0001",
      chapter_index: 8,
      chapter_title: "May I Have Your Attention Please",
      paragraph: 1,
      start: 4,
      end: 106,
      type: "marker",
      color: "yellow",
      quote: "the desire for more money and the things it can buy often obscures what you actually want: respect",
      note_text: null,
      created_at: "2026-08-12T21:03:00Z"
    },
    {
      id: "note-0002",
      chapter_index: 8,
      chapter_title: "May I Have Your Attention Please",
      paragraph: 7,
      start: 0,
      end: 78,
      type: "note",
      color: null,
      quote: "Try this: Write down what you want your obituary to say, then figure out how to",
      note_text: "This is the one idea from the chapter I want to actually try. Draft mine before the end of the month.",
      created_at: "2026-08-12T21:11:00Z"
    },
    {
      id: "note-0003",
      chapter_index: 4,
      chapter_title: "Introduction: The Quest of the Simple Life",
      paragraph: 0,
      start: 0,
      end: 52,
      type: "underline",
      color: "blue",
      quote: "The simple life is not the cheap life; it is the chosen",
      note_text: null,
      created_at: "2026-08-11T08:22:00Z"
    },
    {
      id: "note-0004",
      chapter_index: 14,
      chapter_title: "Wealth Without Independence",
      paragraph: 2,
      start: 0,
      end: 61,
      type: "wavy",
      color: "green",
      quote: "Money is most useful when it gives you control over your time",
      note_text: null,
      created_at: "2026-08-13T19:47:00Z"
    }
  ],

  /* AI conversations (spec §5.6): history list is the five most recent. */
  conversations: [
    { id: "conv-9", title: "Why does status spending fail?", created_at: "2026-08-14T20:31:00Z", messages: 6 },
    { id: "conv-8", title: "Summarize the reverse obituary", created_at: "2026-08-13T10:02:00Z", messages: 4 },
    { id: "conv-7", title: "Compare with Psychology of Money", created_at: "2026-08-11T17:55:00Z", messages: 12 },
    { id: "conv-6", title: "Key claims in part one", created_at: "2026-08-09T09:20:00Z", messages: 8 },
    { id: "conv-5", title: "Background on Housel", created_at: "2026-08-04T14:10:00Z", messages: 3 }
  ],

  aiThread: [
    { role: "user", text: "Why does the author think status spending backfires?", ts: "20:31" },
    {
      role: "assistant",
      ts: "20:31",
      text: "Because the purchase and the payoff are aimed at two different audiences. The spending is aimed at strangers, who notice the object and not the owner; the respect you actually wanted has to come from people who already know you, and they are not persuaded by objects. The chapter frames this as a mismatch rather than a moral failing — the strategy is rational, the target is wrong.",
      citations: [
        { section: 8, label: "Section 8 · May I Have Your Attention Please" },
        { section: 19, label: "Section 19 · Utility vs. Status" }
      ]
    }
  ],

  providers: [
    { id: "anthropic", name: "Anthropic Claude", status: "Enabled", tone: "enabled", enabled: true, needsKey: true, baseUrl: "https://api.anthropic.com", model: "claude-sonnet-4-5", keySet: true },
    { id: "openai", name: "OpenAI", status: "Disabled", tone: "disabled", enabled: false, needsKey: true, baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini", keySet: false },
    { id: "gemini", name: "Google Gemini", status: "Disabled", tone: "disabled", enabled: false, needsKey: true, baseUrl: "https://generativelanguage.googleapis.com", model: "gemini-2.0-flash", keySet: false },
    { id: "ollama", name: "Ollama (Local)", status: "Not connected", tone: "error", enabled: true, needsKey: false, baseUrl: "http://localhost:11434", model: "qwen3:8b", keySet: false, isOllama: true },
    { id: "openrouter", name: "OpenRouter", status: "Disabled", tone: "disabled", enabled: false, needsKey: true, baseUrl: "https://openrouter.ai/api/v1", model: "anthropic/claude-sonnet-4.5", keySet: false }
  ],

  indexErrors: [
    { book_id: "the-timeless-way_data", book_title: "The Timeless Way of Building", message: "Embedding model failed to load: paraphrase-multilingual-MiniLM-L12-v2", at: "2026-08-14 21:07" }
  ]
};
