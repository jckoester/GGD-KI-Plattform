<script>
  /**
   * „Meine Bausteine" — der eigene Bestand, nach Fach gruppiert (AP7 Schritt 2).
   *
   * Die Seite beantwortet **nicht** „wo ist Baustein X" — dafür sind Sammlung,
   * Planner und Fachseite schneller, weil sie vorfiltern. Sie ist Rechenschaft
   * über den eigenen Bestand, Auffangbecken über alle Erzeugungswege und der
   * Ort, an dem der Lebenszyklus quer über die Fächer zusammenläuft
   * (Notiz-Knotentyp-UI A4).
   *
   * Entscheidbare Logik steht in `$lib/meine_bausteine.js` und ist dort geprüft;
   * hier bleibt Darstellung.
   */
  import { page } from '$app/stores'
  import { getMeineBausteine } from '$lib/api.js'
  import { user } from '$lib/stores/user.js'
  import { refreshAufmerksamkeit } from '$lib/stores/meineBausteine.js'
  import { CONTENT_TYPE_LABELS } from '$lib/taxonomy.js'
  import {
    ablaufAnzeige,
    abschnittsTitel,
    aufmerksamkeitsText,
    nachTypGefiltert,
    nurAufmerksamkeit,
    vorkommendeTypen,
  } from '$lib/meine_bausteine.js'
  import NodeTypeIcon from '$lib/components/NodeTypeIcon.svelte'
  import ErrorBanner from '$lib/components/ErrorBanner.svelte'
  import LoadingBanner from '$lib/components/LoadingBanner.svelte'
  import { AlertTriangle, Bot, ChevronDown, ChevronRight, Package } from 'lucide-svelte'
  import PageBody from '$lib/components/PageBody.svelte'

  let daten = $state(null)
  let laedt = $state(true)
  let fehler = $state(null)
  let typFilter = $state('')
  let nurWarnungen = $state(false)
  let zugeklappt = $state(new Set())

  const istLehrkraft = $derived(
    $user?.roles.includes('teacher') || $user?.roles.includes('admin'),
  )

  const warnung = $derived(aufmerksamkeitsText(daten?.aufmerksamkeit))

  // Der Warn-Filter ist die **Grundlage**, der Typ-Filter arbeitet darauf. Nur so
  // zeigen die Typ-Chips Zahlen, die zur Liste darunter passen — leiteten sie sich
  // aus dem Gesamtbestand ab, stünde dort „Arbeitsblatt (12)" über einer Liste mit
  // zwei Zeilen.
  const basis = $derived(nurWarnungen ? nurAufmerksamkeit(daten) : daten)
  const typen = $derived(
    vorkommendeTypen(basis, (t) => CONTENT_TYPE_LABELS[t] ?? t ?? 'Ohne Typ'),
  )
  const sichtbar = $derived(nachTypGefiltert(basis, typFilter))

  function warnFilterUmschalten() {
    nurWarnungen = !nurWarnungen
    // Der zuvor gewählte Typ kommt im neuen Bestand womöglich nicht vor — dann
    // stünde man ohne Zutun vor einer leeren Liste.
    typFilter = ''
  }

  $effect(() => {
    laden()
  })

  async function laden() {
    laedt = true
    fehler = null
    try {
      daten = await getMeineBausteine()
      // Der Sidebar-Zähler zeigt dieselbe Zahl — hier gleich mitziehen, damit er
      // nach dem Öffnen der Seite nicht veraltet danebensteht.
      refreshAufmerksamkeit()
    } catch (e) {
      fehler = e.message ?? 'Die eigenen Bausteine konnten nicht geladen werden.'
    } finally {
      laedt = false
    }
  }

  function klappen(schluessel) {
    const neu = new Set(zugeklappt)
    neu.has(schluessel) ? neu.delete(schluessel) : neu.add(schluessel)
    zugeklappt = neu
  }

  const schluessel = (abschnitt) => String(abschnitt.subject_id ?? 'ohne-fach')

  // Wohin die Detailansicht zurückführt. Konvention im Wissensgraphen: `?back=` mit
  // Pfad **und** Query — ohne ihn landet der Zurück-Weg auf `/knowledge`, das
  // Schüler:innen gar nicht offensteht.
  const rueckweg = $derived(
    encodeURIComponent($page.url.pathname + $page.url.search),
  )
