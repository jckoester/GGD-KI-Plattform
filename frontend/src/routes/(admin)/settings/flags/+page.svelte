<script>
  import { onMount } from "svelte";
  import { TriangleAlert } from "lucide-svelte";
  import { getFlags } from "$lib/api.js";
  import ErrorBanner from "$lib/components/ErrorBanner.svelte";

  let items = $state([]);
  let total = $state(0);
  let loading = $state(true);
  let error = $state(null);

  let status = $state("");
  let severity = $state("");
  let offset = $state(0);
  const limit = 25;

  const SEVERITY = {
    alert: { label: "Alarm", cls: "bg-light-re-2 dark:bg-dark-re-2 text-light-re dark:text-dark-re" },
    warning: { label: "Warnung", cls: "bg-light-or-2 dark:bg-dark-or-2 text-light-or dark:text-dark-or" },
    info: { label: "Hinweis", cls: "bg-light-bl-2 dark:bg-dark-bl-2 text-light-bl dark:text-dark-bl" },
  };
  const STATUS = {
    open: "Offen",
    under_review: "In Prüfung",
    resolved: "Erledigt",
    dismissed: "Verworfen",
  };
  const CATEGORY = {
    suizidalitaet: "Suizidalität",
    selbstverletzung: "Selbstverletzung",
    haeusliche_gewalt: "Häusliche Gewalt",
    essverhalten: "Essverhalten",
    mobbing: "Mobbing",
  };
  const SOURCE = {
    auto_crisis: "Krise (automatisch)",
    auto_guardrail: "Guardrail",
    manual_admin: "Manuell",
  };

  let rangeFrom = $derived(total === 0 ? 0 : offset + 1);
  let rangeTo = $derived(Math.min(offset + limit, total));

  async function load() {
    loading = true;
    error = null;
    try {
      const data = await getFlags({
        status: status || null,
        severity: severity || null,
        limit,
        offset,
      });
      items = data.items;
      total = data.total;
    } catch (e) {
      error = e.message ?? "Meldungen konnten nicht geladen werden.";
      items = [];
      total = 0;
    } finally {
      loading = false;
    }
  }

  function applyFilters() {
    offset = 0;
    load();
  }

  function prevPage() {
    if (offset === 0) return;
    offset = Math.max(0, offset - limit);
    load();
  }

  function nextPage() {
    if (offset + limit >= total) return;
    offset += limit;
    load();
  }

  function fmtDate(s) {
    return new Date(s).toLocaleString("de-DE");
  }

  onMount(load);
</script>

<button
  onclick={() => history.back()}
  class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2
         hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
  ← Zurück
</button>

<div class="max-w-4xl mx-auto py-8">
  <div class="flex items-center gap-2 mb-2 text-light-tx dark:text-dark-tx">
    <TriangleAlert class="w-6 h-6" />
    <h1 class="text-2xl font-semibold">Krisen-Meldungen</h1>
  </div>

  <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-6">
    Automatisch erkannte Krisen-Hinweise auf Konversationen — <strong>pseudonymisiert</strong>
    und <strong>ohne Gesprächsinhalte</strong>. Die Inhalte werden erst nach einer
    Einsichtnahme im Vier-Augen-Prinzip sichtbar.
  </p>

  <!-- Filter -->
  <div class="flex flex-wrap gap-3 mb-4">
    <label class="text-sm text-light-tx-2 dark:text-dark-tx-2">
      Status
      <select
        bind:value={status}
        onchange={applyFilters}
        class="ml-1 px-2 py-1 rounded-md border border-light-ui-3 dark:border-dark-ui-3
               bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx text-sm"
      >
        <option value="">Alle</option>
        <option value="open">Offen</option>
        <option value="under_review">In Prüfung</option>
        <option value="resolved">Erledigt</option>
        <option value="dismissed">Verworfen</option>
      </select>
    </label>
    <label class="text-sm text-light-tx-2 dark:text-dark-tx-2">
      Schweregrad
      <select
        bind:value={severity}
        onchange={applyFilters}
        class="ml-1 px-2 py-1 rounded-md border border-light-ui-3 dark:border-dark-ui-3
               bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx text-sm"
      >
        <option value="">Alle</option>
        <option value="alert">Alarm</option>
        <option value="warning">Warnung</option>
        <option value="info">Hinweis</option>
      </select>
    </label>
  </div>

  {#if error}
    <ErrorBanner message={error} />
  {/if}

  {#if loading}
    <div class="text-center py-8 text-light-tx-2 dark:text-dark-tx-2">Laden...</div>
  {:else if items.length === 0}
    <div class="text-center py-12 text-light-tx-2 dark:text-dark-tx-2 text-sm">
      Keine Meldungen für die aktuelle Auswahl.
    </div>
  {:else}
    <div class="overflow-x-auto">
      <table class="w-full text-sm border-collapse">
        <thead>
          <tr class="border-b border-light-ui-3 dark:border-dark-ui-3
                     text-left text-light-tx-2 dark:text-dark-tx-2">
            <th class="pb-2 pr-4 font-medium">Schweregrad</th>
            <th class="pb-2 pr-4 font-medium">Kategorie</th>
            <th class="pb-2 pr-4 font-medium">Pseudonym</th>
            <th class="pb-2 pr-4 font-medium">Zeitpunkt</th>
            <th class="pb-2 pr-4 font-medium">Status</th>
            <th class="pb-2 font-medium">Antrag</th>
          </tr>
        </thead>
        <tbody>
          {#each items as f (f.id)}
            <tr class="border-b border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx dark:text-dark-tx">
              <td class="py-2 pr-4">
                <span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium
                             {SEVERITY[f.severity]?.cls ?? 'bg-light-ui-2 dark:bg-dark-ui-2'}">
                  {SEVERITY[f.severity]?.label ?? f.severity}
                </span>
              </td>
              <td class="py-2 pr-4">{CATEGORY[f.flag_category] ?? f.flag_category}</td>
              <td class="py-2 pr-4 font-mono text-xs text-light-tx-2 dark:text-dark-tx-2">
                {f.pseudonym.slice(0, 10)}…
              </td>
              <td class="py-2 pr-4 text-xs text-light-tx-2 dark:text-dark-tx-2">
                {fmtDate(f.flagged_at)}
              </td>
              <td class="py-2 pr-4 text-xs">{STATUS[f.status] ?? f.status}</td>
              <td class="py-2 text-xs">
                {#if f.has_active_request}
                  <span class="text-light-bl dark:text-dark-bl">läuft</span>
                {:else}
                  <span class="text-light-tx-2 dark:text-dark-tx-2">—</span>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="flex items-center justify-between mt-4 text-sm text-light-tx-2 dark:text-dark-tx-2">
      <span>{rangeFrom}–{rangeTo} von {total}</span>
      <div class="flex gap-2">
        <button
          onclick={prevPage}
          disabled={offset === 0}
          class="px-3 py-1 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                 hover:bg-light-ui dark:hover:bg-dark-ui transition-colors
                 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Zurück
        </button>
        <button
          onclick={nextPage}
          disabled={offset + limit >= total}
          class="px-3 py-1 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                 hover:bg-light-ui dark:hover:bg-dark-ui transition-colors
                 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Weiter
        </button>
      </div>
    </div>
  {/if}
</div>
