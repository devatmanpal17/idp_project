# ChaiGaram Learning Companion extension

This is an installable Chrome/Edge Manifest V3 extension for the ChaiGaram backend. It works on any normal HTTP or HTTPS page: articles, documentation, LMS lessons, course platforms, blogs, and video sites. It can capture visible captions, selected text, or the useful reading content of a page, then answer grounded questions and generate adaptive quizzes.

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

Only content you explicitly save and visible captions from pages containing learning media are sent to the configured backend. **Learn this page** extracts headings, paragraphs, lists, code, quotes, and captions while excluding navigation, forms, scripts, and decorative UI. With the default URL, data stays on `localhost` and is persisted in the local ChromaDB store.
