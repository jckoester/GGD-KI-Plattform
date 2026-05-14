<script>
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import {
    Bot,
    Send,
    Check,
    Loader2,
    AlertCircle,
    Play,
    RotateCcw,
    X,
  } from "lucide-svelte";
  import ErrorBanner from "$lib/components/ErrorBanner.svelte";
  import SuccessBanner from "$lib/components/SuccessBanner.svelte";
  import MessageBubble from "$lib/components/MessageBubble.svelte";
  import {
    getMyAssistants,
    createMyAssistant,
    updateMyAssistant,
    submitMyAssistant,
    getModels,
    streamChat,
    ApiError,
  } from "$lib/api.js";
  import { user } from "$lib/stores/user.js";

  // ── Parameter ──────────────────────────────────────────────────────────────
  let { data } = $props();
  const assistantId = data.id;
  const isNew = assistantId === "neu";

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

  const SCOPE_OPTIONS = [
    { value: "private", label: "Privat (nur ich)" },
    { value: "subject_department", label: "Fachschaft" },
    { value: "teachers", label: "Alle Lehrkräfte" },
    { value: "activity_group", label: "AG / Kursgruppe" },
    { value: "teaching_group", label: "Unterrichtsgruppe" },
    { value: "grade", label: "Jahrgang" },
    { value: "all_students", label: "Alle Schüler:innen" },
    { value: "all", label: "Alle" },
  ];

  const AUDIENCE_OPTIONS = [
    { value: "student", label: "Schüler:innen" },
    { value: "teacher", label: "Lehrkräfte" },
    { value: "all", label: "Alle" },
  ];

  // ── State ─────────────────────────────────────────────────────────────────
  let form = $state(emptyForm());
  let savedForm = $state(emptyForm());
  let loading = $state(false);
  let saving = $state(false);
  let submitting = $state(false);
  let error = $state(null);
  let success = $state(null);
  let models = $state([]);

  // ── Abgeleitete Werte ─────────────────────────────────────────────────────
  let isDraft = $derived(isNew || form.status === "draft");
  let dirty = $derived(
    JSON.stringify(form) !== JSON.stringify(savedForm) || isNew
  );

  // ━━━━━━━━━━━━━━━━━━━━━━ Formular-Funktionen ━━━━━━━━━━━━━━━━━━━━

  function emptyForm() {
    return {
      name: "",
      description: "",
      subject_id: null,
      system_prompt: "",
      model: "",
      temperature: null,
      max_tokens: null,
      audience: "student",
      scope: "private",
      scope_group_id: null,
      min_grade: null,
      max_grade: null,
      tags: "",
      icon: null,
      available_from: "",
      available_until: "",
      status: "draft",
      reject_reason: null,
      creator_role: null,
    };
  }

  function buildPayload() {
    const payload = {
      ...form,
      tags: form.tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean) || null,
      temperature: form.temperature ? parseFloat(form.temperature) : null,
      max_tokens: form.max_tokens ? parseInt(form.max_tokens) : null,
      min_grade: form.min_grade ? parseInt(form.min_grade) : null,
      max_grade: form.max_grade ? parseInt(form.max_grade) : null,
      scope_group_id: form.scope_group_id ? parseInt(form.scope_group_id) : null,
      available_from: form.available_from || null,
      available_until: form.available_until || null,
    };
    delete payload.sort_order;
    delete payload.status;
    delete payload.reject_reason;
    delete payload.creator_role;
    delete payload.created_by;
    delete payload.created_at;
    delete payload.updated_at;
    delete payload.updated_by_pseudonym;
    return payload;
  }

  // ━━━━━━━━━━━━━━━━━━━━━━ Lade- / Speicher-Logik ━━━━━━━━━━━━━━━━━━

  async function load() {
    if (isNew) {
      // Leeres Formular, Modelle laden
      try {
        models = (await getModels()).models ?? [];
      } catch (e) {
        error = e.message;
      }
      return;
    }

    loading = true;
    error = null;
    try {
      const result = await getMyAssistants();
      const assistant = result.items.find((a) => a.id === Number(assistantId));
      if (!assistant) {
        throw new Error("Assistent nicht gefunden");
      }
      form = {
        ...assistant,
        tags: assistant.tags?.join(", ") || "",
        temperature: assistant.temperature ?? null,
        max_tokens: assistant.max_tokens ?? null,
        min_grade: assistant.min_grade ?? null,
        max_grade: assistant.max_grade ?? null,
        scope_group_id: assistant.scope_group_id ?? null,
        available_from: assistant.available_from ?? "",
        available_until: assistant.available_until ?? "",
      };
      savedForm = { ...form };
      models = (await getModels()).models ?? [];
    } catch (e) {
      error = e.message;
      if (e.status === 404) {
        goto("/assistants/my");
      }
    } finally {
      loading = false;
    }
  }

  async function save() {
    if (!dirty) {
      error = "Keine Änderungen zum Speichern.";
      return;
    }

    // Pflichtfelder prüfen
    if (!form.name.trim() || !form.system_prompt.trim() || !form.model) {
      error = "Bitte füllen Sie alle Pflichtfelder aus (Name, System-Prompt, Modell).";
      return;
    }

    saving = true;
    error = null;
    try {
      const payload = buildPayload();
      let result;
      if (isNew) {
        result = await createMyAssistant(payload);
        // Umleiten zur Bearbeitungsseite mit der neuen ID
        goto(`/assistants/my/${result.id}`);
        return;
      } else {
        result = await updateMyAssistant(assistantId, payload);
        form.status = result.status;
      }
      savedForm = { ...form };
      success = "Änderungen wurden gespeichert.";
    } catch (e) {
      error = e.message;
    } finally {
      saving = false;
    }
  }

  async function submitAssistant() {
    if (dirty) {
      error = "Bitte zuerst speichern, bevor Sie einreichen.";
      return;
    }

    submitting = true;
    error = null;
    try {
      const result = await submitMyAssistant(assistantId);
      form.status = result.status;
      savedForm = { ...form };
      success = "Assistent wurde zur Prüfung eingereicht.";
    } catch (e) {
      error = e.message;
    } finally {
      submitting = false;
    }
  }

  async function resetForm() {
    if (isNew) {
      form = emptyForm();
      savedForm = emptyForm();
    } else {
      await load();
    }
    resetTestChat();
    error = null;
  }

  // ━━━━━━━━━━━━━━━━━━━━━━ Testchat ━━━━━━━━━━━━━━━━━━━━━

  let testConversationId = $state(null);
  let testMessages = $state([]);
  let testInput = $state("");
  let testIsStreaming = $state(false);
  let testError = $state(null);
  let testTextarea = $state(null);
  let testAreaRows = $state(1);

  function adjustTestTextareaHeight() {
    if (!testTextarea) return;
    testTextarea.rows = 1;
    testAreaRows = Math.min(Math.ceil(testTextarea.scrollHeight / 24), 6);
    testTextarea.rows = testAreaRows;
  }

  function resetTestChat() {
    testConversationId = null;
    testMessages = [];
    testInput = "";
    testError = null;
  }

  function handleTestKeydown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendTestMessage();
    }
  }

  async function sendTestMessage() {
    if (!testInput.trim() || testIsStreaming) return;

    if (dirty) {
      await save();
      if (dirty) {
        error = "Bitte zuerst speichern, bevor Sie den Testchat verwenden.";
        return;
      }
    }

    const userMessage = testInput.trim();
    testInput = "";
    adjustTestTextareaHeight();

    testMessages = [...testMessages, { role: "user", content: userMessage }];
    testMessages = [...testMessages, { role: "assistant", content: "" }];
    testIsStreaming = true;
    testError = null;

    try {
      const history = testMessages.slice(0, -1).map(m => ({ role: m.role, content: m.content }));
      for await (const item of streamChat(history, testConversationId, null, Number(assistantId), true)) {
        if (item.type === "start") {
          testConversationId = item.conversationId;
        } else if (item.type === "title" || item.type === "cost") {
          // ignorieren
        } else if (typeof item === "string") {
          const last = testMessages.length - 1;
          testMessages[last] = { ...testMessages[last], content: testMessages[last].content + item };
          testMessages = testMessages;
        }
      }
    } catch (e) {
      testError = e.message;
      if (testMessages.length > 0 && testMessages[testMessages.length - 1].content === "") {
        testMessages = testMessages.slice(0, -1);
      }
    } finally {
      testIsStreaming = false;
    }
  }

  // ━━━━━━━━━━━━━━━━━━━━━━ Lifecycle ━━━━━━━━━━━━━━━━━━━━━

  onMount(load);
