<script>
  // Hinweis nach einer gescheiterten erneuten Anmeldung (Step-up, 0.18.1).
  //
  // Das Backend springt mit `?stepup_fehler=<grund>` auf die Ausgangsseite zurück. Einmal im
  // Layout, weil die Anmeldung von mehreren Seiten ausgeht (Zugangstoken, Krisen-Einsicht).
  // Der Code wird beim Erzeugen gelesen — so sehen ihn auch Komponenten der Seite, die ihn
  // selbst auswerten — und erst danach aus der Adresse entfernt, damit ein Neuladen ihn
  // nicht wieder zeigt.
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import ErrorBanner from "$lib/components/ErrorBanner.svelte";
  import { ohneStepupFehler, stepupFehlerAusUrl, stepupFehlerText } from "$lib/stepup_rueckkehr.js";

  let text = $state(stepupFehlerText(stepupFehlerAusUrl(window.location.search)));

  onMount(() => {
    if (!text) return;
    goto(ohneStepupFehler(window.location.pathname, window.location.search), {
      replaceState: true,
      noScroll: true,
      keepFocus: true,
    });
  });
</script>

{#if text}
  <div class="px-4 pt-3 bg-light-bg-2 dark:bg-dark-bg-2 flex items-start gap-2">
    <div class="flex-1"><ErrorBanner message={text} /></div>
    <button
      class="text-sm text-light-tx-2 dark:text-dark-tx-2 px-2 py-1"
      onclick={() => (text = null)}
      aria-label="Hinweis schließen">✕</button
    >
  </div>
{/if}
