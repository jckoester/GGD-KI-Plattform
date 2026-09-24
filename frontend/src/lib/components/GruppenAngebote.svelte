<script>
  /**
   * Neue Unterrichtsgruppen aus dem Schulkonto — zuordnen, anlegen oder ignorieren.
   *
   * ⚠️ **Es entsteht nichts von selbst.** Ob `unterricht.9d.ch` die vorhandene Gruppe
   * *Chemie 9D* meint oder eine neue ist, steht in keinem Datum, das die Plattform hat.
   * Eine falsche Verschmelzung schiebt zwei Jahrespläne ineinander und ist aus
   * Nutzersicht nicht rückgängig zu machen — deshalb entscheidet die Lehrkraft.
   */
  import { Link2, Plus, EyeOff, Eye } from "lucide-svelte"
  import {
    getGroupOffers,
    assignGroupOffer,
    createGroupFromOffer,
    ignoreGroupOffer,
  } from "$lib/api.js"
  import {
    anlegenGesperrt,
    angebotsHinweis,
    hatKandidaten,
    kandidatZeile,
    zuordnenErgebnis,
    zuordnenFrage,
  } from "$lib/gruppenangebote.js"
  import { refreshMyGroups } from "$lib/stores/myGroups.js"
  import ErrorBanner from "$lib/components/ErrorBanner.svelte"
  import SuccessBanner from "$lib/components/SuccessBanner.svelte"

  let daten = $state(null)
  let zeigeIgnorierte = $state(false)
  let arbeitet = $state(null)
  let fehler = $state(null)
  let erfolg = $state(null)
  let wahl = $state({})

  const hinweis = $derived(angebotsHinweis(daten))
  const sichtbar = $derived(
    (daten?.angebote ?? []).filter((a) => zeigeIgnorierte || !a.ignoriert),
  )

  $effect(() => {
    void zeigeIgnorierte
    lesen()
  })

  async function lesen() {
    try {
      daten = await getGroupOffers(zeigeIgnorierte)
      fehler = null
    } catch (e) {
      fehler = e.message
    }
  }

  async function fuehreAus(id, aktion) {
    arbeitet = id
    fehler = null
    try {
      await aktion()
      await lesen()
      await refreshMyGroups()
    } catch (e) {
      fehler = e.message
    } finally {
      arbeitet = null
    }
  }

  function zuordnen(angebot) {
    const gruppe = (daten?.gruppen ?? []).find((g) => g.id === Number(wahl[angebot.id]))
    if (!gruppe) return
    // Harte Rückfrage: Hier werden zwei Gruppen zusammengeführt und geerbte
    // Mitgliedschaften entfernt. Beides steht im Text, nicht nur der Name.
    if (!confirm(zuordnenFrage(angebot, gruppe))) return
    fuehreAus(angebot.id, async () => {
      const antwort = await assignGroupOffer(angebot.id, gruppe.id)
      erfolg = zuordnenErgebnis(antwort)
    })
  }

  const anlegen = (a) =>
    fuehreAus(a.id, async () => {
      await createGroupFromOffer(a.id)
      erfolg = "Die Gruppe wurde angelegt."
    })

  const umschalten = (a) =>
    fuehreAus(a.id, () => ignoreGroupOffer(a.id, !a.ignoriert))
</script>

{#if sichtbar.length || (daten?.angebote ?? []).length}
  <section class="mb-8">
    <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-1">
      Neu aus dem Schulkonto
    </h2>
    {#if hinweis}
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-3">{hinweis}</p>
    {/if}

    {#if fehler}<ErrorBanner message={fehler} />{/if}
    {#if erfolg}<div class="mb-3"><SuccessBanner message={erfolg} /></div>{/if}

    <ul class="flex flex-col gap-2">
      {#each sichtbar as a (a.id)}
        {@const gesperrt = anlegenGesperrt(a)}
        <li
          class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-3"
          class:opacity-60={a.ignoriert}
        >
          <p class="text-sm font-medium text-light-tx dark:text-dark-tx">
            {a.name}
            {#if a.fach}
              <span class="font-normal text-light-tx-2 dark:text-dark-tx-2">· {a.fach}</span>
            {/if}
          </p>
          <p class="font-mono text-xs text-light-tx-2 dark:text-dark-tx-2">
            {a.sso_group_id}
          </p>

          {#if gesperrt}
            <p class="mt-1 text-xs text-light-tx-2 dark:text-dark-tx-2">{gesperrt}</p>
          {/if}

          {#if !a.ignoriert}
            <div class="mt-2 flex flex-wrap items-center gap-2">
              {#if hatKandidaten(daten)}
                <select
                  bind:value={wahl[a.id]}
                  class="rounded border border-light-ui-3 dark:border-dark-ui-3
                         bg-light-bg dark:bg-dark-bg px-2 py-1 text-sm
                         text-light-tx dark:text-dark-tx max-w-xs"
                >
                  <option value={undefined}>Gehört zu … (Gruppe wählen)</option>
                  {#each daten.gruppen as g (g.id)}
                    <option value={g.id}>{kandidatZeile(g)}</option>
                  {/each}
                </select>
                <button
                  onclick={() => zuordnen(a)}
                  disabled={arbeitet === a.id || !wahl[a.id]}
                  class="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium
                         bg-primary dark:bg-primary-dark text-white disabled:opacity-50"
                >
                  <Link2 size={13} /> Zuordnen
                </button>
              {/if}
              {#if !gesperrt}
                <button
                  onclick={() => anlegen(a)}
                  disabled={arbeitet === a.id}
                  class="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium
                         border border-light-ui-3 dark:border-dark-ui-3
                         text-light-tx dark:text-dark-tx disabled:opacity-50"
                >
                  <Plus size={13} /> Als neue Gruppe anlegen
                </button>
              {/if}
              <button
                onclick={() => umschalten(a)}
                disabled={arbeitet === a.id}
                class="flex items-center gap-1.5 text-xs underline
                       text-light-tx-2 dark:text-dark-tx-2 disabled:opacity-50"
              >
                <EyeOff size={13} /> Ignorieren
              </button>
            </div>
          {:else}
            <button
              onclick={() => umschalten(a)}
              disabled={arbeitet === a.id}
              class="mt-2 flex items-center gap-1.5 text-xs underline
                     text-light-tx-2 dark:text-dark-tx-2 disabled:opacity-50"
            >
              <Eye size={13} /> Wieder anzeigen
            </button>
          {/if}
        </li>
      {/each}
    </ul>

    <button
      onclick={() => (zeigeIgnorierte = !zeigeIgnorierte)}
      class="mt-2 text-xs underline text-light-tx-2 dark:text-dark-tx-2"
    >
      {zeigeIgnorierte ? "Ignorierte ausblenden" : "Ignorierte anzeigen"}
    </button>
  </section>
{/if}
