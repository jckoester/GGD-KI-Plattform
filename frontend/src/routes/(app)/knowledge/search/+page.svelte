<script>
    /**
     * Suchseite des Kontextspeichers (ADR-017, AP7).
     *
     * Sie zeigt den Ergebnisumschlag so, wie er gemeint ist: drei beschriftete
     * Abschnitte statt einer vermischten Liste. Der Unterschied ist keine Optik —
     * er entscheidet, was eine Antwort trägt. Was so **heißt**, belegt, dass es
     * einen Baustein dieses Namens gibt; was nur so **ähnelt**, belegt gar nichts.
     */
    import {
        ChevronRight,
        Loader2,
        MessageSquarePlus,
        Pin,
        Search,
        Waypoints,
    } from "lucide-svelte";
    import { goto } from "$app/navigation";
    import { page } from "$app/stores";
    import { onMount } from "svelte";

    import ContextNodeLabel from "$lib/components/ContextNodeLabel.svelte";
    import { mehrdeutigeFassungen } from "$lib/bp_fassung.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import { addChatContextNode, searchContextNodes } from "$lib/api.js";
    import { fuerNeuenChat } from "$lib/context_handover.js";
    import { holen, merken, suchSchluessel } from "$lib/suche_cache.js";
    // Dieselben Abschnittstitel wie im Vorschlagsfenster des Chats: Derselbe Umschlag
    // darf an zwei Stellen nicht verschieden heißen.
    import { ABSCHNITT_TITEL } from "$lib/umschlag.js";
    import { CONTENT_TYPE_LABELS } from "$lib/taxonomy.js";
    import { STUDENT_GRADES } from "$lib/grades.js";
    import { activeConversationId, pageTitle } from "$lib/stores/pageTitle.js";
    import { subjects } from "$lib/stores/subjects.js";
    import { user } from "$lib/stores/user.js";

    pageTitle.set("Suche");

    // Wie viele Treffer je Abschnitt. Großzügiger als das Vorschlagsfenster im Chat:
    // Dort ist die Trefferzahl eine Platzfrage, hier nicht.
    const PRO_ABSCHNITT = 25;

    // Wozu die Häkchen da sind. Steht als Tooltip an jeder Checkbox **und** als Zeile
    // über der ersten Trefferliste: Die Aktionsleiste, die es sonst erklären würde,
    // erscheint erst, wenn man bereits ausgewählt hat.
    const AUSWAHL_ZWECK =
        "Bausteine auswählen, um sie einem Chat als Kontext mitzugeben.";

    // ⚠️ **Der Suchzustand gehört in die URL, nicht nur in die Komponente.** Wer einen
    // Treffer öffnet und zurückkommt, bekommt sonst eine leere Suchseite: Beim Verlassen
    // der Route wird die Komponente abgebaut, ihr Zustand mit. Über die URL überlebt die
    // Suche den Ausflug — und lässt sich nebenbei weitergeben.
    let frage = $state($page.url.searchParams.get("q") ?? "");
    let umschlag = $state(null);
    let laeuft = $state(false);
    let fehler = $state(null);
    let gesucht = $state(""); // wonach der angezeigte Umschlag gesucht wurde

    // Facetten — Verfeinerung des Ergebnisses, keine Vorbedingung.
    let typ = $state($page.url.searchParams.get("typ") ?? "");
    let fachId = $state($page.url.searchParams.get("fach") ?? "");
    let stufe = $state($page.url.searchParams.get("stufe") ?? "");

    let auswahl = $state(new Set());

    const hatFacette = $derived(Boolean(typ || fachId || stufe));
    const offeneKonversation = $derived($activeConversationId);

    // Detailansicht und Wissensgraph hängen an `GET /context/nodes/{id}` und sind
    // Lehrkraft-gesichert. Für Schüler:innen ist die Knotensicht in ADR-019 für 0.9
    // vorgesehen — sie hier nachzuziehen, hieße diese Entscheidung zu überholen.
    // Bis dahin liefert die Suche ihnen Namensauflösung, Zählung und das Anheften.
    const istLehrkraft = $derived(
        ($user?.roles?.includes("teacher") ?? false) ||
            ($user?.roles?.includes("admin") ?? false),
    );

    // Die Identifikation führt zwei Stufen in einem Abschnitt. Getrennt anzeigen:
    // Nur die exakten Namensträger tragen die Aussage, dass es den Namen gibt.
    // ⚠️ `=== "exakt"`, nicht `!== "teilweise"`: Die Identifikation kennt seit AP9 eine
    // dritte Stufe (`praefix`). Eine Ausschlussprüfung ließe sie als Namensträger
    // durchgehen — und „n Bausteine heißen so" wäre dann keine belastbare Auskunft mehr.
    const exakte = $derived(
        (umschlag?.identifikation?.treffer ?? []).filter(
            (t) => t.treffer_art === "exakt",
        ),
    );
    const aehnlich = $derived(
        (umschlag?.identifikation?.treffer ?? []).filter(
            (t) => t.treffer_art !== "exakt",
        ),
    );
    const thematisch = $derived(umschlag?.thematisch?.treffer ?? []);
    const aufzaehlung = $derived(umschlag?.aufzaehlung ?? null);

    // „Dazu gibt es keinen Baustein" darf sich **nur** auf Identifikation und
    // Aufzählung stützen. Thematische Nachbarn belegen nichts (ADR-017, Existenz).
    const nichtsGefunden = $derived(
        umschlag !== null &&
            exakte.length === 0 &&
            (aufzaehlung?.gesamt ?? 0) === 0,
    );

    /** Den Suchzustand in die Adresszeile spiegeln — ohne History-Eintrag je Tastendruck. */
    function inDieUrl(q) {
        const url = new URL($page.url);
        for (const [name, wert] of [
            ["q", q], ["typ", typ], ["fach", fachId], ["stufe", stufe],
        ]) {
            wert ? url.searchParams.set(name, String(wert)) : url.searchParams.delete(name);
        }
        goto(url, { replaceState: true, keepFocus: true, noScroll: true });
    }

    /** Anfrage und Facetten — beide bestimmen das Ergebnis, beide gehören in den Schlüssel. */
    const cacheSchluessel = () =>
        suchSchluessel({ q: frage, typ, fach: fachId, stufe });

    onMount(() => {
        if (!frage.trim()) return;
        // Rückkehr aus der Detail- oder Graphansicht: Das Ergebnis liegt noch vor, der
        // Wissensgraph hat sich in der Zwischenzeit nicht geändert. Erneut zu suchen
        // hieße, rund 400 ms für dasselbe Ergebnis zu warten.
        const gemerkt = holen(cacheSchluessel());
        if (gemerkt) {
            umschlag = gemerkt;
            gesucht = frage.trim();
            return;
        }
        suchen();
    });

    async function suchen() {
        const q = frage.trim();
        if (!q) return;
        inDieUrl(q);
        laeuft = true;
        fehler = null;
        try {
            umschlag = await searchContextNodes(q, null, {
                limit: PRO_ABSCHNITT,
                content_type: typ ? [typ] : null,
                subject_id: fachId ? Number(fachId) : null,
                grade: stufe ? Number(stufe) : null,
            });
            merken(cacheSchluessel(), umschlag);
            gesucht = q;
            auswahl = new Set();
        } catch (err) {
            fehler = err?.message ?? "Die Suche ist fehlgeschlagen.";
            umschlag = null;
        } finally {
            laeuft = false;
        }
    }

    // Wohin die Detailansicht zurückführt. Konvention im Wissensgraphen: `?back=` mit
    // Pfad **und** Query — nur so kommt der Suchzustand mit zurück.
    const rueckweg = $derived(
        encodeURIComponent($page.url.pathname + $page.url.search),
    );

    function umschalten(nodeId) {
        const naechste = new Set(auswahl);
        naechste.has(nodeId) ? naechste.delete(nodeId) : naechste.add(nodeId);
        auswahl = naechste;
    }

    /** Alle angezeigten Treffer, um aus IDs wieder Knoten zu machen. */
    const alleTreffer = $derived([
        ...exakte,
        ...aehnlich,
        ...(aufzaehlung?.treffer ?? []),
        ...thematisch,
    ]);

    const gewaehlt = $derived(
        alleTreffer.filter((t) => auswahl.has(t.node_id)),
    );

    // Solange zwei Bildungsplan-Editionen aktiv sind, stehen gleiche Nummern mit
    // verschiedenem Text nebeneinander. Über alle Abschnitte hinweg verglichen: Die
    // eine Fassung kann als Namensträger auftauchen, die andere thematisch.
    const fassungen = $derived(mehrdeutigeFassungen(alleTreffer));

    async function anheften() {
        if (!offeneKonversation || !gewaehlt.length) return;
        laeuft = true;
        try {
            for (const knoten of gewaehlt) {
                await addChatContextNode(offeneKonversation, knoten.node_id);
            }
            await goto(`/chat?id=${offeneKonversation}`);
        } catch (err) {
            fehler = err?.message ?? "Anheften fehlgeschlagen.";
        } finally {
            laeuft = false;
        }
    }

    function neuerChat() {
        if (!gewaehlt.length) return;
        fuerNeuenChat(gewaehlt);
        goto("/chat");
    }
