<script>
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { TriangleAlert } from "lucide-svelte";
  import { getFlags, createAccessRequest } from "$lib/api.js";
  import { refreshCrisisAlerts } from "$lib/stores/crisisAlerts.js";
  import ErrorBanner from "$lib/components/ErrorBanner.svelte";

  let items = $state([]);
  let total = $state(0);
  let loading = $state(true);
  let error = $state(null);

  let status = $state("");
  let severity = $state("");
  let offset = $state(0);
  const limit = 25;

  // Einsicht-Antrag-Dialog
  let requestFor = $state(null); // das Flag, für das ein Antrag gestellt wird
  let reason = $state("");
  let windowHours = $state(48);
  let submitting = $state(false);
  let submitError = $state(null);

  const CLOSED = new Set(["resolved", "dismissed"]);

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

  function openRequest(flag) {
    requestFor = flag;
    reason = "";
    windowHours = 48;
    submitError = null;
  }

  function closeRequest() {
    if (submitting) return;
    requestFor = null;
  }

  async function submitRequest() {
    if (submitting) return;
    submitting = true;
    submitError = null;
    try {
      await createAccessRequest(requestFor.id, {
        reason: reason.trim() || null,
        windowHours,
      });
      requestFor = null;
      await load();
      refreshCrisisAlerts();
    } catch (e) {
      submitError = e.message ?? "Antrag konnte nicht gestellt werden.";
    } finally {
      submitting = false;
    }
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
            <th class="pb-2 pr-4 font-medium">Antrag</th>
            <th class="pb-2 font-medium"></th>
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
              <td class="py-2 pr-4 text-xs">
                {#if f.active_request_status === "approved"}
                  <span class="text-light-gr dark:text-dark-gr">freigegeben</span>
                {:else if f.has_active_request}
                  <span class="text-light-bl dark:text-dark-bl">läuft</span>
                {:else}
                  <span class="text-light-tx-2 dark:text-dark-tx-2">—</span>
                {/if}
              </td>
              <td class="py-2 text-xs">
                {#if f.active_request_status === "approved"}
                  <button
                    onclick={() => goto(`/access-requests/${f.active_request_id}`)}
                    class="text-light-gr dark:text-dark-gr hover:underline"
                  >
                    Einsehen
                  </button>
                {:else if f.has_active_request || CLOSED.has(f.status)}
                  <span class="text-light-tx-2 dark:text-dark-tx-2">—</span>
                {:else}
                  <button
                    onclick={() => openRequest(f)}
                    class="text-light-bl dark:text-dark-bl hover:underline"
                  >
                    Einsicht beantragen
                  </button>
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

<!-- Einsicht-Antrag-Dialog -->
{#if requestFor}
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4">
    <button
      class="absolute inset-0 bg-black/50"
      onclick={closeRequest}
      aria-label="Dialog schließen"
    ></button>
    <div
      class="relative bg-light-bg dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3
             rounded-lg shadow-lg w-full max-w-lg p-6"
    >
      <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-1">
        Einsicht beantragen
      </h2>
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
        Anlass ist die Meldung
        <strong>{CATEGORY[requestFor.flag_category] ?? requestFor.flag_category}</strong>
        ({SEVERITY[requestFor.severity]?.label ?? requestFor.severity}) vom
        {fmtDate(requestFor.flagged_at)}. Die Einsicht wird erst nach Freigabe durch
        eine zweite Person (Vier-Augen-Prinzip) und nur innerhalb des Zeitfensters
        möglich; jeder Zugriff wird protokolliert.
      </p>

      <label
        for="access-reason"
        class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
      >
        Zusätzlicher Kontext <span class="font-normal text-light-tx-2 dark:text-dark-tx-2">(optional)</span>
      </label>
      <textarea
        id="access-reason"
        bind:value={reason}
        rows="3"
        placeholder="Nur ausfüllen, wenn weitere Hinweise vorliegen (z. B. Meldung einer Lehrkraft, wiederholtes Muster)."
        class="w-full p-3 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
               bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx text-sm
               focus:outline-none focus:ring-2 focus:ring-primary dark:focus:ring-primary-dark resize-y mb-4"
      ></textarea>

      <label
        for="access-window"
        class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
      >
        Zeitfenster
      </label>
      <select
        id="access-window"
        bind:value={windowHours}
        class="mb-5 px-2 py-1 rounded-md border border-light-ui-3 dark:border-dark-ui-3
               bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx text-sm"
      >
        <option value={24}>24 Stunden</option>
        <option value={48}>48 Stunden</option>
        <option value={72}>72 Stunden</option>
        <option value={168}>1 Woche</option>
      </select>

      {#if submitError}
        <p class="text-sm text-light-re dark:text-dark-re mb-3">{submitError}</p>
      {/if}

      <div class="flex justify-end gap-3">
        <button
          onclick={closeRequest}
          disabled={submitting}
          class="px-4 py-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                 text-light-tx-2 dark:text-dark-tx-2
                 hover:bg-light-ui dark:hover:bg-dark-ui transition-colors
                 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Abbrechen
        </button>
        <button
          onclick={submitRequest}
          disabled={submitting}
          class="px-4 py-2 bg-primary dark:bg-primary-dark text-white rounded-lg
                 hover:bg-primary-dark dark:hover:bg-primary transition-colors
                 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? "Wird gestellt..." : "Antrag stellen"}
        </button>
      </div>
    </div>
  </div>
{/if}