</script>

<svelte:head><title>Meine Bausteine</title></svelte:head>

<PageBody>
  <h1 class="text-2xl font-semibold text-light-tx dark:text-dark-tx">Meine Bausteine</h1>

  <!-- Kopfzeile je Rolle. Für Schüler:innen in einfacher Sprache und mit der
       Zusicherung, dass niemand sonst mitliest (A4). -->
  <p class="mt-1 text-sm text-light-tx-2 dark:text-dark-tx-2">
    {#if istLehrkraft}
      Alles, was unter deinem Konto gespeichert ist — über alle Fächer und
      Entstehungswege hinweg.
    {:else}
      Das sind deine gespeicherten Bausteine. Nur du kannst sie sehen.
    {/if}
  </p>

  {#if laedt}
    <div class="mt-6"><LoadingBanner /></div>
  {:else if fehler}
    <div class="mt-6"><ErrorBanner message={fehler} /></div>
  {:else if !daten?.gesamt}
    <!-- Leerzustand erklärt den Entstehungsweg, statt nur „nichts da" zu sagen. -->
    <div class="mt-8 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-6 text-center">
      <Package class="w-8 h-8 mx-auto text-light-tx-3 dark:text-dark-tx-3" />
      <p class="mt-3 text-light-tx dark:text-dark-tx">Hier ist noch nichts.</p>
      <p class="mt-1 text-sm text-light-tx-2 dark:text-dark-tx-2">
        {#if istLehrkraft}
          Bausteine entstehen beim Anlegen im Wissensgraph, in einer Sammlung
          oder aus dem Unterrichtsplaner.
        {:else}
          Wenn du im Chat etwas erarbeitest, kannst du es dort als Baustein
          speichern — danach findest du es hier wieder.
        {/if}
      </p>
    </div>
  {:else}
    <!-- Warnbanner (A4): nur sichtbar, wenn etwas ansteht. Der Knopf **filtert die
         Liste**, statt einen zweiten Block aufzumachen — sonst stünde dasselbe
         zweimal auf der Seite. Die Zahl ist dieselbe wie am Sidebar-Zähler. -->
    {#if warnung}
      <div class="mt-5 rounded-lg border border-light-ye/40 dark:border-dark-ye/40
                  bg-light-ye/10 dark:bg-dark-ye/10 px-4 py-3
                  flex items-start gap-3 flex-wrap">
        <AlertTriangle class="w-5 h-5 text-light-ye dark:text-dark-ye flex-shrink-0 mt-0.5" />
        <p class="flex-1 min-w-0 text-sm text-light-tx dark:text-dark-tx">{warnung}</p>
        <button
          onclick={warnFilterUmschalten}
          class="text-sm px-3 py-1 rounded-lg border transition-colors
                 {nurWarnungen
                   ? 'bg-primary dark:bg-primary-dark text-white border-transparent'
                   : 'border-light-ye/50 dark:border-dark-ye/50 text-light-tx dark:text-dark-tx hover:bg-light-ye/20 dark:hover:bg-dark-ye/20'}"
        >
          {nurWarnungen ? 'Alle anzeigen' : 'Nur diese anzeigen'}
        </button>
      </div>
    {/if}

    {#if typen.length > 1}
      <div class="mt-5 flex flex-wrap gap-2">
        <button
          onclick={() => (typFilter = '')}
          class="px-3 py-1 text-sm rounded-full border transition-colors
                 {typFilter === ''
                   ? 'bg-primary dark:bg-primary-dark text-white border-transparent'
                   : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
        >
          Alle ({basis.gesamt})
        </button>
        {#each typen as t (t.typ)}
          <button
            onclick={() => (typFilter = typFilter === t.typ ? '' : t.typ)}
            class="px-3 py-1 text-sm rounded-full border transition-colors flex items-center gap-1.5
                   {typFilter === t.typ
                     ? 'bg-primary dark:bg-primary-dark text-white border-transparent'
                     : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
          >
            <NodeTypeIcon contentType={t.typ} size={14} />
            {t.label} ({t.anzahl})
          </button>
        {/each}
      </div>
    {/if}

    <div class="mt-5 space-y-4">
      {#each sichtbar.abschnitte as abschnitt (schluessel(abschnitt))}
        {@const zu = zugeklappt.has(schluessel(abschnitt))}
        <section class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3 overflow-hidden">
          <button
            onclick={() => klappen(schluessel(abschnitt))}
            class="w-full flex items-center gap-2 px-4 py-3 text-left
                   bg-light-bg-2 dark:bg-dark-bg-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
            aria-expanded={!zu}
          >
            {#if zu}
              <ChevronRight class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2" />
            {:else}
              <ChevronDown class="w-4 h-4 text-light-tx-2 dark:text-dark-tx-2" />
            {/if}
            <span class="font-medium text-light-tx dark:text-dark-tx">
              {abschnittsTitel(abschnitt)}
            </span>
            <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">({abschnitt.anzahl})</span>
          </button>

          {#if !zu}
            <ul class="divide-y divide-light-ui-2 dark:divide-dark-ui-2">
              {#each abschnitt.bausteine as b (b.id)}
                {@const ablauf = ablaufAnzeige(b.valid_until)}
                <li class="px-4 py-3 flex items-start gap-3">
                  <NodeTypeIcon contentType={b.content_type} size={18} />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2 flex-wrap">
                      <a
                        href="/knowledge/{b.id}?back={rueckweg}"
                        class="text-light-bl dark:text-dark-bl hover:underline truncate"
                      >{b.title}</a>

                      {#if b.status !== 'active'}
                        <span class="text-xs px-1.5 py-0.5 rounded
                                     bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx-2 dark:text-dark-tx-2">
                          {b.status === 'archived' ? 'archiviert' : b.status}
                        </span>
                      {/if}

                      {#if b.kategorien.includes('archivierte_referenzen')}
                        <span title="Verweist auf archivierte Bausteine"
                              class="text-light-ye dark:text-dark-ye">
                          <AlertTriangle class="w-4 h-4" />
                        </span>
                      {/if}

                      {#if b.kategorien.includes('unvollstaendig')}
                        <span class="text-xs px-1.5 py-0.5 rounded
                                     bg-light-ye/30 dark:bg-dark-ye/30 text-light-ye dark:text-dark-ye">
                          unvollständig
                        </span>
                      {/if}

                      {#if b.herkunft?.art === 'assistent'}
                        <span class="text-xs flex items-center gap-1 text-light-tx-3 dark:text-dark-tx-3"
                              title="Aus einem Assistenten-Kontext entstanden">
                          <Bot class="w-3 h-3" /> Assistent
                        </span>
                      {/if}
                    </div>

                    <div class="mt-0.5 text-xs text-light-tx-2 dark:text-dark-tx-2 flex gap-3 flex-wrap">
                      <span>{CONTENT_TYPE_LABELS[b.content_type] ?? b.content_type ?? 'Ohne Typ'}</span>
                      {#if ablauf.text}
                        <span class={ablauf.stufe === 'keine'
                                      ? ''
                                      : 'text-light-ye dark:text-dark-ye font-medium'}>
                          {ablauf.text}
                        </span>
                      {/if}
                    </div>
                  </div>
                </li>
              {/each}
            </ul>
          {/if}
        </section>
      {/each}
    </div>
  {/if}
</PageBody>
