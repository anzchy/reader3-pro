const { useEffect, useRef, useState } = React;
const SD = window.ReaderProData;
const { Toggle, ConfirmModal, LiveRegion } = window;

function ProviderRow(props) {
  const { provider, onAnnounce } = props;
  const [enabled, setEnabled] = useState(provider.enabled);
  const [apiKey, setApiKey] = useState("");
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState(false);

  const runTest = () => {
    setBusy(true);
    setTest(null);
    window.setTimeout(() => {
      setBusy(false);
      const ok = provider.isOllama ? true : provider.keySet || apiKey.length > 0;
      setTest(ok ? "ok" : "fail");
      onAnnounce(provider.name + " connection " + (ok ? "succeeded" : "failed"));
    }, 700);
  };

  return (
    <article className={"provider-card " + (enabled ? "is-enabled" : "")} data-testid={"provider-" + provider.id}>
      <header className="provider-head">
        <div>
          <h3 className="provider-name">{provider.name}</h3>
          <p className="provider-sub">{provider.isOllama ? "Local · no API key required" : provider.keySet ? "API key configured" : "No API key configured"}</p>
        </div>
        <div className="provider-head-actions">
          <span className="provider-state">{enabled ? "Enabled" : "Disabled"}</span>
          <Toggle
            checked={enabled}
            label={"Enable " + provider.name}
            data-testid={"provider-toggle-" + provider.id}
            onChange={(next) => {
              setEnabled(next);
              onAnnounce(provider.name + (next ? " enabled" : " disabled"));
            }}
          />
        </div>
      </header>

      <div className="provider-grid">
        <label className="field-label">Model
          <input className="field-control" defaultValue={provider.model} data-testid={"provider-model-" + provider.id} />
        </label>
        <label className="field-label">Base URL
          <input className="field-control" defaultValue={provider.baseUrl} data-testid={"provider-url-" + provider.id} />
        </label>
        {provider.needsKey && (
          <label className="field-label">API key
            {/* Spec §7.3: the stored key is never sent to the browser. The field
                shows a placeholder for a configured key and only carries what
                the user types this session. */}
            <input
              className="field-control"
              type="password"
              value={apiKey}
              autoComplete="off"
              placeholder={provider.keySet ? "•••••••••••••• (stored, hidden)" : "sk-…"}
              data-testid={"provider-key-" + provider.id}
              onChange={(event) => setApiKey(event.target.value)}
            />
          </label>
        )}
      </div>

      <div className="provider-actions">
        <button className="btn btn-primary btn-sm" type="button" data-testid={"provider-save-" + provider.id} onClick={() => onAnnounce(provider.name + " saved")}>Save</button>
        <button className="btn btn-secondary btn-sm" type="button" disabled={busy} data-testid={"provider-test-" + provider.id} onClick={runTest}>
          {busy ? "Testing…" : "Test connection"}
        </button>
        {/* Refresh models queries a running server for its installed models —
            only Ollama exposes that, so it is Ollama-only (spec §4.3). */}
        {provider.isOllama && (
          <button className="btn btn-secondary btn-sm" type="button" data-testid="provider-refresh-models" onClick={() => onAnnounce("Model list refreshed")}>Refresh models</button>
        )}
        {test === "ok" && <span className="state-line is-ok" data-testid={"provider-result-" + provider.id}>Connection OK</span>}
        {test === "fail" && <span className="state-line is-error" data-testid={"provider-result-" + provider.id}>Connection failed — add an API key first</span>}
      </div>

      {provider.isOllama && (
        <p className="inline-note" data-testid="ollama-hint">
          Ollama must be running locally. Start it with <code>ollama serve</code>, then pull a model with <code>ollama pull llama3</code>.
        </p>
      )}
    </article>
  );
}

function SettingsScreen(props) {
  const [confirm, setConfirm] = useState(null);
  const [announce, setAnnounce] = useState("");

  const destructive = {
    reindex: {
      title: "Rebuild all semantic indexes?",
      body: "Every indexed book will be re-embedded from scratch. This can take several minutes and existing embeddings are discarded.",
      label: "Rebuild indexes"
    },
    conversations: {
      title: "Delete all conversations?",
      body: "All AI conversations for every book will be permanently removed. This cannot be undone.",
      label: "Delete conversations"
    },
    cache: {
      title: "Clear local reading cache?",
      body: "Reading positions and cached chapters stored in this browser (IndexedDB) will be cleared. Your books, notes and settings on the server are untouched.",
      label: "Clear cache"
    }
  };

  return (
    <div className="settings-screen" data-testid="settings-screen">
      <LiveRegion message={announce} />
      <div className="settings-inner">
        <section className="settings-block">
          <h2 className="settings-title">AI providers</h2>
          <p className="settings-copy">
            Reader3 reads provider configuration from <code>config/ai_settings.json</code>. Keys are stored server-side and never returned to the browser.
          </p>
          {SD.providers.map((provider) => (
            <ProviderRow key={provider.id} provider={provider} onAnnounce={setAnnounce} />
          ))}
        </section>

        <section className="settings-block">
          <h2 className="settings-title">Retrieval</h2>
          <div className="provider-grid">
            <label className="field-label">Chunks per query
              <input className="field-control" type="number" defaultValue="6" min="1" max="20" data-testid="rag-chunks" />
            </label>
            <label className="field-label">Context window
              <input className="field-control" type="number" defaultValue="8000" step="500" data-testid="rag-context" />
            </label>
            <label className="field-label">Embedding model
              <input className="field-control" defaultValue="paraphrase-multilingual-MiniLM-L12-v2" data-testid="rag-embedding" />
            </label>
          </div>
        </section>

        <section className="settings-block">
          <h2 className="settings-title">Data</h2>
          <p className="settings-copy">These actions change stored state and each asks for confirmation first.</p>
          <div className="settings-actions">
            <button className="btn btn-secondary" type="button" data-testid="data-reindex" onClick={() => setConfirm("reindex")}>Rebuild all indexes</button>
            <button className="btn btn-secondary" type="button" data-testid="data-conversations" onClick={() => setConfirm("conversations")}>Delete all conversations</button>
            <button className="btn btn-secondary" type="button" data-testid="data-cache" onClick={() => setConfirm("cache")}>Clear reading cache (IndexedDB)</button>
          </div>
        </section>

        <section className="settings-block">
          <h2 className="settings-title">Export</h2>
          <p className="settings-copy">Exports contain books, notes, collections and conversations. Provider settings are exported without API keys (no keys).</p>
          <div className="settings-actions">
            <button className="btn btn-secondary" type="button" data-testid="export-json" onClick={() => setAnnounce("Export started")}>Export library JSON</button>
            <button className="btn btn-secondary" type="button" data-testid="export-settings" onClick={() => setAnnounce("Export started")}>Export settings (no keys)</button>
          </div>
        </section>
      </div>

      {confirm && (
        <ConfirmModal
          title={destructive[confirm].title}
          body={destructive[confirm].body}
          confirmLabel={destructive[confirm].label}
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            setAnnounce(destructive[confirm].label + " completed");
            setConfirm(null);
          }}
        />
      )}
    </div>
  );
}

Object.assign(window, { SettingsScreen, ProviderRow });
