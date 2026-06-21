<script>
  // Wiederverwendbarer Re-Authentifizierungs-Dialog (Step-up, Phase 12, Schritt 5).
  // Wird vor sensiblen Aktionen (Krisen-Freigabe, Reader-View) geöffnet, wenn das
  // Backend 401 mit X-Stepup-Required liefert. Behandelt beide Adapter-Modi:
  //   direct  → Passwort-Re-Entry im Dialog
  //   redirect→ Weiterleitung zum SSO-Provider (prompt=login) und zurück
  import { onMount } from "svelte";
  import { ShieldCheck } from "lucide-svelte";
  import { getStepUpChallenge, stepUpDirect } from "$lib/api.js";

  let { onSuccess, onCancel } = $props();

  let mode = $state(null); // "direct" | "redirect"
  let redirectUrl = $state(null);
  let loading = $state(true);
  let error = $state(null);

  let username = $state("");
  let password = $state("");
  let submitting = $state(false);

  onMount(async () => {
    try {
      const returnTo = window.location.pathname + window.location.search;
      const data = await getStepUpChallenge(returnTo);
      mode = data.mode;
      redirectUrl = data.redirect_url ?? null;
    } catch (e) {
      error = e.message ?? "Re-Authentifizierung nicht verfügbar.";
    } finally {
      loading = false;
    }
  });

  function goRedirect() {
    if (redirectUrl) window.location.href = redirectUrl;
  }

  async function submitDirect() {
    if (submitting || !username || !password) return;
    submitting = true;
    error = null;
    try {
      await stepUpDirect(username, password);
      onSuccess?.();
    } catch (e) {
      error = e.message ?? "Re-Authentifizierung fehlgeschlagen.";
    } finally {
      submitting = false;
    }
  }
</script>

<div class="fixed inset-0 z-50 flex items-center justify-center p-4">
  <button
    class="absolute inset-0 bg-black/50"
    onclick={() => onCancel?.()}
    aria-label="Dialog schließen"
  ></button>
  <div
    class="relative bg-light-bg dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3
           rounded-lg shadow-lg w-full max-w-sm p-6"
  >
    <div class="flex items-center gap-2 mb-1 text-light-tx dark:text-dark-tx">
      <ShieldCheck class="w-5 h-5" />
      <h2 class="text-lg font-semibold">Erneute Anmeldung</h2>
    </div>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
      Diese Aktion ist besonders geschützt. Bitte bestätigen Sie kurz Ihre Identität.
    </p>

    {#if loading}
      <div class="text-center py-6 text-light-tx-2 dark:text-dark-tx-2">Lädt…</div>
    {:else if mode === "redirect"}
      {#if error}
        <p class="text-sm text-light-re dark:text-dark-re mb-3">{error}</p>
      {/if}
      <button
        onclick={goRedirect}
        class="w-full py-2.5 px-4 rounded-lg bg-primary dark:bg-primary-dark text-white
               font-medium hover:bg-primary-dark dark:hover:bg-primary transition-colors"
      >
        Erneut anmelden
      </button>
    {:else if mode === "direct"}
      <form
        onsubmit={(e) => {
          e.preventDefault();
          submitDirect();
        }}
        class="space-y-3"
      >
        <input
          type="text"
          bind:value={username}
          placeholder="Benutzername"
          autocomplete="username"
          class="w-full rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx px-3 py-2 text-sm"
        />
        <input
          type="password"
          bind:value={password}
          placeholder="Passwort"
          autocomplete="current-password"
          class="w-full rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx px-3 py-2 text-sm"
        />
        {#if error}
          <p class="text-sm text-light-re dark:text-dark-re">{error}</p>
        {/if}
        <div class="flex justify-end gap-3 pt-1">
          <button
            type="button"
            onclick={() => onCancel?.()}
            disabled={submitting}
            class="px-4 py-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                   text-light-tx-2 dark:text-dark-tx-2
                   hover:bg-light-ui dark:hover:bg-dark-ui transition-colors
                   disabled:opacity-50"
          >
            Abbrechen
          </button>
          <button
            type="submit"
            disabled={submitting || !username || !password}
            class="px-4 py-2 bg-primary dark:bg-primary-dark text-white rounded-lg
                   hover:bg-primary-dark dark:hover:bg-primary transition-colors
                   disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Bestätigen…" : "Bestätigen"}
          </button>
        </div>
      </form>
    {:else}
      <p class="text-sm text-light-re dark:text-dark-re">{error ?? "Nicht verfügbar."}</p>
    {/if}
  </div>
</div>
