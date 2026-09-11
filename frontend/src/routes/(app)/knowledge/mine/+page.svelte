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
  import {
    deleteContextNode,
    getMeineBausteine,
    reactivateContextNode,
    verwalteBaustein,
  } from '$lib/api.js'
  import { user } from '$lib/stores/user.js'
  import { refreshAufmerksamkeit } from '$lib/stores/meineBausteine.js'
  import { CONTENT_TYPE_LABELS } from '$lib/taxonomy.js'
  import {
    ablaufAnzeige,
    abschnittsTitel,
    aktionenFuer,
    loeschHindernis,
    CHIPS_JE_ZEILE,
    ORTE_ALS_CHIPS,
    gekappt,
    nachEinsatzortGefiltert,
    vorkommendeEinsatzorte,
    aufmerksamkeitsText,
    nachTypGefiltert,
    nurAufmerksamkeit,
    vorkommendeTypen,
  } from '$lib/meine_bausteine.js'
  import NodeTypeIcon from '$lib/components/NodeTypeIcon.svelte'
  import ErrorBanner from '$lib/components/ErrorBanner.svelte'
  import LoadingBanner from '$lib/components/LoadingBanner.svelte'
  import {
    AlertTriangle,
    Archive,
    Bot,
    CalendarClock,
    Check,
    ChevronDown,
    ChevronRight,
    MapPin,
    Package,
    Pencil,
    RotateCcw,
    Trash2,
    X,
  } from 'lucide-svelte'
  import PageBody from '$lib/components/PageBody.svelte'

  let daten = $state(null)
  let laedt = $state(true)
  let fehler = $state(null)
  let typFilter = $state('')
  let ortFilter = $state('')
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
  const einsatzorte = $derived(vorkommendeEinsatzorte(basis))
  const orteLeiste = $derived(gekappt(einsatzorte, ORTE_ALS_CHIPS))
  const sichtbar = $derived(
    nachEinsatzortGefiltert(nachTypGefiltert(basis, typFilter), ortFilter),
  )

  function warnFilterUmschalten() {
    nurWarnungen = !nurWarnungen
    ortFilter = ''
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

  // ── Aktionen je Zeile (A4/A6) ───────────────────────────────────────────
  //
  // Alle laufen über `PATCH …/verwalten` — den schmalen Vertrag aus Titel, Status
  // und Ablaufdatum. Der generische Editor bleibt außen vor: „Verwalten ist nicht
  // Bearbeiten" (Leitprinzip 5).

  let umbenennt = $state(null)      // id des Bausteins, dessen Titel gerade editiert wird
  let entwurf = $state('')
  let ablaufOffen = $state(null)    // id, an der das Datumsfeld aufgeklappt ist
  let ablaufEntwurf = $state('')
  let loeschKandidat = $state(null) // {baustein, hindernis|null}
  let rueckgaengig = $state(null)   // {text, tun} — der Undo-Streifen
  let aktionsFehler = $state(null)
  let laeuft = $state(false)

  let undoTimer
  function undoAnbieten(text, tun) {
    // Zeitlich begrenzt: Ein Streifen, der stehen bleibt, wird zur Tapete. Zehn
    // Sekunden reichen für „huch" und verschwinden vor der nächsten Handlung.
    clearTimeout(undoTimer)
    rueckgaengig = { text, tun }
    undoTimer = setTimeout(() => (rueckgaengig = null), 10000)
  }

  async function mitFehlerfang(fn) {
    aktionsFehler = null
    laeuft = true
    try {
      await fn()
      await laden()
    } catch (e) {
      aktionsFehler = e.message ?? 'Die Aktion ist fehlgeschlagen.'
    } finally {
      laeuft = false
    }
  }

  function umbenennenStarten(b) {
    umbenennt = b.id
    entwurf = b.title
  }

  async function umbenennenSpeichern(b) {
    const titel = entwurf.trim()
    umbenennt = null
    if (!titel || titel === b.title) return
    await mitFehlerfang(() => verwalteBaustein(b.id, { title: titel }))
  }

  async function archivieren(b) {
    await mitFehlerfang(async () => {
      await verwalteBaustein(b.id, { status: 'archived' })
      // Rückgängig heißt: Zustand von davor. **Nicht** „Reaktivieren" — das setzte
      // ein neues Ablaufdatum und wäre keine Rücknahme, sondern eine zweite Änderung.
      undoAnbieten(`„${b.title}" archiviert`, () =>
        mitFehlerfang(() => verwalteBaustein(b.id, { status: 'active' })),
      )
    })
  }

  async function reaktivieren(b) {
    // Eigener Weg: Ein wegen Ablauf archivierter Baustein trüge sonst weiter sein
    // altes Datum und wäre in derselben Nacht wieder weg.
    await mitFehlerfang(() => reactivateContextNode(b.id))
  }

  function ablaufOeffnen(b) {
    ablaufOffen = b.id
    ablaufEntwurf = b.valid_until ?? ''
  }

  async function ablaufSpeichern(b) {
    const wert = ablaufEntwurf || null
    ablaufOffen = null
    await mitFehlerfang(() =>
      verwalteBaustein(b.id, { valid_until: wert, valid_until_gesetzt: true }),
    )
  }

  async function loeschenBestaetigen() {
    const b = loeschKandidat.baustein
    aktionsFehler = null
    laeuft = true
    try {
      await deleteContextNode(b.id)
      loeschKandidat = null
      await laden()
    } catch (e) {
      // 409 heißt: fremde Bausteine verweisen darauf (F7). Der Dialog bleibt offen
      // und zeigt sie — Archivieren ist dann die richtige Handlung, nicht Löschen.
      loeschKandidat = { baustein: b, hindernis: loeschHindernis(e) }
    } finally {
      laeuft = false
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

  {#if aktionsFehler}
    <div class="mt-4"><ErrorBanner message={aktionsFehler} /></div>
  {/if}

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

    {#if istLehrkraft && einsatzorte.length}
      <!-- Zweiter Filter: „was steckt in dieser Einheit/Stunde?". Nur für
           Lehrkräfte — bei Schüler:innen gibt es keine Unterrichtsplanung, die
           etwas einsetzt, die Leiste bliebe leer. -->
      <div class="mt-3 flex flex-wrap gap-2 items-center">
        <span class="text-xs text-light-tx-3 dark:text-dark-tx-3">Eingesetzt in:</span>
        {#each orteLeiste.sichtbar as o (o.id)}
          <button
            onclick={() => (ortFilter = ortFilter === o.id ? '' : o.id)}
            class="px-2.5 py-1 text-xs rounded-full border transition-colors flex items-center gap-1
                   {ortFilter === o.id
                     ? 'bg-primary dark:bg-primary-dark text-white border-transparent'
                     : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
          >
            <MapPin class="w-3 h-3" />
            {o.titel} ({o.anzahl})
          </button>
        {/each}
        {#if orteLeiste.weitere}
          <!-- Der Rest als Auswahlfeld statt weiterer Chips: Nach einem Schuljahr
               sind es hunderte Stunden, und eine Wand aus Chips filtert nichts,
               sie verdeckt. Gekürzt wird trotzdem nicht stumm — die Zahl steht
               dran (Leitprinzip 3). -->
          <select
            value={orteLeiste.rest.some((o) => o.id === ortFilter) ? ortFilter : ''}
            onchange={(e) => (ortFilter = e.currentTarget.value)}
            aria-label="Weitere Einsatzorte"
            class="px-2 py-1 text-xs rounded-full border
                   border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx-2 dark:text-dark-tx-2"
          >
            <option value="">+{orteLeiste.weitere} weitere …</option>
            {#each orteLeiste.rest as o (o.id)}
              <option value={o.id}>{o.titel} ({o.anzahl})</option>
            {/each}
          </select>
        {/if}
        {#if ortFilter}
          <button onclick={() => (ortFilter = '')}
                  class="text-xs text-light-tx-3 dark:text-dark-tx-3 hover:underline">
            Filter aufheben
          </button>
        {/if}
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
                {@const kann = aktionenFuer(b)}
                {@const orte = gekappt(b.eingesetzt_in, CHIPS_JE_ZEILE)}
                <li class="px-4 py-3 flex items-start gap-3">
                  <NodeTypeIcon contentType={b.content_type} size={18} />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2 flex-wrap">
                      {#if umbenennt === b.id}
                        <!-- Inline umbenennen: kein Dialog für eine Zeile Text.
                             Enter speichert, Escape verwirft, Verlassen speichert
                             ebenfalls — sonst verliert man die Eingabe durch einen
                             Klick daneben. -->
                        <!-- svelte-ignore a11y_autofocus -->
                        <input
                          bind:value={entwurf}
                          autofocus
                          onkeydown={(e) => {
                            if (e.key === 'Enter') umbenennenSpeichern(b)
                            if (e.key === 'Escape') umbenennt = null
                          }}
                          onblur={() => umbenennenSpeichern(b)}
                          aria-label="Neuer Titel"
                          class="flex-1 min-w-0 px-2 py-0.5 text-sm rounded border
                                 border-light-ui-3 dark:border-dark-ui-3
                                 bg-light-bg dark:bg-dark-bg
                                 text-light-tx dark:text-dark-tx"
                        />
                      {:else}
                        <a
                          href="/knowledge/{b.id}?back={rueckweg}"
                          class="text-light-bl dark:text-dark-bl hover:underline truncate"
                        >{b.title}</a>
                      {/if}

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
                      {#each orte.sichtbar as o (o.id)}
                        <!-- Wo der Baustein im Unterricht steckt. Klick filtert die
                             Liste darauf. Ein Baustein ohne Chip ist der natürliche
                             Archiv-Kandidat (A4) — deshalb steht hier nichts statt
                             eines „nirgends". -->
                        <button
                          onclick={() => (ortFilter = ortFilter === o.id ? '' : o.id)}
                          class="flex items-center gap-1 hover:text-light-bl dark:hover:text-dark-bl"
                          title="Nur Bausteine aus {o.titel} zeigen"
                        >
                          <MapPin class="w-3 h-3" />{o.titel}
                        </button>
                      {/each}
                      {#if orte.weitere}
                        <span title={orte.rest.map((o) => o.titel).join(', ')}
                              class="text-light-tx-3 dark:text-dark-tx-3">
                          +{orte.weitere}
                        </span>
                      {/if}
                    </div>

                    {#if ablaufOffen === b.id}
                      <!-- Ablauf verlängern: die Lücke aus A4. Dort steht nur das neue
                           Datum beim *Reaktivieren* — für einen noch aktiven Baustein
                           („läuft in 3 Tagen ab") gab es keinen Weg außer dem
                           allgemeinen Editor, der bei einer Stunde die Phasen als
                           JSON zeigt. Leeres Feld heißt „gilt dauerhaft". -->
                      <div class="mt-2 flex items-center gap-2 flex-wrap">
                        <input
                          type="date"
                          bind:value={ablaufEntwurf}
                          aria-label="Neues Ablaufdatum"
                          class="px-2 py-1 text-xs rounded border
                                 border-light-ui-3 dark:border-dark-ui-3
                                 bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                        />
                        <button onclick={() => ablaufSpeichern(b)} disabled={laeuft}
                                class="text-xs px-2 py-1 rounded
                                       bg-primary dark:bg-primary-dark text-white
                                       disabled:opacity-40">
                          Übernehmen
                        </button>
                        <button onclick={() => (ablaufOffen = null)}
                                class="text-xs px-2 py-1 rounded
                                       text-light-tx-2 dark:text-dark-tx-2
                                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2">
                          Abbrechen
                        </button>
                        {#if ablaufEntwurf}
                          <button onclick={() => (ablaufEntwurf = '')}
                                  class="text-xs text-light-tx-3 dark:text-dark-tx-3 hover:underline">
                            Datum entfernen
                          </button>
                        {/if}
                      </div>
                    {/if}
                  </div>

                  <!-- Aktionen. Verwalten, nicht bearbeiten: umbenennen, archivieren,
                       Ablauf, löschen — kein Weg in einen Editor (Leitprinzip 5). -->
                  <div class="shrink-0 flex items-center gap-1">
                    <button onclick={() => umbenennenStarten(b)} disabled={laeuft}
                            title="Umbenennen" aria-label="{b.title} umbenennen"
                            class="p-1.5 rounded text-light-tx-2 dark:text-dark-tx-2
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-40">
                      <Pencil class="w-4 h-4" />
                    </button>

                    {#if kann.ablauf}
                      <button onclick={() => ablaufOeffnen(b)} disabled={laeuft}
                              title="Ablaufdatum ändern"
                              aria-label="Ablaufdatum von {b.title} ändern"
                              class="p-1.5 rounded text-light-tx-2 dark:text-dark-tx-2
                                     hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-40">
                        <CalendarClock class="w-4 h-4" />
                      </button>
                    {/if}

                    {#if kann.archivieren}
                      <button onclick={() => archivieren(b)} disabled={laeuft}
                              title="Archivieren" aria-label="{b.title} archivieren"
                              class="p-1.5 rounded text-light-tx-2 dark:text-dark-tx-2
                                     hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-40">
                        <Archive class="w-4 h-4" />
                      </button>
                    {:else if kann.reaktivieren}
                      <button onclick={() => reaktivieren(b)} disabled={laeuft}
                              title="Zurückholen — mit neuem Ablaufdatum"
                              aria-label="{b.title} zurückholen"
                              class="p-1.5 rounded text-light-tx-2 dark:text-dark-tx-2
                                     hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-40">
                        <RotateCcw class="w-4 h-4" />
                      </button>
                    {/if}

                    <button onclick={() => (loeschKandidat = { baustein: b, hindernis: null })}
                            disabled={laeuft}
                            title="Löschen" aria-label="{b.title} löschen"
                            class="p-1.5 rounded text-light-tx-2 dark:text-dark-tx-2
                                   hover:bg-light-re/15 hover:text-light-re
                                   dark:hover:bg-dark-re/15 dark:hover:text-dark-re
                                   disabled:opacity-40">
                      <Trash2 class="w-4 h-4" />
                    </button>
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
{#if rueckgaengig}
  <!-- Undo statt Rückfrage: Archivieren ist folgenlos und umkehrbar, ein Dialog davor
       wäre eine Bremse ohne Nutzen (Entscheidung 6 des Plans). Gelöscht wird dagegen
       nur nach Rückfrage — das lässt sich nicht zurücknehmen. -->
  <div class="fixed bottom-4 left-1/2 -translate-x-1/2 z-50
              flex items-center gap-3 px-4 py-2 rounded-lg shadow-lg
              bg-light-bg-2 dark:bg-dark-bg-2
              border border-light-ui-3 dark:border-dark-ui-3">
    <Check class="w-4 h-4 text-light-gr dark:text-dark-gr" />
    <span class="text-sm text-light-tx dark:text-dark-tx">{rueckgaengig.text}</span>
    <button
      onclick={() => { const t = rueckgaengig; rueckgaengig = null; t.tun() }}
      class="text-sm text-light-bl dark:text-dark-bl hover:underline"
    >Rückgängig</button>
    <button onclick={() => (rueckgaengig = null)} aria-label="Hinweis schließen"
            class="text-light-tx-3 dark:text-dark-tx-3 hover:text-light-tx dark:hover:text-dark-tx">
      <X class="w-4 h-4" />
    </button>
  </div>
{/if}

{#if loeschKandidat}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
    <div class="w-full max-w-md rounded-lg p-6
                bg-light-bg dark:bg-dark-bg
                border border-light-ui-3 dark:border-dark-ui-3">
      <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx">
        Baustein löschen?
      </h2>
      <p class="mt-2 text-sm text-light-tx-2 dark:text-dark-tx-2">
        „{loeschKandidat.baustein.title}" wird endgültig entfernt. Das lässt sich
        nicht rückgängig machen.
      </p>

      {#if loeschKandidat.hindernis}
        <!-- F7-Regel (ADR-019): Verweisen aktive Bausteine anderer darauf, ist
             Löschen die falsche Handlung — es reißt in fremde Planungen ein Loch,
             das dort niemand erklären kann. Archivieren erhält die Kanten. -->
        <div class="mt-4 rounded-lg border border-light-ye/40 dark:border-dark-ye/40
                    bg-light-ye/10 dark:bg-dark-ye/10 px-3 py-2">
          <p class="text-sm text-light-tx dark:text-dark-tx">
            {loeschKandidat.hindernis.nachricht}
          </p>
          {#if loeschKandidat.hindernis.referenzen.length}
            <ul class="mt-2 space-y-0.5 text-xs text-light-tx-2 dark:text-dark-tx-2">
              {#each loeschKandidat.hindernis.referenzen as r (r.id)}
                <li>· {r.title}</li>
              {/each}
            </ul>
          {/if}
        </div>
      {/if}

      <div class="mt-5 flex justify-end gap-2">
        <button onclick={() => (loeschKandidat = null)}
                class="px-3 py-1.5 text-sm rounded-lg
                       text-light-tx dark:text-dark-tx
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2">
          Abbrechen
        </button>
        {#if loeschKandidat.hindernis}
          <button onclick={() => { const b = loeschKandidat.baustein; loeschKandidat = null; archivieren(b) }}
                  disabled={laeuft}
                  class="px-3 py-1.5 text-sm rounded-lg
                         bg-primary dark:bg-primary-dark text-white disabled:opacity-40">
            Stattdessen archivieren
          </button>
        {:else}
          <button onclick={loeschenBestaetigen} disabled={laeuft}
                  class="px-3 py-1.5 text-sm rounded-lg text-white disabled:opacity-40
                         bg-light-re dark:bg-dark-re">
            Endgültig löschen
          </button>
        {/if}
      </div>
    </div>
  </div>
{/if}