</script>

<div class="flex min-h-0 flex-1">
  <!-- Hauptinhalt -->
  <main class="flex-1 overflow-y-auto p-6 max-w-4xl">
    <!-- Kopfzeile -->
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-3">
        {#if isNew}
          <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
            Neuer Assistent
          </h1>
        {:else}
          <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
            {savedForm.name || form.name || "Assistent bearbeiten"}
          </h1>
        {/if}
      </div>

      <!-- Aktionsbuttons -->
      <div class="flex items-center gap-3">
        {#if isNew || isDraft}
          <button
            onclick={save}
            disabled={saving || !dirty || !form.name.trim() || !form.system_prompt.trim() || !form.model}
            class="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium
                   bg-primary dark:bg-primary-dark text-white
                   hover:opacity-90 transition-opacity
                   disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {#if saving}
              <Loader2 size={16} class="animate-spin" />
              Speichern...
            {:else}
              <Check size={16} />
              Speichern
            {/if}
          </button>

          {#if isDraft && !isNew}
            <button
              onclick={submitAssistant}
              disabled={submitting || dirty}
              class="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium
                     bg-light-ye dark:bg-dark-ye text-light-tx dark:text-dark-tx
                     hover:opacity-90 transition-opacity
                     disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {#if submitting}
                <Loader2 size={16} class="animate-spin" />
                Einreichen...
              {:else}
                <Send size={16} />
                Einreichen
              {/if}
            </button>
          {/if}
        {:else}
          <!-- Readonly-Modus: Hinweis -->
          <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            {#if form.status === "pending_review"}
              Eingereicht – wartet auf Admin-Freigabe
            {:else if form.status === "active" || form.status === "disabled"}
              Dieser Assistent ist bereits freigegeben.
            {/if}
          </span>
        {/if}

        <button
          onclick={resetForm}
          disabled={loading}
          class="p-2 rounded-md hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                 text-light-tx-2 dark:text-dark-tx-2 transition-colors
                 disabled:opacity-50"
          title="Zurücksetzen"
        >
          <RotateCcw size={18} />
        </button>
        <button
          onclick={() => goto("/assistants/my")}
          class="p-2 rounded-md hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                 text-light-tx-2 dark:text-dark-tx-2 transition-colors"
          title="Zur Liste"
        >
          <X size={18} />
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

    {#if loading}
      <div class="flex justify-center py-8">
        <Loader2 class="w-6 h-6 animate-spin text-light-tx-2 dark:text-dark-tx-2" />
      </div>

    {:else}
      <div class="grid gap-6">
        <!-- Name & Beschreibung -->
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Name *
            </label>
            <input
              bind:value={form.name}
              disabled={!isDraft}
              placeholder="Name des Assistenten"
              class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                     disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Beschreibung
            </label>
            <textarea
              bind:value={form.description}
              disabled={!isDraft}
              placeholder="Kurze Beschreibung der Funktion dieses Assistenten"
              rows="2"
              class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                     disabled:opacity-50 disabled:cursor-not-allowed resize-none"
            ></textarea>
          </div>
        </div>

        <!-- Modell & Parameter -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Modell *
            </label>
            <select
              bind:value={form.model}
              disabled={!isDraft}
              class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                     disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value="">Bitte auswählen</option>
              {#each models as model}
                <option value={model.id}>{model.label || model.id}</option>
              {/each}
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Temperatur
            </label>
            <input
              bind:value={form.temperature}
              disabled={!isDraft}
              type="number"
              min="0"
              max="2"
              step="0.1"
              placeholder="0.0 – 2.0"
              class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                     disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Max. Tokens
            </label>
            <input
              bind:value={form.max_tokens}
              disabled={!isDraft}
              type="number"
              min="1"
              placeholder="optional"
              class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                     disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>
        </div>

        <!-- System-Prompt -->
        <div>
          <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
            System-Prompt *
          </label>
          <textarea
            bind:value={form.system_prompt}
            disabled={!isDraft}
            placeholder="Definieren Sie die Rolle und das Verhalten des Assistenten..."
            rows="6"
            class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                   focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                   disabled:opacity-50 disabled:cursor-not-allowed resize-none"
          ></textarea>
        </div>

        <!-- Zielgruppe & Sichtbarkeit -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Zielgruppe
            </label>
            <select
              bind:value={form.audience}
              disabled={!isDraft}
              class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                     disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {#each AUDIENCE_OPTIONS as opt}
                <option value={opt.value}>{opt.label}</option>
              {/each}
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Sichtbarkeit
            </label>
            <select
              bind:value={form.scope}
              disabled={!isDraft}
              class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                     disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {#each SCOPE_OPTIONS as opt}
                <option value={opt.value}>{opt.label}</option>
              {/each}
            </select>
          </div>
        </div>

        <!-- scope_group_id (konditionell) -->
        {#if ['subject_department', 'activity_group', 'teaching_group'].includes(form.scope)}
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Gruppen-ID
            </label>
            <input
              bind:value={form.scope_group_id}
              disabled={!isDraft}
              type="number"
              min="1"
              placeholder="ID der Gruppe"
              class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                     disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>
        {/if}

        <!-- Jahrgang (konditionell für grade-Scope) -->
        {#if form.scope === 'grade'}
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
                Jahrgang von
              </label>
              <input
                bind:value={form.min_grade}
                disabled={!isDraft}
                type="number"
                min="1"
                max="13"
                placeholder="z. B. 5"
                class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                       disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
                Jahrgang bis
              </label>
              <input
                bind:value={form.max_grade}
                disabled={!isDraft}
                type="number"
                min="1"
                max="13"
                placeholder="z. B. 10"
                class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                       disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>
          </div>
        {/if}

        <!-- Tags -->
        <div>
          <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
            Tags (kommagetrennt)
          </label>
          <input
            bind:value={form.tags}
            disabled={!isDraft}
            placeholder="z. B. Mathe, Geometrie, 7. Klasse"
            class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                   focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                   disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>

        <!-- Verfügbarkeit -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Verfügbar von
            </label>
            <input
              bind:value={form.available_from}
              disabled={!isDraft}
              type="datetime-local"
              class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                     disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
              Verfügbar bis
            </label>
            <input
              bind:value={form.available_until}
              disabled={!isDraft}
              type="datetime-local"
              class="w-full px-3 py-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark
                     disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>
        </div>

        <!-- Status-Anzeige (nur bei bestehendem Assistenten) -->
        {#if !isNew}
          <div class="space-y-2 pt-2 border-t border-light-ui-3 dark:border-dark-ui-3">
            <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
              Status
            </label>
            <span class="px-3 py-1 rounded-full text-xs {STATUS_CLASS[form.status]}">
              {STATUS_LABEL[form.status] || form.status}
            </span>
            {#if form.reject_reason}
              <div class="flex items-start gap-2 text-sm text-light-re dark:text-dark-re">
                <AlertCircle size={16} class="shrink-0 mt-0.5" />
                <span>{form.reject_reason}</span>
              </div>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  </main>

  <!-- Testchat-Spalte (immer sichtbar) -->
  <aside class="w-96 shrink-0 border-l border-light-ui-2 dark:border-dark-ui-2
                 bg-light-bg dark:bg-dark-bg p-4 flex flex-col">
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <Play size={18} class="text-light-gr dark:text-dark-gr" />
        <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx">
          Testchat
        </h2>
      </div>
      {#if testMessages.length > 0}
        <button
          onclick={resetTestChat}
          disabled={testIsStreaming}
          title="Testchat zurücksetzen"
          class="p-1.5 rounded-md hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                 text-light-tx-2 dark:text-dark-tx-2 transition-colors disabled:opacity-50"
        >
          <RotateCcw size={14} />
        </button>
      {/if}
    </div>

    {#if isNew}
      <div class="flex-1 flex items-center justify-center text-center px-4">
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
          Speichern Sie den Assistenten zuerst, um den Testchat zu nutzen.
        </p>
      </div>

    {:else if !form.model}
      <div class="flex-1 flex items-center justify-center text-center px-4">
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
          Wählen Sie ein Modell aus, um den Testchat zu nutzen.
        </p>
      </div>

    {:else}
      <!-- Nachrichtenbereich -->
      <div class="flex-1 overflow-y-auto space-y-4 mb-4 min-h-0">
        {#if testMessages.length === 0}
          <div class="flex items-center justify-center h-full text-light-tx-3 dark:text-dark-tx-3 text-sm">
            <p>Stellen Sie eine Testfrage an den Assistenten.</p>
          </div>
        {:else}
          {#each testMessages as message, i}
            <MessageBubble
              {message}
              isStreaming={testIsStreaming && i === testMessages.length - 1 && message.role === "assistant"}
            />
          {/each}
        {/if}
        {#if testError}
          <div class="flex justify-center">
            <span class="text-light-re dark:text-dark-re text-sm">{testError}</span>
          </div>
        {/if}
      </div>

      <!-- Eingabe -->
      <div class="border-t border-light-ui-3 dark:border-dark-ui-3 pt-3">
        <div class="flex gap-2">
          <textarea
            bind:this={testTextarea}
            bind:value={testInput}
            rows={testAreaRows}
            onkeydown={handleTestKeydown}
            oninput={adjustTestTextareaHeight}
            disabled={testIsStreaming}
            placeholder={testIsStreaming ? "..." : "Testfrage eingeben…"}
            class="flex-1 resize-none rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                   px-3 py-2 text-sm disabled:opacity-50"
          ></textarea>
          <button
            onclick={sendTestMessage}
            disabled={testIsStreaming || !testInput.trim()}
            class="p-2 bg-primary dark:bg-primary-dark text-white rounded-lg
                   hover:opacity-90 transition-opacity disabled:opacity-50
                   flex items-center justify-center min-w-[40px]"
          >
            {#if testIsStreaming}
              <Loader2 size={16} class="animate-spin" />
            {:else}
              <Send size={16} />
            {/if}
          </button>
        </div>
      </div>
    {/if}
  </aside>
</div>
