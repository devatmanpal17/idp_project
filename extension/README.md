# ChaiGaram Learning Companion extension

This is an installable Chrome/Edge Manifest V3 extension for the ChaiGaram backend. It works on any normal HTTP or HTTPS page: articles, documentation, LMS lessons, course platforms, blogs, and video sites. It can capture visible captions, selected text, or the useful reading content of a page, then answer grounded questions and generate adaptive quizzes.

The popup includes **Open my dashboard**. Its URL can be changed in Connection settings, along with the backend URL, so the same build works with local development or a deployed website/API.

**Learn this page** now indexes the active page/video context, opens an English teaching summary, and leaves a follow-up box for any question about that source. Quizzes receive the same active-source context and are explicitly generated in English.

On video pages, ChaiGaram tracks intervals of visible playback. Seeking ahead does not unlock skipped captions. Available timestamped caption tracks are sent to the backend, where future captions can be embedded into a sealed SQL store. Only chunks fully covered by observed intervals enter the searchable Chroma index. Keep English captions enabled; quiz generation waits until at least 50 observed caption words are available. On document pages, navigation, sidebars, related links, comments, and advertisements are removed before the lesson is indexed.

## Install for development

1. Start the backend from the `chaigaram` directory:

   ```powershell
   python -m uvicorn backend.app:app --port 8000
   ```

2. Open `chrome://extensions` or `edge://extensions`.
3. Enable **Developer mode**.
4. Choose **Load unpacked** and select this `extension` directory.
5. Open any article, lesson, documentation, or video page and choose **Open study sidekick**. Use **Learn this page**, save a selection, or enable video captions.

The backend URL and automatic caption capture can be changed from the extension's **Connection settings** page. API keys remain in the backend `.env`; they are never stored in the browser extension.

## How the model adapts

The extension does not run a model in the browser. Captured lesson text is embedded by Ollama, persisted in ChromaDB, and retrieved as grounded evidence for the local Llama model. Quiz attempts are evaluated server-side and persisted for mastery-history analytics.

## Privacy

With automatic capture enabled, available timestamped caption tracks, including future captions, are sent to the configured backend. Observation gating limits which chunks become searchable; it does not prevent future caption text from being stored or embedded. **Learn this page** extracts headings, paragraphs, lists, code, quotes, and captions while excluding navigation, forms, scripts, and decorative UI. With the default URL, backend data stays on `localhost` in SQL and ChromaDB. Pending AI request identifiers and their payload signatures are saved in extension local storage until a terminal result is received.

## Interrupted requests

The backend persists AI jobs and resumes queued or interrupted work after restart. Retrying the same operation with an unchanged payload after a lost extension connection reuses its request ID. Changed questions, source context, or quiz parameters create a new request. A page reload does not automatically reopen or restore the assistant's displayed response.

Interactive video actions finish embedding the observed caption batches before generation. Background speculation uses a separate worker and yields between embedding calls when interactive work is active. An embedding call already in progress cannot be interrupted.
