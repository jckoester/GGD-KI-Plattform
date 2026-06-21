<script>
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { ShieldCheck } from "lucide-svelte";
  import {
    getAccessRequests,
    approveAccessRequest,
    denyAccessRequest,
  } from "$lib/api.js";
  import ErrorBanner from "$lib/components/ErrorBanner.svelte";
  import StepUpDialog from "$lib/components/StepUpDialog.svelte";

  let items = $state([]);
  let approved = $state([]);
  let loading = $state(true);
  let error = $state(null);
  let processing = $state(null); // id, der gerade verarbeitet wird

  let pendingAction = $state(null); // { id, action } für Wiederholung nach Step-up
  let showStepUp = $state(false);

  const SEVERITY = {
    alert: { label: "Alarm", cls: "bg-light-re-2 dark:bg-dark-re-2 text-light-re dark:text-dark-re" },
    warning: { label: "Warnung", cls: "bg-light-or-2 dark:bg-dark-or-2 text-light-or dark:text-dark-or" },
    info: { label: "Hinweis", cls: "bg-light-bl-2 dark:bg-dark-bl-2 text-light-bl dark:text-dark-bl" },
  };
  const CATEGORY = {
    suizidalitaet: "Suizidalität",
    selbstverletzung: "Selbstverletzung",
    haeusliche_gewalt: "Häusliche Gewalt",
    essverhalten: "Essverhalten",
    mobbing: "Mobbing",
  };

  async function load() {
    loading = true;
    error = null;
    try {
      const [pend, appr] = await Promise.all([
        getAccessRequests("pending"),
        getAccessRequests("approved"),
      ]);
      items = pend.items;
      approved = appr.items;
    } catch (e) {
      error = e.message ?? "Anträge konnten nicht geladen werden.";
      items = [];
      approved = [];
    } finally {
      loading = false;
    }
  }

  async function doAction(id, action) {
    processing = id;
    error = null;
    try {
      if (action === "approve") {
        await approveAccessRequest(id);
        // Freigegeben → direkt in die Einsicht (Zweitperson ist Beteiligte).
        goto(`/access-requests/${id}`);
        return;
      }
      await denyAccessRequest(id);
      await load();
    } catch (e) {
      if (e.stepUpRequired) {
        pendingAction = { id, action };
        showStepUp = true;
      } else {
        error = e.message ?? "Aktion fehlgeschlagen.";
      }
    } finally {
      processing = null;
    }
  }

  function onStepUpSuccess() {
    showStepUp = false;
    const a = pendingAction;
    pendingAction = null;
    if (a) doAction(a.id, a.action);
  }

  function onStepUpCancel() {
    showStepUp = false;
    pendingAction = null;
  }

  function fmtDate(s) {
    return new Date(s).toLocaleString("de-DE");
  }

  onMount(load);
</script>

<div class="h-full overflow-y-auto">
  <div class="max-w-3xl mx-auto py-8 px-4">
    <div class="flex items-center gap-2 mb-2 text-light-tx dark:text-dark-tx">
      <ShieldCheck class="w-6 h-6" />
      <h1 class="text-2xl font-semibold">Krisen-Freigaben</h1>
    </div>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-6">
      Offene Anträge auf Einsicht in geflaggte Konversationen. Geben Sie nur frei, wenn
      die Einsicht fachlich begründet ist — Sie sind die <strong>zweite</strong> Person
      im Vier-Augen-Prinzip. Eigene Anträge können Sie nicht selbst freigeben.
    </p>

    {#if error}
      <ErrorBanner message={error} />
    {/if}

    {#if loading}
      <div class="text-center py-8 text-light-tx-2 dark:text-dark-tx-2">Laden...</div>
    {:else if items.length === 0}
      <div class="text-center py-12 text-light-tx-2 dark:text-dark-tx-2 text-sm">
        Derzeit keine offenen Anträge.
      </div>
    {:else}
      <div class="space-y-3">
        {#each items as req (req.id)}
          <div class="border border-light-ui-3 dark:border-dark-ui-3 rounded-lg p-4
                      bg-light-ui dark:bg-dark-ui">
            <div class="flex items-center gap-2 mb-2">
              <span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium
                           {SEVERITY[req.severity]?.cls ?? 'bg-light-ui-2 dark:bg-dark-ui-2'}">
                {SEVERITY[req.severity]?.label ?? req.severity}
              </span>
              <span class="font-medium text-light-tx dark:text-dark-tx">
                {CATEGORY[req.flag_category] ?? req.flag_category}
              </span>
            </div>
            <dl class="text-sm text-light-tx-2 dark:text-dark-tx-2 space-y-1 mb-3">
              <div class="flex gap-2">
                <dt class="w-32 shrink-0">Konversation</dt>
                <dd class="font-mono text-xs">{req.subject_pseudonym.slice(0, 12)}…</dd>
              </div>
              <div class="flex gap-2">
                <dt class="w-32 shrink-0">Beantragt von</dt>
                <dd class="font-mono text-xs">{req.requested_by.slice(0, 12)}…</dd>
              </div>
              <div class="flex gap-2">
                <dt class="w-32 shrink-0">Beantragt am</dt>
                <dd>{fmtDate(req.requested_at)}</dd>
              </div>
              <div class="flex gap-2">
                <dt class="w-32 shrink-0">Zeitfenster</dt>
                <dd>{req.access_window_hours} Stunden</dd>
              </div>
              {#if req.reason}
                <div class="flex gap-2">
                  <dt class="w-32 shrink-0">Zusatzkontext</dt>
                  <dd class="text-light-tx dark:text-dark-tx">{req.reason}</dd>
                </div>
              {/if}
            </dl>
            <div class="flex justify-end gap-3">
              <button
                onclick={() => doAction(req.id, "deny")}
                disabled={processing === req.id}
                class="px-4 py-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg text-sm
                       text-light-tx-2 dark:text-dark-tx-2
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Ablehnen
              </button>
              <button
                onclick={() => doAction(req.id, "approve")}
                disabled={processing === req.id}
                class="px-4 py-2 bg-primary dark:bg-primary-dark text-white rounded-lg text-sm
                       hover:bg-primary-dark dark:hover:bg-primary transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {processing === req.id ? "…" : "Freigeben"}
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}

    <!-- Freigegebene Anträge: Einsicht erneut öffnen (Beteiligte) -->
    {#if !loading && approved.length > 0}
      <div class="mt-10">
        <h2 class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-3">
          Freigegeben
        </h2>
        <div class="space-y-2">
          {#each approved as req (req.id)}
            <div class="flex items-center justify-between gap-4 border border-light-ui-3 dark:border-dark-ui-3
                        rounded-lg px-4 py-3 bg-light-ui dark:bg-dark-ui">
              <div class="text-sm text-light-tx dark:text-dark-tx">
                {CATEGORY[req.flag_category] ?? req.flag_category}
                <span class="text-light-tx-2 dark:text-dark-tx-2 font-mono text-xs ml-1">
                  {req.subject_pseudonym.slice(0, 10)}…
                </span>
              </div>
              <button
                onclick={() => goto(`/access-requests/${req.id}`)}
                class="shrink-0 px-3 py-1.5 text-sm rounded-lg bg-primary dark:bg-primary-dark text-white
                       hover:bg-primary-dark dark:hover:bg-primary transition-colors"
              >
                Öffnen
              </button>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </div>
</div>

{#if showStepUp}
  <StepUpDialog onSuccess={onStepUpSuccess} onCancel={onStepUpCancel} />
{/if}
