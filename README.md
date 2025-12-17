# reader 3

![reader3](reader3.png)

A lightweight, self-hosted EPUB reader that lets you read through EPUB books one chapter at a time. This makes it very easy to copy paste the contents of a chapter to an LLM, to read along. Basically - get epub books (e.g. [Project Gutenberg](https://www.gutenberg.org/) has many), open them up in this reader, copy paste text around to your favorite LLM, and read together and along.

This project was 90% vibe coded just to illustrate how one can very easily [read books together with LLMs](https://x.com/karpathy/status/1990577951671509438). I'm not going to support it in any way, it's provided here as is for other people's inspiration and I don't intend to improve it. Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like.

## Usage

The project uses [uv](https://docs.astral.sh/uv/). So for example, download [Dracula EPUB3](https://www.gutenberg.org/ebooks/345) to this directory as `dracula.epub`, then:

```bash
uv run reader3.py dracula.epub
```

This creates the directory `dracula_data`, which registers the book to your local library. We can then run the server:

```bash
uv run server.py
```

And visit [localhost:8123](http://localhost:8123/) to see your current Library. You can easily add more books, or delete them from your library by deleting the folder. It's not supposed to be complicated or complex.

## (Optional) Manual Setup: Semantic Search Dependencies (Phase 1)

Keyword search works out of the box. If you want to prepare your environment for future semantic search (P3), install the extra dependencies and download the embedding model:

```bash
uv add chromadb sentence-transformers
# activate当前文件夹下的虚拟环境
source .venv/bin/activate
python -c "import chromadb; import sentence_transformers; print('OK')"
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

The model download is large (~420MB) and is cached by HuggingFace after the first run.

默认会下载到 HuggingFace 的缓存目录：

 \- macOS / Linux：`~/.cache/huggingface/hub/`

 \- Windows：`%USERPROFILE%\.cache\huggingface\hub\`

## Search

### Reader (in-book)

Open any book (e.g. from the Library). In the left sidebar, type into **Search in this book…** to search within the current book. Results show a snippet; click any result to jump to that chapter and highlight all occurrences (scrolls to the selected match). Use **Clear** to remove results/highlights. Toggle **Case** for case-sensitive matching.

You can also deep-link to a highlighted chapter/occurrence:

`/read/{book_id}/{chapter_index}?q=your+term&occurrence=0`

Where `book_id` is the processed folder name (e.g. `dracula_data`).

### Library (cross-book)

On the Library page, use **Search across your library…** to search across all processed books (`*_data/`). Results are grouped by book; click a passage to open the book at the matching chapter/occurrence. Use **Sort** (relevance/title/author), **Case**, and **Clear** as needed.

## License

MIT
