<script>
  /**
   * Der Beitrittscode einer Unterrichtsgruppe — Ausgabe, Erneuern, Rücknahme.
   *
   * ⚠️ **Keine Namen, keine Pseudonyme.** Die Lehrkraft sieht Zahlen und Tage. Das ist
   * keine Sparsamkeit, sondern die Folge der Pseudonymisierung: Eine Liste aus
   * Pseudonymen wäre nicht bedienbar, und wer ohne Namen die falsche Zeile trifft,
   * entfernt eine berechtigte Person und merkt es nicht. Zurückgenommen wird deshalb
   * eine **Menge** — die Code-Runde oder ein Tag daraus.
   */
  import { KeyRound, RefreshCw, Ban } from "lucide-svelte"
  import {
    getJoinCode,
    createJoinCode,
    revokeJoinCode,
    rollbackJoins,
  } from "$lib/api.js"
  import {
    beitritteAbsteigend,
    beitritteGesamt,
    codeHinweis,
    codeLage,
    ruecknahmeFrage,
  } from "$lib/beitrittscode.js"
  import ErrorBanner from "$lib/components/ErrorBanner.svelte"

  let { groupId } = $props()

  let antwort = $state(null)
  let laedt = $state(true)
  let arbeitet = $state(false)
  let fehler = $state(null)

  const lage = $derived(codeLage(antwort))
  const tage = $derived(beitritteAbsteigend(antwort))
  const gesamt = $derived(beitritteGesamt(antwort))

  $effect(() => {
    void groupId
    lesen()
  })

  async function lesen() {
    laedt = true
    try {
      antwort = await getJoinCode(groupId)
      fehler = null
    } catch (e) {
      fehler = e.message
    } finally {
      laedt = false
    }
  }

  async function fuehreAus(aktion) {
    arbeitet = true
    fehler = null
    try {
      await aktion()
      await lesen()
    } catch (e) {
      fehler = e.message
    } finally {
      arbeitet = false
    }
  }

  const erzeugen = () => fuehreAus(() => createJoinCode(groupId))
  const widerrufen = () => fuehreAus(() => revokeJoinCode(groupId))

  function zuruecknehmen(anzahl, tag = null) {
    // Bewusst eine harte Rückfrage: Hier werden Mitgliedschaften gelöscht, und der
    // Code wird dabei ungültig. Beides steht im Text, nicht nur die Zahl.
    if (!confirm(ruecknahmeFrage(anzahl, tag))) return
    fuehreAus(() => rollbackJoins(groupId, tag))
  }
</script>

<section class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-4">
  <h3 class="flex items-center gap-2 text-sm font-medium text-light-tx dark:text-dark-tx">
    <KeyRound size={16} class="text-light-tx-2 dark:text-dark-tx-2" />
    Beitrittscode
  </h3>

  {#if fehler}<div class="mt-2"><ErrorBanner message={fehler} /></div>{/if}

  {#if laedt}
    <p class="mt-2 text-sm text-light-tx-2 dark:text-dark-tx-2">Lädt …</p>
  {:else}
    {#if lage !== "keiner"}
      <p
        class="mt-2 font-mono text-2xl tracking-widest text-light-tx dark:text-dark-tx"
        class:opacity-50={lage === "abgelaufen"}
      >
        {antwort.code}
      </p>
    {/if}

    <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
      {codeHinweis(antwort)}
    </p>

    <div class="mt-3 flex flex-wrap gap-2">
      <button
        onclick={erzeugen}
        disabled={arbeitet}
        class="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium
               bg-primary dark:bg-primary-dark text-white disabled:opacity-50"
      >
        <RefreshCw size={13} />
        {lage === "keiner" ? "Code ausgeben" : "Erneuern"}
      </button>
      {#if lage === "gueltig"}
        <button
          onclick={widerrufen}
          disabled={arbeitet}
          class="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium
                 border border-light-ui-3 dark:border-dark-ui-3
                 text-light-tx dark:text-dark-tx disabled:opacity-50"
        >
          <Ban size={13} />
          Ungültig machen
        </button>
      {/if}
    </div>

    {#if gesamt > 0}
      <div class="mt-4 border-t border-light-ui-2 dark:border-dark-ui-2 pt-3">
        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
          {gesamt}
          {gesamt === 1 ? "Beitritt" : "Beitritte"} über diesen Code. Sind zu viele
          dabei, lassen sie sich tageweise zurücknehmen — Namen zeigt die Plattform nicht.
        </p>
        <ul class="mt-2 flex flex-col gap-1">
          {#each tage as t (t.tag)}
            <li class="flex items-center justify-between gap-3 text-xs">
              <span class="text-light-tx dark:text-dark-tx">
                {new Date(t.tag).toLocaleDateString("de-DE", {
                  day: "2-digit",
                  month: "2-digit",
                })}
                — {t.anzahl}
                {t.anzahl === 1 ? "Beitritt" : "Beitritte"}
              </span>
              <button
                onclick={() => zuruecknehmen(t.anzahl, t.tag)}
                disabled={arbeitet}
                class="underline text-light-tx-2 dark:text-dark-tx-2
                       hover:text-light-tx dark:hover:text-dark-tx disabled:opacity-50"
              >
                zurücknehmen
              </button>
            </li>
          {/each}
        </ul>
        {#if tage.length > 1}
          <button
            onclick={() => zuruecknehmen(gesamt)}
            disabled={arbeitet}
            class="mt-2 text-xs underline text-light-tx-2 dark:text-dark-tx-2
                   hover:text-light-tx dark:hover:text-dark-tx disabled:opacity-50"
          >
            Alle Beitritte dieses Codes zurücknehmen
          </button>
        {/if}
      </div>
    {/if}
  {/if}
</section>