</script>

<svelte:head><title>Suche · Wissensgraph</title></svelte:head>

<!-- `<main>` im App-Layout ist `overflow-hidden`: Jede Seite bringt ihren eigenen
     Scrollbereich mit. Die Auswahlleiste steht **außerhalb** davon und bleibt damit
     sichtbar — sonst müsste man zum Bestätigen erst ans Listenende scrollen. -->
<div class="h-full flex flex-col">
    <div class="flex-1 overflow-y-auto">
        <div class="max-w-4xl mx-auto px-4 py-6">
            <h1 class="text-xl font-semibold text-light-tx dark:text-dark-tx mb-1">
                Bausteine suchen
            </h1>
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-5">
                Durchsucht den Kontextspeicher nach Namen und nach Thema.
            </p>

            <form onsubmit={(e) => { e.preventDefault(); suchen(); }} class="space-y-3">
                <div class="flex gap-2">
                    <input
                        type="search"
                        bind:value={frage}
                        placeholder="Suchbegriff oder ganze Frage"
                        aria-label="Suchbegriff"
                        class="flex-1 px-3 py-2 rounded-lg text-sm
                               bg-light-bg-2 dark:bg-dark-bg-2
                               text-light-tx dark:text-dark-tx
                               border border-light-ui-3 dark:border-dark-ui-3"
                    />
                    <button
                        type="submit"
                        disabled={laeuft || !frage.trim()}
                        class="px-4 py-2 rounded-lg text-sm bg-primary dark:bg-primary-dark text-white
                               hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed
                               flex items-center gap-2"
                    >
                        {#if laeuft}
                            <Loader2 class="w-4 h-4 animate-spin" />
                        {:else}
                            <Search class="w-4 h-4" />
                        {/if}
                        Suchen
                    </button>
                </div>

                <!-- Facetten: Verfeinerung des Ergebnisses, nicht Vorbedingung. Sie sind
                     deshalb optional und lösen zusätzlich die gezählte Aufzählung aus. -->
                <div class="flex flex-wrap gap-2 text-sm">
                    <select
                        bind:value={typ}
                        onchange={() => gesucht && suchen()}
                        aria-label="Bausteinart"
                        class="pl-3 pr-9 py-1.5 text-sm rounded-md
                               border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                    >
                        <option value="">Alle Bausteinarten</option>
                        {#each Object.entries(CONTENT_TYPE_LABELS) as [wert, label]}
                            <option value={wert}>{label}</option>
                        {/each}
                    </select>

                    <select
                        bind:value={fachId}
                        onchange={() => gesucht && suchen()}
                        aria-label="Fach"
                        class="pl-3 pr-9 py-1.5 text-sm rounded-md
                               border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                    >
                        <option value="">Alle Fächer</option>
                        {#each $subjects as fach}
                            <option value={fach.id}>{fach.name}</option>
                        {/each}
                    </select>

                    <select
                        bind:value={stufe}
                        onchange={() => gesucht && suchen()}
                        aria-label="Jahrgangsstufe"
                        class="pl-3 pr-9 py-1.5 text-sm rounded-md
                               border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
                    >
                        <option value="">Alle Stufen</option>
                        {#each STUDENT_GRADES as k}
                            <option value={k}>Klasse {k}</option>
                        {/each}
                    </select>
                </div>
            </form>

            {#if fehler}
                <div class="mt-4"><ErrorBanner message={fehler} /></div>
            {/if}

            {#if laeuft && !umschlag}
                <div class="mt-4"><LoadingBanner message="Sucht…" /></div>
            {/if}

            {#if umschlag && !nichtsGefunden}
                <p class="mt-5 text-xs text-light-tx-2 dark:text-dark-tx-2">
                    {AUSWAHL_ZWECK}
                </p>
            {/if}

            {#if umschlag}
                {#if nichtsGefunden}
                    <!-- Ehrlich: kein Baustein dieses Namens. Über das Thema sagt das nichts —
                         die nächstliegenden Bausteine stehen trotzdem darunter. -->
                    <div class="mt-5">
                        <InfoBanner
                            message={`Kein Baustein heißt „${gesucht}“${hatFacette ? " (mit diesen Filtern)" : ""}. Das heißt nicht, dass es zum Thema nichts gibt — siehe unten.`}
                        />
                    </div>
                {/if}

                {#each umschlag.hinweise ?? [] as hinweis}
                    <p class="mt-3 text-xs text-light-tx-2 dark:text-dark-tx-2">{hinweis}</p>
                {/each}

                <!-- Abschnitt 1: exakte Namensträger -->
                {#if exakte.length}
                    {@render abschnitt(
                        ABSCHNITT_TITEL.exakt,
                        exakte,
                        umschlag.identifikation.vollstaendig
                            ? `${umschlag.identifikation.gesamt} gefunden`
                            : `${exakte.length} von ${umschlag.identifikation.gesamt} — grenze die Suche ein, um alle zu sehen`,
                    )}
                {/if}

                <!-- Abschnitt 2: ähnlich benannte -->
                {#if aehnlich.length}
                    {@render abschnitt(
                        ABSCHNITT_TITEL.aehnlich,
                        aehnlich,
                        "Prüfe am Titel, ob einer gemeint ist — sie belegen nicht, dass es den gesuchten Namen gibt.",
                    )}
                {/if}

                <!-- Abschnitt 3: Aufzählung (nur bei gesetzten Facetten) -->
                {#if aufzaehlung}
                    {@render abschnitt(
                        ABSCHNITT_TITEL.aufzaehlung,
                        aufzaehlung.treffer,
                        aufzaehlung.vollstaendig
                            ? `${aufzaehlung.gesamt} insgesamt`
                            : `${aufzaehlung.treffer.length} von ${aufzaehlung.gesamt}`,
                    )}
                    {#if aufzaehlung.hinweis}
                        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 -mt-2 mb-4">
                            {aufzaehlung.hinweis}
                        </p>
                    {/if}
                    {#if aufzaehlung.gruppen?.length}
                        <div class="-mt-2 mb-5 flex flex-wrap gap-1.5">
                            {#each aufzaehlung.gruppen as gruppe}
                                <span
                                    class="px-2 py-0.5 rounded text-xs
                                           bg-light-bg-2 dark:bg-dark-bg-2
                                           text-light-tx-2 dark:text-dark-tx-2
                                           border border-light-ui-3 dark:border-dark-ui-3"
                                >
                                    {gruppe.name}: {gruppe.anzahl}
                                </span>
                            {/each}
                        </div>
                    {/if}
                {/if}

                <!-- Abschnitt 4: thematische Nachbarn. Nie als vollständig dargestellt. -->
                {#if thematisch.length}
                    {@render abschnitt(
                        ABSCHNITT_TITEL.thematisch,
                        thematisch,
                        "Nach Ähnlichkeit sortiert. Diese Liste ist nie vollständig.",
                    )}
                {/if}
            {/if}
        </div>
    </div>

    {#if gewaehlt.length}
        <!-- Aktionsleiste. „Anheften" nur bei offener Konversation — sonst gäbe es nichts,
             woran man anheften könnte; dafür gibt es den neuen Chat. -->
        <div
            class="shrink-0 border-t border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg px-4 py-3"
        >
            <div class="max-w-4xl mx-auto flex items-center gap-3 text-sm">
                <span class="text-light-tx-2 dark:text-dark-tx-2">
                    {gewaehlt.length}
                    {gewaehlt.length === 1 ? "Baustein" : "Bausteine"} gewählt
                </span>
                <div class="flex-1"></div>
                {#if offeneKonversation}
                    <button
                        type="button"
                        onclick={anheften}
                        disabled={laeuft}
                        class="px-3 py-1.5 rounded-lg text-sm flex items-center gap-2
                               text-light-tx dark:text-dark-tx
                               border border-light-ui-3 dark:border-dark-ui-3
                               hover:bg-light-ui dark:hover:bg-dark-ui
                               disabled:opacity-40"
                    >
                        <Pin class="w-4 h-4" />
                        An offenen Chat anheften
                    </button>
                {/if}
                <button
                    type="button"
                    onclick={neuerChat}
                    class="px-3 py-1.5 rounded-lg text-sm flex items-center gap-2
                           bg-primary dark:bg-primary-dark text-white hover:opacity-90"
                >
                    <MessageSquarePlus class="w-4 h-4" />
                    Neuen Chat damit starten
                </button>
            </div>
        </div>
    {/if}
</div>

{#snippet abschnitt(titel, treffer, zeile)}
    <section class="mt-5 mb-4">
        <div class="flex items-baseline gap-2 mb-2">
            <h2 class="text-sm font-medium text-light-tx dark:text-dark-tx">
                {titel}
            </h2>
            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">{zeile}</span>
        </div>
        <ul class="space-y-1">
            {#each treffer as knoten (knoten.node_id)}
                <li
                    class="flex items-start gap-2 px-2 py-1.5 rounded-lg
                           hover:bg-light-bg-2 dark:hover:bg-dark-bg-2"
                >
                    <input
                        type="checkbox"
                        checked={auswahl.has(knoten.node_id)}
                        onchange={() => umschalten(knoten.node_id)}
                        title={AUSWAHL_ZWECK}
                        aria-label={`„${knoten.title}“ für einen Chat auswählen`}
                        class="mt-1 accent-primary"
                    />
                    <!-- Symbol, Fach und Typ kommen aus `ContextNodeLabel` — die
                         Komponente ist genau dafür da, dass Kontextknoten überall
                         gleich aussehen. Sie hier zusätzlich zu beschriften, hieß
                         Fach und Symbol doppelt zu zeigen. -->
                    <div class="min-w-0 flex-1 flex items-center gap-2">
                        <ContextNodeLabel
                            node={knoten}
                            fassung={fassungen.get(knoten.node_id)}
                            titleClass="truncate text-light-tx dark:text-dark-tx"
                        />
                    </div>
                    {#if istLehrkraft}
                        <a
                            href={`/knowledge/${knoten.node_id}/graph?back=${rueckweg}`}
                            title="Graphansicht öffnen"
                            class="shrink-0 text-xs text-light-tx-2 dark:text-dark-tx-2
                                   hover:text-light-bl dark:hover:text-dark-bl"
                        >
                            <Waypoints class="w-4 h-4" />
                        </a>
                        <a
                            href={`/knowledge/${knoten.node_id}?back=${rueckweg}`}
                            class="shrink-0 text-xs flex items-center gap-1
                                   text-light-bl dark:text-dark-bl hover:underline"
                        >
                            Ansehen <ChevronRight class="w-3 h-3" />
                        </a>
                    {/if}
                </li>
            {/each}
        </ul>
    </section>
{/snippet}
