<script>
  /**
   * Handabgleich mit dem Stundenplan (UP-8, Schritt 10b).
   *
   * Warum es diesen Knopf gibt: Vertretungen werden an der Schule erst wenige Minuten vor
   * Unterrichtsbeginn eingetragen, weitere im Lauf des Vormittags. Der nächtliche Cron
   * sieht sie erst am Folgetag — bei Ausfall verkraftbar, bei Verlegungen nicht.
   *
   * Eine Komponente für beide Orte (Jahresplan und Profil), damit Aussehen und Verhalten
   * nicht auseinanderlaufen. `kompakt` schaltet auf die schmale Fassung für die
   * Werkzeugleiste des Jahresplans.
   */
  import { RefreshCw } from "lucide-svelte";
  import { getSyncStatus, runTimetableSync } from "$lib/api.js";
  import { onMount } from "svelte";
  import ErrorBanner from "./ErrorBanner.svelte";
  import SuccessBanner from "./SuccessBanner.svelte";
  import WarningBanner from "./WarningBanner.svelte";

  let { kompakt = false, onFertig = null } = $props();

  let status = $state({ configured: false, kuerzel: null, letzter_lauf: null });
  let laeuft = $state(false);
  let fehler = $state("");
  let ergebnis = $state(null);

  onMount(async () => {
    status = await getSyncStatus();
  });

  async function abgleichen() {
    laeuft = true;
    fehler = "";
    ergebnis = null;
    try {
      ergebnis = await runTimetableSync(1);
      status = await getSyncStatus();
      // Der Jahresplan muss sich neu laden — die Slot-Kategorien können sich geändert
      // haben, und eine Anzeige, die den alten Stand zeigt, ist schlimmer als keine.
      onFertig?.(ergebnis);
    } catch (err) {
      fehler = err.message;
    } finally {
      laeuft = false;
    }
  }

  function zeitpunkt(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    const minuten = Math.round((Date.now() - d.getTime()) / 60000);
    if (minuten < 1) return "gerade eben";
    if (minuten < 60) return `vor ${minuten} min`;
    if (minuten < 24 * 60) return `vor ${Math.round(minuten / 60)} h`;
    return d.toLocaleDateString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  const letzter = $derived(status?.letzter_lauf ?? null);
  const zuletzt = $derived(zeitpunkt(letzter?.last_sync_at));

  // Fehlerzustände des letzten Laufs — der Cron scheitert unbemerkt, wenn ihn niemand
  // anzeigt. `ok` und `kein_kuerzel` sind keine Störung.
  const STATUSTEXT = {
    nicht_erreichbar: "Der Stundenplan war beim letzten Lauf nicht erreichbar.",
    anmeldung_fehlgeschlagen: "Die Anmeldung am Stundenplan ist fehlgeschlagen.",
    fehler: "Der letzte Abgleich ist fehlgeschlagen.",
  };
  const stoerung = $derived(STATUSTEXT[letzter?.status] ?? null);

  function zusammenfassung(r) {
    const teile = [];
    teile.push(r.geaendert === 1 ? "1 Stunde geändert" : `${r.geaendert} Stunden geändert`);
    if (r.verlegungen?.length) teile.push(`${r.verlegungen.length} Verlegung(en)`);
    if (r.konflikte?.length) teile.push(`${r.konflikte.length} Hinweis(e)`);
    return teile.join(" · ");
  }
</script>

{#if status.configured && status.kuerzel}
  {#if kompakt}
    <button
      onclick={abgleichen}
      disabled={laeuft}
      title={zuletzt ? `Zuletzt abgeglichen: ${zuletzt}` : "Noch nicht abgeglichen"}
      class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border
             border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2
             hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors
             disabled:opacity-50"
    >
      <RefreshCw class="w-3.5 h-3.5 {laeuft ? 'animate-spin' : ''}" />
      Stundenplan
    </button>
  {:else}
    <div class="flex flex-wrap items-center gap-3">
      <button
        onclick={abgleichen}
        disabled={laeuft}
        class="inline-flex items-center gap-2 px-4 py-2 rounded-lg
               bg-primary dark:bg-primary-dark text-white disabled:opacity-50"
      >
        <RefreshCw class="w-4 h-4 {laeuft ? 'animate-spin' : ''}" />
        Jetzt abgleichen
      </button>
      <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        {#if zuletzt}
          Zuletzt abgeglichen {zuletzt}{#if letzter?.changed}, {letzter.changed} Stunden
            geändert{/if}.
        {:else}
          Noch nicht abgeglichen.
        {/if}
      </span>
    </div>
  {/if}

  {#if fehler}
    <div class="mt-3"><ErrorBanner message={fehler} /></div>
  {:else if stoerung && !ergebnis}
    <div class="mt-3"><WarningBanner message={stoerung} /></div>
  {:else if ergebnis}
    <div class="mt-3"><SuccessBanner message={zusammenfassung(ergebnis)} /></div>
  {/if}
{/if}
