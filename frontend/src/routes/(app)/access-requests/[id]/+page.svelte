<script>
  import { onMount } from "svelte";
  import { page } from "$app/stores";
  import { ArrowLeft, Download } from "lucide-svelte";
  import {
    getReaderConversation,
    exportReaderConversation,
  } from "$lib/api.js";
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
        <button
          onclick={doExport}
          disabled={exporting}
          class="shrink-0 flex items-center gap-2 px-3 py-2 border border-light-ui-3 dark:border-dark-ui-3
                 rounded-lg text-sm text-light-tx dark:text-dark-tx
                 hover:bg-light-ui dark:hover:bg-dark-ui transition-colors disabled:opacity-50"
        >
          <Download class="w-4 h-4" />
          {exporting ? "Export…" : "Export"}
        </button>
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
