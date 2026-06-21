<script>
  import { onMount } from "svelte";
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import { ArrowLeft, Download, CheckCircle } from "lucide-svelte";
  import {
    getReaderConversation,
    exportReaderConversation,
    resolveAccessRequest,
  } from "$lib/api.js";
  import { user } from "$lib/stores/user.js";
  import MessageBubble from "$lib/components/MessageBubble.svelte";
  import StepUpDialog from "$lib/components/StepUpDialog.svelte";
  import ErrorBanner from "$lib/components/ErrorBanner.svelte";
  import WarningBanner from "$lib/components/WarningBanner.svelte";

  const id = $page.params.id;

  let data = $state(null);
  let loading = $state(true);
  let error = $state(null);
  let exporting = $state(false);
  let showStepUp = $state(false);
  let pendingIntent = $state(null); // "view" | "export"

  let isAdmin = $derived($user?.roles?.includes("admin") ?? false);

  // Fall-Abschluss (nur Admin)
  let showResolve = $state(false);
  let resolveOutcome = $state("resolved");
  let resolveNote = $state("");
  let resolving = $state(false);
  let resolveError = $state(null);

  function openResolve() {
    resolveOutcome = "resolved";
    resolveNote = "";
    resolveError = null;
    showResolve = true;
  }

  async function doResolve() {
    if (resolving || !resolveNote.trim()) return;
    resolving = true;
    resolveError = null;
    try {
      await resolveAccessRequest(id, {
        outcome: resolveOutcome,
        note: resolveNote.trim(),
      });
      goto("/flags");
    } catch (e) {
      resolveError = e.message ?? "Abschluss fehlgeschlagen.";
    } finally {
      resolving = false;
    }
  }

  const SEVERITY = { alert: "Alarm", warning: "Warnung", info: "Hinweis" };
  const CATEGORY = {
    suizidalitaet: "Suizidalität",
    selbstverletzung: "Selbstverletzung",
    haeusliche_gewalt: "Häusliche Gewalt",
    essverhalten: "Essverhalten",
    mobbing: "Mobbing",
  };

  async function loadView() {
    loading = true;
    error = null;
    try {
      data = await getReaderConversation(id);
    } catch (e) {
      if (e.stepUpRequired) {
        pendingIntent = "view";
        showStepUp = true;
      } else {
        error = e.message ?? "Konversation konnte nicht geladen werden.";
      }
    } finally {
      loading = false;
    }
  }

  async function doExport() {
    exporting = true;
    error = null;
    try {
      const payload = await exportReaderConversation(id);
      downloadMarkdown(payload);
    } catch (e) {
      if (e.stepUpRequired) {
        pendingIntent = "export";
        showStepUp = true;
      } else {
        error = e.message ?? "Export fehlgeschlagen.";
      }
    } finally {
      exporting = false;
    }
  }

  function downloadMarkdown(payload) {
    const lines = [
      `# Einsicht — ${CATEGORY[payload.flag_category] ?? payload.flag_category}`,
      "",
      `Konversation: ${payload.subject_pseudonym}`,
      `Schweregrad: ${SEVERITY[payload.severity] ?? payload.severity}`,
      "",
      "---",
      "",
    ];
    for (const m of payload.messages) {
      const who = m.role === "user" ? "Schüler:in" : "Assistent";
      lines.push(`## ${who} — ${new Date(m.created_at).toLocaleString("de-DE")}`);
      lines.push("");
      lines.push(m.content);
      lines.push("");
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `einsicht-${id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function onStepUpSuccess() {
    showStepUp = false;
    const intent = pendingIntent;
    pendingIntent = null;
    if (intent === "view") loadView();
    else if (intent === "export") doExport();
  }

  function onStepUpCancel() {
    showStepUp = false;
    pendingIntent = null;
  }

  onMount(loadView);
</script>

<div class="h-full overflow-y-auto">
  <div class="max-w-3xl mx-auto py-8 px-4">
    <button
      onclick={() => history.back()}
      class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2
             hover:text-light-tx dark:hover:text-dark-tx transition-colors"
    >
      <ArrowLeft class="w-4 h-4" /> Zurück
    </button>

    {#if loading}
      <div class="text-center py-12 text-light-tx-2 dark:text-dark-tx-2">Laden...</div>
    {:else if error}
      <ErrorBanner message={error} />
    {:else if data}
      <div class="flex items-start justify-between gap-4 mb-2">
        <div>
          <h1 class="text-2xl font-semibold text-light-tx dark:text-dark-tx">
            {CATEGORY[data.flag_category] ?? data.flag_category}
          </h1>
          <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
            Konversation <span class="font-mono">{data.subject_pseudonym.slice(0, 12)}…</span>
            · Zugriff bis {new Date(data.access_granted_until).toLocaleString("de-DE")}
          </p>
        </div>
        <div class="shrink-0 flex items-center gap-2">
          <button
            onclick={doExport}
            disabled={exporting}
            class="flex items-center gap-2 px-3 py-2 border border-light-ui-3 dark:border-dark-ui-3
                   rounded-lg text-sm text-light-tx dark:text-dark-tx
                   hover:bg-light-ui dark:hover:bg-dark-ui transition-colors disabled:opacity-50"
          >
            <Download class="w-4 h-4" />
            {exporting ? "Export…" : "Export"}
          </button>
          {#if isAdmin}
            <button
              onclick={openResolve}
              class="flex items-center gap-2 px-3 py-2 bg-primary dark:bg-primary-dark text-white
                     rounded-lg text-sm hover:bg-primary-dark dark:hover:bg-primary transition-colors"
            >
              <CheckCircle class="w-4 h-4" />
              Fall abschließen
            </button>
          {/if}
        </div>
      </div>

      <div class="mb-4">
        <WarningBanner
          message="Nur-Lese-Einsicht im Vier-Augen-Prinzip. Jeder Zugriff und Export wird protokolliert. Behandeln Sie die Inhalte streng vertraulich."
        />
      </div>

      <div class="space-y-1">
        {#each data.messages as m, i (i)}
          <MessageBubble message={m} />
        {/each}
      </div>
    {/if}
  </div>
</div>

{#if showStepUp}
  <StepUpDialog onSuccess={onStepUpSuccess} onCancel={onStepUpCancel} />
{/if}

{#if showResolve}
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <button
      class="absolute inset-0 bg-black/50"
      onclick={() => (showResolve = false)}
      aria-label="Dialog schließen"
    ></button>
    <div
      class="relative bg-light-bg dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3
             rounded-lg shadow-lg w-full max-w-lg p-6"
    >
      <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-1">
        Fall abschließen
      </h2>
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
        Schließt die Meldung ab. Die Konversation wird danach noch 180 Tage aufbewahrt
        und anschließend dem normalen Löschzyklus überlassen.
      </p>

      <fieldset class="mb-4">
        <legend class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1">
          Ergebnis
        </legend>
        <label class="flex items-center gap-2 text-sm text-light-tx dark:text-dark-tx mb-1">
          <input type="radio" bind:group={resolveOutcome} value="resolved" />
          Erledigt — Anliegen wurde bearbeitet
        </label>
        <label class="flex items-center gap-2 text-sm text-light-tx dark:text-dark-tx">
          <input type="radio" bind:group={resolveOutcome} value="dismissed" />
          Verworfen — kein tatsächlicher Anlass (Fehlalarm)
        </label>
      </fieldset>

      <label
        for="resolve-note"
        class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
      >
        Abschlussvermerk
      </label>
      <textarea
        id="resolve-note"
        bind:value={resolveNote}
        rows="3"
        placeholder="Was wurde veranlasst? (Pflicht)"
        class="w-full p-3 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
               bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx text-sm
               focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark resize-y mb-4"
      ></textarea>

      {#if resolveError}
        <p class="text-sm text-light-re dark:text-dark-re mb-3">{resolveError}</p>
      {/if}

      <div class="flex justify-end gap-3">
        <button
          onclick={() => (showResolve = false)}
          disabled={resolving}
          class="px-4 py-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                 text-light-tx-2 dark:text-dark-tx-2
                 hover:bg-light-ui dark:hover:bg-dark-ui transition-colors disabled:opacity-50"
        >
          Abbrechen
        </button>
        <button
          onclick={doResolve}
          disabled={resolving || !resolveNote.trim()}
          class="px-4 py-2 bg-primary dark:bg-primary-dark text-white rounded-lg
                 hover:bg-primary-dark dark:hover:bg-primary transition-colors
                 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {resolving ? "Abschließen…" : "Abschließen"}
        </button>
      </div>
    </div>
  </div>
{/if}
