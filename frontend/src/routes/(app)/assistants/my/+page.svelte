<script>
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import yaml from 'js-yaml';
  import {
    Plus,
    Pencil,
    Trash2,
    Send,
    AlertCircle,
    Loader2,
    ChevronDown,
    Play,
    Upload,
    X,
    Download,
  } from "lucide-svelte";
  import ErrorBanner from "$lib/components/ErrorBanner.svelte";
  import SuccessBanner from "$lib/components/SuccessBanner.svelte";
  import {
    getMyAssistants,
    deleteMyAssistant,
    submitMyAssistant,
    importAssistant,
    exportAssistant,
    getModels,
    ApiError,
  } from "$lib/api.js";

  // ── Konstanten ────────────────────────────────────────────────────────────
  const STATUS_CLASS = {
    draft: "bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2",
    pending_review: "bg-light-ye/20 dark:bg-dark-ye/20 text-light-ye dark:text-dark-ye",
    active: "bg-light-gr/20 dark:bg-dark-gr/20 text-light-gr dark:text-dark-gr",
    disabled: "bg-light-re/20 dark:bg-dark-re/20 text-light-re dark:text-dark-re",
  };
  const STATUS_LABEL = {
    draft: "Entwurf",
    pending_review: "In Prüfung",
    active: "Aktiv",
    disabled: "Deaktiviert",
  };
  const AUDIENCE_LABELS = {
    student: "Schüler:innen",
    teacher: "Lehrkräfte",
    all: "Alle",
  };

  // ── State ─────────────────────────────────────────────────────────────────
  let items = $state([]);
  let total = $state(0);
  let loading = $state(true);
  let error = $state(null);
  let success = $state(null);
  let statusFilter = $state(null);
  let deleteTarget = $state(null);
  let deleteLoading = $state(false);
  let submitTarget = $state(null);
  let submitLoading = $state(false);

  // Import
  let importOpen = $state(false);
  let importFile = $state(null);
  let importModelOverride = $state("");
  let importingFile = $state(false);
  let importError = $state(null);
  let availableModels = $state([]);
  let importPreview = $state(null);
  // { name: string, system_prompt: string, model: string }
  let importModelMismatch = $state(false);

  async function parseImportPreview(file) {
      importPreview = null;
      importModelMismatch = false;
      try {
          const text = await file.text();
          const data = yaml.load(text);
          if (!data || typeof data !== 'object') return;
          const name = data.metadata?.name ?? null;
          const system_prompt = data.config?.system_prompt ?? null;
          const model = data.config?.model ?? null;
          importPreview = { name, system_prompt, model };
          if (model && availableModels.length > 0) {
              importModelMismatch = !availableModels.includes(model);
          }
      } catch {
          // Parsing-Fehler werden beim eigentlichen Import behandelt
      }
  }

  // ── Ladefunktion ───────────────────────────────────────────────────────────
  async function load() {
    loading = true;
    error = null;
    try {
      const result = await getMyAssistants(statusFilter ? { status: statusFilter } : {});
      items = result.items;
      total = result.total;
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  onMount(async () => {
    const [, models] = await Promise.allSettled([load(), getModels()]);
    if (models.status === "fulfilled") {
      availableModels = models.value.models?.map((m) => m.id) ?? [];
    }
  });

  // ── Import ────────────────────────────────────────────────────────────────
  function openImport() {
    importOpen = true;
    importFile = null;
    importModelOverride = "";
    importError = null;
    importPreview = null;
    importModelMismatch = false;
  }

  function closeImport() {
    importOpen = false;
    importError = null;
    importPreview = null;
    importModelMismatch = false;
  }

  async function doImport() {
    if (!importFile) return;
    importingFile = true;
    importError = null;
    try {
      const result = await importAssistant(importFile, importModelOverride || null);
      importOpen = false;
      success = "Assistent wurde importiert.";
      await load();
      goto(`/assistants/my/${result.id}`);
    } catch (e) {
      importError = e.message;
    } finally {
      importingFile = false;
    }
  }

  async function handleFileDrop(event) {
    event.preventDefault();
    const files = event.dataTransfer?.files;
    if (files?.length > 0) {
        importFile = files[0];
        await parseImportPreview(importFile);
    }
  }

  async function handleFileSelect(event) {
    const files = event.target.files;
    if (files?.length > 0) {
        importFile = files[0];
        await parseImportPreview(importFile);
    }
  }

  // ── Export ───────────────────────────────────────────────────────────────
  async function doExportItem(item) {
      const slug = item.name.toLowerCase().replace(/\s+/g, "-");
      try {
          await exportAssistant(item.id, `${slug}.yaml`);
      } catch (e) {
          error = e.message;
      }
  }

  // ── Einreichen ─────────────────────────────────────────────────────────────
  async function confirmSubmit() {
    submitLoading = true;
    error = null;
    try {
      await submitMyAssistant(submitTarget);
      submitTarget = null;
      await load();
      success = "Assistent wurde zur Prüfung eingereicht.";
    } catch (e) {
      error = e.message;
    } finally {
      submitLoading = false;
    }
  }

  // ── Löschen ───────────────────────────────────────────────────────────────
  async function confirmDelete(id) {
    deleteTarget = id;
    deleteLoading = true;
    error = null;
    try {
      await deleteMyAssistant(id);
      deleteTarget = null;
      await load();
      success = "Assistent wurde gelöscht.";
    } catch (e) {
      error = e.message;
    } finally {
      deleteLoading = false;
    }
  }

  function formatDate(dateString) {
    if (!dateString) return "–";
    return new Date(dateString).toLocaleDateString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  }

  function scopeLabel(assistant) {
    if (assistant.scope === "teaching_group" && assistant.scope_group_id) {
      return "Unterrichtsgruppe";
    }
    if (assistant.scope === "grade") {
      return `Jahrgang ${assistant.min_grade || "?"}${assistant.max_grade && assistant.min_grade !== assistant.max_grade ? `–${assistant.max_grade}` : ""}`;
    }
    const labels = {
      private: "Privat",
      subject_department: "Fachschaft",
      teachers: "Alle Lehrkräfte",
      activity_group: "AG/Kurs",
      all_students: "Alle Schüler:innen",
      all: "Alle",
    };
    return labels[assistant.scope] || assistant.scope;
  }
</script>

<div class="h-full overflow-y-auto p-6">
  <!-- Kopfzeile -->
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-xl font-semibold text-light-tx dark:text-dark-tx">
      Meine Assistenten
    </h1>
    <div class="flex items-center gap-2">
      <button
        onclick={openImport}
        class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium
               border border-light-ui-3 dark:border-dark-ui-3
               text-light-tx dark:text-dark-tx
               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
      >
        <Upload size={16} />
        Importieren
      </button>
      <button
        onclick={() => goto("/assistants/my/neu")}
        class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium
               bg-primary dark:bg-primary-dark text-white
               hover:opacity-90 transition-opacity"
      >
        <Plus size={16} />
        Neuer Assistent
      </button>
    </div>
  </div>

  <!-- Error & Success -->
  {#if error}
    <ErrorBanner message={error} onClose={() => (error = null)} />
  {/if}
  {#if success}
    <SuccessBanner message={success} onClose={() => (success = null)} />
  {/if}

  <!-- Filter -->
  <div class="mb-4">
    <label class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1">
      Status
    </label>
    <select
      bind:value={statusFilter}
      onchange={load}
      class="w-full max-w-xs px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
             bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
             focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark"
    >
      <option value="">Alle ({total || 0})</option>
      <option value="draft">Entwürfe</option>
      <option value="pending_review">In Prüfung</option>
      <option value="active">Aktiv</option>
      <option value="disabled">Deaktiviert</option>
    </select>
  </div>

  <!-- Loading -->
  {#if loading}
    <div class="flex justify-center py-8">
      <Loader2 class="w-6 h-6 animate-spin text-light-tx-2 dark:text-dark-tx-2" />
    </div>

  {:else if items.length === 0}
    <div class="text-center py-8">
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        Sie haben noch keine Assistenten erstellt.
      </p>
      <button
        onclick={() => goto("/assistants/my/neu")}
        class="mt-4 px-4 py-2 rounded-md bg-primary dark:bg-primary-dark text-white
               text-sm font-medium hover:opacity-90 transition-opacity"
      >
        Ersten Assistenten anlegen
      </button>
    </div>

  {:else}
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-xs font-semibold uppercase tracking-wide
                    text-light-tx-2 dark:text-dark-tx-2 border-b border-light-ui-2 dark:border-dark-ui-2">
            <th class="pb-3 pr-4">Name</th>
            <th class="pb-3 pr-4">Status</th>
            <th class="pb-3 pr-4">Zielgruppe</th>
            <th class="pb-3 pr-4">Sichtbarkeit</th>
            <th class="pb-3 pr-4">Aktualisiert</th>
            <th class="pb-3">Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {#each items as item (item.id)}
            <tr class="border-b border-light-ui-2 dark:border-dark-ui-2
                        hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors">
              <!-- Name -->
              <td class="py-3 pr-4">
                <a
                  href={`/assistants/my/${item.id}`}
                  class="font-medium text-light-tx dark:text-dark-tx
                         hover:text-primary dark:hover:text-primary-dark transition-colors"
                >
                  {item.name}
                </a>
                {#if item.description}
                  <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 line-clamp-1 mt-0.5">
                    {item.description}
                  </p>
                {/if}
              </td>

              <!-- Status -->
              <td class="py-3 pr-4">
                <span class="px-2 py-1 rounded-full text-xs {STATUS_CLASS[item.status]}">
                  {STATUS_LABEL[item.status] || item.status}
                </span>
                {#if item.reject_reason}
                  <div class="flex items-center gap-1 mt-1 text-xs text-light-re dark:text-dark-re">
                    <AlertCircle size={12} />
                    <span title={item.reject_reason}>{item.reject_reason}</span>
                  </div>
                {/if}
              </td>

              <!-- Zielgruppe -->
              <td class="py-3 pr-4 text-light-tx-2 dark:text-dark-tx-2">
                {AUDIENCE_LABELS[item.audience] || item.audience}
              </td>

              <!-- Sichtbarkeit -->
              <td class="py-3 pr-4 text-light-tx-2 dark:text-dark-tx-2">
                {scopeLabel(item)}
              </td>

              <!-- Aktualisiert -->
              <td class="py-3 pr-4 text-light-tx-2 dark:text-dark-tx-2 whitespace-nowrap">
                {formatDate(item.updated_at)}
              </td>

              <!-- Aktionen -->
              <td class="py-3">
                <div class="flex items-center gap-2 justify-end">
                  {#if item.status === "draft"}
                    <button
                      onclick={() => goto(`/assistants/my/${item.id}`)}
                      title="Bearbeiten"
                      class="p-1.5 rounded-md hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                             text-light-tx-2 dark:text-dark-tx-2 transition-colors"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onclick={() => (submitTarget = item.id)}
                      disabled={submitLoading}
                      title="Zur Prüfung einreichen"
                      class="p-1.5 rounded-md hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                             text-light-tx-2 dark:text-dark-tx-2 transition-colors
                             disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Send size={14} />
                    </button>
                    <button
                      onclick={() => (deleteTarget = item.id)}
                      title="Löschen"
                      class="p-1.5 rounded-md hover:bg-light-re/10 dark:hover:bg-dark-re/10
                             text-light-re dark:text-dark-re transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  {:else if item.status === "pending_review"}
                    <button
                      onclick={() => goto(`/assistants/my/${item.id}`)}
                      title="Ansehen"
                      class="p-1.5 rounded-md hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                             text-light-tx-2 dark:text-dark-tx-2 transition-colors"
                    >
                      <Play size={14} />
                    </button>
                    <button
                      onclick={() => (deleteTarget = item.id)}
                      title="Löschen"
                      class="p-1.5 rounded-md hover:bg-light-re/10 dark:hover:bg-dark-re/10
                             text-light-re dark:text-dark-re transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  {:else}
                    <button
                      onclick={() => goto(`/assistants/my/${item.id}`)}
                      title="Ansehen"
                      class="p-1.5 rounded-md hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                             text-light-tx-2 dark:text-dark-tx-2 transition-colors"
                    >
                      <Play size={14} />
                    </button>
                    {#if item.status === "active"}
                        <button
                            onclick={() => doExportItem(item)}
                            title="Als YAML exportieren"
                            class="p-1.5 rounded-md hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                                   text-light-tx-2 dark:text-dark-tx-2 transition-colors"
                        >
                            <Download size={14} />
                        </button>
                    {/if}
                  {/if}
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  <!-- Löschen-Bestätigungsmodal -->
  {#if deleteTarget !== null}
    <div
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onclick={() => (deleteTarget = null)}
      onkeydown={(e) => e.key === "Escape" && (deleteTarget = null)}
    >
      <div
        class="bg-light-bg-2 dark:bg-dark-bg-2 rounded-xl p-6 max-w-sm w-full"
        onclick={(e) => e.stopPropagation()}
      >
        <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-2">
          Assistent löschen?
        </h2>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
          Der Assistent "{items.find(i => i.id === deleteTarget)?.name ?? "..."}"
          wird dauerhaft gelöscht. Diese Aktion kann nicht rückgängig gemacht werden.
        </p>
        <p class="text-xs text-light-tx-3 dark:text-dark-tx-3 mb-6">
          Nur Assistenten im Status "Entwurf" oder "In Prüfung" können gelöscht werden.
        </p>
        <div class="flex justify-end gap-3">
          <button
            onclick={() => (deleteTarget = null)}
            disabled={deleteLoading}
            class="px-4 py-2 rounded-md text-sm font-medium
                   bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx
                   hover:bg-light-ui-3 dark:hover:bg-dark-ui-3 transition-colors
                   disabled:opacity-50"
          >
            Abbrechen
          </button>
          <button
            onclick={() => confirmDelete(deleteTarget)}
            disabled={deleteLoading}
            class="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium
                   bg-light-re dark:bg-dark-re text-white
                   hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {#if deleteLoading}
              <Loader2 size={14} class="animate-spin" />
            {:else}
              Löschen
            {/if}
          </button>
        </div>
      </div>
    </div>
  {/if}

  <!-- Einreichen-Bestätigungsmodal -->
  {#if submitTarget !== null}
    <div
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onclick={() => (submitTarget = null)}
      onkeydown={(e) => e.key === "Escape" && (submitTarget = null)}
    >
      <div
        class="bg-light-bg-2 dark:bg-dark-bg-2 rounded-xl p-6 max-w-sm w-full"
        onclick={(e) => e.stopPropagation()}
      >
        <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-2">
          Zur Prüfung einreichen?
        </h2>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
          Der Assistent "{items.find(i => i.id === submitTarget)?.name ?? "..."}"
          wird zur Admin-Freigabe eingereicht.
        </p>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-6">
          Nach Freigabe durch einen Admin wird er für die gewählte Zielgruppe sichtbar.
        </p>
        <div class="flex justify-end gap-3">
          <button
            onclick={() => (submitTarget = null)}
            disabled={submitLoading}
            class="px-4 py-2 rounded-md text-sm font-medium
                   bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx
                   hover:bg-light-ui-3 dark:hover:bg-dark-ui-3 transition-colors
                   disabled:opacity-50"
          >
            Abbrechen
          </button>
          <button
            onclick={confirmSubmit}
            disabled={submitLoading}
            class="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium
                   bg-primary dark:bg-primary-dark text-white
                   hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {#if submitLoading}
              <Loader2 size={14} class="animate-spin" />
            {:else}
              Einreichen
            {/if}
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

<!-- Import-Dialog -->
{#if importOpen}
  <div class="fixed inset-0 bg-black/50 z-40" onclick={closeImport}></div>
  <div class="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96
              bg-light-bg dark:bg-dark-bg rounded-xl shadow-2xl z-50 p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx">
        Assistenten importieren
      </h2>
      <button onclick={closeImport} class="p-1 rounded-lg hover:bg-light-ui-2 dark:hover:bg-dark-ui-2">
        <X size={20} class="text-light-tx-2 dark:text-dark-tx-2" />
      </button>
    </div>

    {#if importError}
      <div class="mb-4">
        <ErrorBanner message={importError} />
      </div>
    {/if}

    <div
      class="border-2 border-dashed rounded-xl p-8 text-center mb-4 transition-colors
             {importFile
               ? 'border-light-gr dark:border-dark-gr bg-light-gr/10 dark:bg-dark-gr/10'
               : 'border-light-ui-3 dark:border-dark-ui-3'}"
      ondragenter={(e) => e.preventDefault()}
      ondragover={(e) => e.preventDefault()}
      ondrop={handleFileDrop}
    >
      <input type="file" accept=".yaml,.yml" onchange={handleFileSelect}
             class="hidden" id="my-import-file-input" />
      <label for="my-import-file-input" class="cursor-pointer">
        <Upload size={48} class="mx-auto text-light-tx-2 dark:text-dark-tx-2 mb-2" />
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
          Datei auswählen oder hier ablegen
        </p>
        <p class="text-xs text-light-tx-3 dark:text-dark-tx-3 mt-1">
          {importFile?.name || "Keine Datei ausgewählt (.yaml)"}
        </p>
      </label>
    </div>

    <!-- Vorschau-Block -->
    {#if importPreview}
        <div class="mb-4 p-3 rounded-lg bg-light-bg-2 dark:bg-dark-bg-2
                    border border-light-ui-3 dark:border-dark-ui-3 space-y-2">
            {#if importPreview.name}
                <p class="text-sm font-medium text-light-tx dark:text-dark-tx">
                    {importPreview.name}
                </p>
            {/if}
            {#if importPreview.model}
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                    Modell: <span class="font-mono">{importPreview.model}</span>
                </p>
            {/if}
            {#if importModelMismatch}
                <p class="text-xs text-light-ye dark:text-dark-ye flex items-center gap-1">
                    <AlertCircle size={12} class="shrink-0" />
                    Dieses Modell ist nicht freigeschaltet — bitte unten überschreiben.
                </p>
            {/if}
            {#if importPreview.system_prompt}
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 line-clamp-3 whitespace-pre-wrap">
                    {importPreview.system_prompt}
                </p>
            {/if}
        </div>
    {/if}

    {#if availableModels.length > 0}
      <div class="mb-4">
        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
          Modell überschreiben (optional)
        </label>
        <select
          bind:value={importModelOverride}
          class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                 bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                 px-3 py-2 text-sm"
        >
          <option value="">Modell aus Datei übernehmen</option>
          {#each availableModels as m}
            <option value={m}>{m}</option>
          {/each}
        </select>
      </div>
    {/if}

    <div class="flex justify-end gap-2">
      <button
        onclick={closeImport}
        disabled={importingFile}
        class="px-4 py-2 rounded-md text-sm font-medium
               bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx
               hover:bg-light-ui-3 dark:hover:bg-dark-ui-3 transition-colors disabled:opacity-50"
      >
        Abbrechen
      </button>
      <button
        onclick={doImport}
        disabled={importingFile || !importFile}
        class="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium
               bg-primary dark:bg-primary-dark text-white
               hover:opacity-90 transition-opacity disabled:opacity-50"
      >
        {#if importingFile}
          <Loader2 size={16} class="animate-spin" />
          Wird importiert…
        {:else}
          <Upload size={16} />
          Importieren
        {/if}
      </button>
    </div>
  </div>
{/if}
