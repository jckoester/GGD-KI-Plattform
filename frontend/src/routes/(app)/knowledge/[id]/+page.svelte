<script>
    import { untrack } from "svelte";
    import { getNeighborhood, deleteContextEdge } from "$lib/api.js";
    import { kannVerknuepfen, istStub } from "$lib/collections.js";
    import { gruppiereKanten } from "$lib/vernetzung.js";
    import { bearbeitenZiel } from "$lib/bearbeiten.js";
    import VerknuepfenDialog from "$lib/components/VerknuepfenDialog.svelte";


    import { page } from "$app/stores";
    import { goto } from "$app/navigation";
    import { CATEGORY_LABELS, CONTENT_TYPE_LABELS } from "$lib/taxonomy.js";
    import { getContextNode, getArchivedReferences, updateNodeTitle } from "$lib/api.js";
    import { renderInlineMath, renderMarkdown } from "$lib/markdown.js";
    import { renderDiagrams } from "$lib/diagrams.js";
    import { renderServerBlocks } from "$lib/serverRender.js";
    import { fuelleAbbildungen, ohneEinbettung } from "$lib/abbildungen.js";
    import { feldSchema } from "$lib/collections.js";
    import { user } from "$lib/stores/user.js";
    import { subjectMap } from "$lib/stores/subjects.js";
    import { ArrowLeft, Pencil, Check, X } from "lucide-svelte";
    import WarningBanner from "$lib/components/WarningBanner.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import NodeTypeIcon from "$lib/components/NodeTypeIcon.svelte";
    import PageBody from '$lib/components/PageBody.svelte'

    let node = $state(null);
    let loadingNode = $state(true);
    let error = $state(null);
    let archivedRefs = $state([]);

    // C1: Inline-Titel-Korrektur importierter BP-Knoten (nur Admin).
    let editingTitle = $state(false);
    let titleDraft = $state("");
    let savingTitle = $state(false);
    let titleError = $state(null);

    const isAdmin = $derived($user?.roles?.includes("admin") ?? false);
    // Importierte BP-Knoten tragen metadata.bp_id; nur der Titel ist korrigierbar,
    // der Inhalt bleibt read-only (die Voll-Bearbeiten-Ansicht entfällt für sie).
    const isImported = $derived(!!node?.metadata?.bp_id);

    function startTitleEdit() {
        titleDraft = node.title;
        titleError = null;
        editingTitle = true;
    }

    async function saveTitle() {
        const t = titleDraft.trim();
        if (!t) {
            titleError = "Titel darf nicht leer sein.";
            return;
        }
        savingTitle = true;
        titleError = null;
        try {
            const updated = await updateNodeTitle(node.id, t);
            node = { ...node, title: updated.title, title_locked: updated.title_locked };
            editingTitle = false;
        } catch (e) {
            titleError = e.message;
        } finally {
            savingTitle = false;
        }
    }

    const backUrl = $derived(
        $page.url.searchParams.get("back") ?? "/knowledge",
    );

    // Die Graphansicht ebenso: Von dort führt „Zurück zum Knoten" hierher, und von hier
    // muss der Weg zur Ausgangsliste offen bleiben.
    const graphUrl = $derived(
        `/knowledge/${$page.params.id}/graph` +
            ($page.url.searchParams.get("back")
                ? `?back=${encodeURIComponent($page.url.searchParams.get("back"))}`
                : ""),
    );

    // Wohin „Bearbeiten" führt, entscheidet der Typ: Sammlungen haben ihren
    // Formular-Editor, Planungsobjekte gehören in den Planer, alles Übrige in den
    // allgemeinen Editor. Die Regel steht in `bearbeiten.js` — sie ist zu verzweigt für
    // eine Komponente und ohne Browser sonst nicht prüfbar.
    const ziel = $derived(
        bearbeitenZiel(
            node,
            node?.subject_id ? ($subjectMap[node.subject_id] ?? null) : null,
            $page.url.searchParams.get("back"),
        ),
    );

    // ── Nachbarschaft (UI-Notiz A3) ──────────────────────────────────────────
    //
    // Ego-Graph der Tiefe 1, nach Relationstyp gruppiert. Die Leitplanke aus ADR-013
    // gilt: nie „alle Kanten" auf einmal — ab `KAPPUNG` Nachbarn je Relationstyp steht
    // „+ n weitere" und der Weg in die große Ansicht.

    let nachbarschaft = $state(null);
    let nachbarnFehler = $state(null);
    let dialogOffen = $state(false);

    async function ladeNachbarschaft(id) {
        nachbarnFehler = null;
        try {
            nachbarschaft = await getNeighborhood(id, { depth: 1 });
        } catch (e) {
            nachbarnFehler = e.message;
            nachbarschaft = null;
        }
    }

    $effect(() => {
        const id = $page.params.id;
        untrack(() => ladeNachbarschaft(id));
    });

    const gruppen = $derived(gruppiereKanten(node, nachbarschaft));

    const kannVerknuepfenJetzt = $derived(
        Boolean(node) && kannVerknuepfen(node.content_type) && canEdit,
    );

    async function entferneKante(kanteId) {
        nachbarnFehler = null;
        try {
            await deleteContextEdge(kanteId);
            await ladeNachbarschaft($page.params.id);
        } catch (e) {
            nachbarnFehler = e.message;
        }
    }

    const canEdit = $derived(
        node &&
            $user &&
            (($user.roles?.includes("admin") ?? false) ||
                node.owner_pseudonym === $user.pseudonym),
    );

    const subjectName = $derived(
        node?.subject_id != null
            ? ($subjectMap[node.subject_id]?.name ?? null)
            : null,
    );

    const contentHtml = $derived(
        node?.content ? renderMarkdown(node.content) : "",
    );

    const SCOPE_LABELS = {
        private: "Privat",
        group: "Gruppe",
        subject: "Fach",
        school: "Schule",
        global: "Global",
    };

    const isStructured = $derived(node?.content_type === "funktion");

    // ── Abbildungen (Paket 9, AP6) ───────────────────────────────────────────
    //
    // Der Platzhalter `{{abbildung:…}}` im Text wird zur leeren Hülle (renderMarkdown);
    // gefüllt wird sie hier, weil erst hier der Knoten und damit
    // `metadata.illustrationen` bekannt ist. Dieselbe Funktion füllt die Hüllen, die
    // unten für die Abbildungen ohne Einbettung und für das Schaltzeichen stehen —
    // deshalb umschließt `inhaltWurzel` beide Bereiche.
    const illustrationen = $derived(node?.metadata?.illustrationen ?? []);

    // Ein Schaltzeichen ist eine Abbildung wie jede andere, nur ohne Datei. Der
    // Pseudoname hängt es an denselben Renderer, statt einen zweiten zu bauen.
    const SCHALTZEICHEN = "schaltzeichen";
    const schaltzeichen = $derived(
        node?.content_type === "bauteil" && node?.metadata?.schaltzeichen?.svg
            ? { ...node.metadata.schaltzeichen, datei: SCHALTZEICHEN }
            : null,
    );

    const alleAbbildungen = $derived(
        schaltzeichen ? [...illustrationen, schaltzeichen] : illustrationen,
    );

    // Abbildungen, die im Text nicht vorkommen — sie stehen am Ende, statt zu fehlen.
    const nachgestellt = $derived(ohneEinbettung(node?.content ?? "", illustrationen));

    let inhaltWurzel = $state(null);

    $effect(() => {
        // Von `contentHtml` und `alleAbbildungen` abhängig: Beides kommt asynchron, und
        // der Effekt muss **nach** dem Einsetzen des HTML laufen. Ein `use:`-Action mit
        // MutationObserver (wie bei Mermaid) täte es auch, bekäme aber die geänderte
        // Abbildungsliste nicht mit.
        contentHtml;
        const abbildungen = alleAbbildungen;
        if (inhaltWurzel) fuelleAbbildungen(inhaltWurzel, abbildungen);
    });

    /** Häufige Irrtümer — der eigentliche Mehrwert eines Fachbegriffs im Gespräch. */
    const fehlvorstellungen = $derived(
        Array.isArray(node?.metadata?.fehlvorstellungen)
            ? node.metadata.fehlvorstellungen
            : [],
    );

    /**
     * Die Eigenschaftstabelle eines Stoffsteckbriefs.
     *
     * Feste Schlüssel nach Bildungsplan 3.1.2.1 (1), deshalb eine Beschriftungstabelle
     * und kein freies Dictionary: `loeslichkeit_wasser` als Überschrift zu zeigen wäre
     * eine Datenbankspalte, keine Auskunft.
     */
    const EIGENSCHAFT_LABELS = {
        aussehen: "Aussehen",
        schmelztemperatur: "Schmelztemperatur",
        siedetemperatur: "Siedetemperatur",
        dichte: "Dichte",
        loeslichkeit_wasser: "Löslichkeit in Wasser",
        molare_masse: "Molare Masse",
        elektrische_leitfaehigkeit: "Elektrische Leitfähigkeit",
        konzentration: "Konzentration",
        besonderheiten: "Besonderheiten",
    };

    const eigenschaften = $derived(
        Object.entries(node?.metadata?.eigenschaften ?? {})
            .filter(([, wert]) => wert !== null && wert !== "")
            // Reihenfolge der Tabelle, nicht die der Datei: So steht bei jedem Stoff
            // dasselbe an derselben Stelle, und man vergleicht Zeilen statt zu suchen.
            .sort(
                (a, b) =>
                    Object.keys(EIGENSCHAFT_LABELS).indexOf(a[0]) -
                    Object.keys(EIGENSCHAFT_LABELS).indexOf(b[0]),
            )
            .map(([schluessel, wert]) => [
                EIGENSCHAFT_LABELS[schluessel] ?? schluessel,
                String(wert),
            ]),
    );

    /**
     * Die Schema-Felder des Knotens für den Eigenschaften-Block.
     *
     * Aus `taxonomy.js` abgeleitet, nicht aufgezählt: Ein Feld, das AP1 ergänzt, steht
     * damit von selbst da — und ein umbenanntes verschwindet, statt leer zu bleiben.
     * `fehlvorstellungen` und `eigenschaften` bleiben draußen; sie haben oben ihren
     * eigenen Platz.
     */
    const EIGENER_PLATZ = ["fehlvorstellungen", "formel", "fassung", "ab_klasse"];

    const schemaFelder = $derived(
        Object.entries(feldSchema(node?.content_type) ?? {})
            .filter(([name]) => !EIGENER_PLATZ.includes(name))
            .map(([name, feld]) => [feld.label ?? name, node?.metadata?.[name]])
            .filter(([, wert]) => wert !== undefined && wert !== null && wert !== "")
            .map(([label, wert]) => [label, Array.isArray(wert) ? wert.join(", ") : String(wert)]),
    );

    // Knoten laden (Curriculum-Knoten haben eine eigene Ansicht)
    $effect(() => {
        const id = $page.params.id;
        loadingNode = true;
        error = null;
        getContextNode(id)
            .then((n) => {
                if (n.content_type === "curriculum") {
                    goto(`/knowledge/curriculum/${id}`, { replaceState: true });
                    return;
                }
                node = n;
                if (n.status === "active") {
                    getArchivedReferences(n.id)
                        .then((refs) => {
                            archivedRefs = refs;
                        })
                        .catch(() => {});
                }
            })
            .catch((e) => {
                error = e.message;
            })
            .finally(() => {
                loadingNode = false;
            });
    });

    function formatDate(dateString) {
        if (!dateString) return "";
        return new Date(dateString).toLocaleDateString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        });
    }
</script>

<!-- Schmales Muster (`PageBody`): eine Detailseite wird gelesen, nicht überflogen.
     Der **Fließtext** darin bleibt noch schmaler — dafür sorgt unten die Vorgabe des
     Typografie-Plugins (65 Zeichen); eine Definition über die volle Breite zu lesen
     ist mühsamer, nicht leichter. -->
<PageBody>
    <a
        href={backUrl}
        class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2
             hover:text-light-tx dark:hover:text-dark-tx transition-colors"
    >
        <ArrowLeft class="w-4 h-4" /> Zurück
    </a>

    {#if loadingNode}
        <div class="py-8 text-center text-sm text-light-tx-2 dark:text-dark-tx-2">
            Wird geladen…
        </div>
    {:else if error && !node}
        <div class="py-8 text-center text-sm text-light-re dark:text-dark-re">
            {error}
        </div>
    {:else if node}
        <!-- Kopfzeile -->
        <div class="flex items-start justify-between gap-3 mb-2">
            <div class="min-w-0 flex-1">
                {#if editingTitle}
                    <!-- Inline-Titel-Korrektur (Admin, importierter BP-Knoten) -->
                    <div class="flex items-center gap-2">
                        <!-- svelte-ignore a11y_autofocus -->
                        <input
                            bind:value={titleDraft}
                            autofocus
                            onkeydown={(e) => {
                                if (e.key === "Enter") saveTitle();
                                if (e.key === "Escape") (editingTitle = false);
                            }}
                            class="flex-1 text-xl font-bold rounded-md px-2 py-1 border
                                   border-light-ui-3 dark:border-dark-ui-3
                                   bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx"
                        />
                        <button
                            onclick={saveTitle}
                            disabled={savingTitle}
                            title="Speichern"
                            class="shrink-0 p-2 rounded-md bg-primary dark:bg-primary-dark text-white disabled:opacity-50"
                        >
                            <Check class="w-4 h-4" />
                        </button>
                        <button
                            onclick={() => (editingTitle = false)}
                            title="Abbrechen"
                            class="shrink-0 p-2 rounded-md border border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2"
                        >
                            <X class="w-4 h-4" />
                        </button>
                    </div>
                    {#if titleError}
                        <p class="text-sm text-light-re dark:text-dark-re mt-1">{titleError}</p>
                    {/if}
                {:else}
                    <div class="flex items-center gap-3 flex-wrap">
                        <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
                            {@html renderInlineMath(node.title)}
                        </h1>
                        {#if isAdmin && isImported}
                            <button
                                onclick={startTitleEdit}
                                title="Titel korrigieren"
                                class="shrink-0 p-1.5 rounded-md text-light-tx-2 dark:text-dark-tx-2
                                       hover:text-light-tx dark:hover:text-dark-tx
                                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                            >
                                <Pencil class="w-4 h-4" />
                            </button>
                        {/if}
                        <span
                            class="text-xs px-2 py-0.5 rounded-full
                            {node.status === 'active'
                                ? 'bg-light-gr/20 dark:bg-dark-gr/20 text-light-gr dark:text-dark-gr'
                                : 'bg-light-ye/20 dark:bg-dark-ye/20 text-light-ye dark:text-dark-ye'}"
                        >
                            {node.status === "active" ? "Aktiv" : "Archiviert"}
                        </span>
                    </div>
                {/if}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    {CATEGORY_LABELS[node.category] ?? node.category}
                    {#if node.content_type}
                        · {CONTENT_TYPE_LABELS[node.content_type] ??
                            node.content_type}
                    {/if}
                    <!-- ⚠️ Fassung und Klassenstufe **im Kopf**, nicht in den
                         Eigenschaften: Bei gleichnamigen Begriffen („Oxidation") sind
                         sie das Einzige, woran man erkennt, welchen man vor sich hat.
                         Eingeklappt wären sie genau dort unsichtbar, wo sie zählen. -->
                    {#if node.metadata?.fassung}
                        · <span class="text-light-tx dark:text-dark-tx"
                            >{node.metadata.fassung}</span
                        >
                    {/if}
                    {#if node.metadata?.ab_klasse}
                        · ab Klasse {node.metadata.ab_klasse}
                    {/if}
                    {#if node.metadata?.formel}
                        · {@html renderInlineMath(`$${node.metadata.formel}$`)}
                    {/if}
                </p>
            </div>
            {#if canEdit && !isImported && ziel.url}
                <a
                    href={ziel.url}
                    class="shrink-0 flex items-center gap-1.5 px-4 py-2 text-sm rounded-md
                           bg-primary dark:bg-primary-dark text-white font-medium
                           hover:opacity-90 transition-opacity"
                >
                    <Pencil class="w-4 h-4" /> {ziel.label}
                </a>
            {:else if canEdit && !isImported && ziel.hinweis}
                <!-- Kein Knopf ins Leere: Der eigene Editor braucht Angaben, die an
                     diesem Knoten nicht stehen. Dann lieber sagen, wo es hingehört. -->
                <p
                    class="shrink-0 max-w-56 text-xs text-light-tx-2 dark:text-dark-tx-2"
                >
                    {ziel.hinweis}
                </p>
            {/if}
        </div>

        <!-- Banner: Import-Hinweis (z. B. LFDB — Inhalte nur als PDF) -->
        {#if node.metadata?.import_hinweis}
            <WarningBanner message={node.metadata.import_hinweis} />
        {/if}

        <!-- Banner für archivierte Referenzen -->
        {#if archivedRefs.length > 0}
            <div
                class="mb-4 px-4 py-3 rounded-md border border-light-ye dark:border-dark-ye
                  bg-light-ye/10 dark:bg-dark-ye/10 text-sm text-light-tx dark:text-dark-tx"
            >
                <p class="font-medium mb-1">
                    ⚠️ Dieser Knoten verweist auf archivierte Inhalte:
                </p>
                <ul class="space-y-1 ml-2">
                    {#each archivedRefs as ref (ref.id)}
                        <li>
                            <span class="text-light-tx-2 dark:text-dark-tx-2"
                                >{ref.relation}:</span
                            >
                            <a
                                href="/knowledge/{ref.id}"
                                class="underline text-light-tx dark:text-dark-tx hover:text-primary dark:hover:text-primary-dark"
                            >
                                {ref.title}
                            </a>
                        </li>
                    {/each}
                </ul>
            </div>
        {/if}

        <!-- Inhalt. `inhaltWurzel` umschließt alles, was Abbildungshüllen enthalten
             kann — den Fließtext, die nachgestellten Abbildungen und das
             Schaltzeichen. Gefüllt werden sie alle von derselben Funktion. -->
        <div bind:this={inhaltWurzel}>
            {#if contentHtml}
                <div
                    class="prose dark:prose-invert
                           prose-p:text-light-tx dark:prose-p:text-dark-tx
                           prose-headings:text-light-tx dark:prose-headings:text-dark-tx
                           prose-strong:text-light-tx dark:prose-strong:text-dark-tx
                           prose-li:text-light-tx dark:prose-li:text-dark-tx
                           prose-a:text-light-bl dark:prose-a:text-dark-bl"
                    use:renderDiagrams
                    use:renderServerBlocks
                >
                    {@html contentHtml}
                </div>
            {:else}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 italic">
                    Kein Inhalt hinterlegt.
                </p>
            {/if}

            <!-- Eigenschaften eines Stoffs: der Zweck des Steckbriefs. Feste Reihenfolge,
                 damit man Zeilen vergleicht, statt sie zu suchen. -->
            {#if eigenschaften.length > 0}
                <section class="mt-6">
                    <h2
                        class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-2"
                    >
                        Eigenschaften des Stoffs
                    </h2>
                    <dl
                        class="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm
                               border border-light-ui-3 dark:border-dark-ui-3 rounded-lg p-4
                               bg-light-bg-2 dark:bg-dark-bg-2"
                    >
                        {#each eigenschaften as [label, wert] (label)}
                            <dt class="text-light-tx-2 dark:text-dark-tx-2">{label}</dt>
                            <dd class="text-light-tx dark:text-dark-tx">
                                {@html renderInlineMath(wert)}
                            </dd>
                        {/each}
                    </dl>
                </section>
            {/if}

            <!-- ⚠️ **Eigener Abschnitt, nicht in den Eigenschaften versteckt.** Häufige
                 Irrtümer sind das, wogegen eine Erklärung anarbeiten muss — für eine
                 Lehrkraft der Grund, den Eintrag überhaupt zu öffnen. -->
            {#if fehlvorstellungen.length > 0}
                <section class="mt-6">
                    <h2
                        class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-2"
                    >
                        Häufige Irrtümer
                    </h2>
                    <ul
                        class="space-y-1.5 text-sm text-light-tx dark:text-dark-tx
                               list-disc pl-5"
                    >
                        {#each fehlvorstellungen as irrtum, i (i)}
                            <li>{@html renderInlineMath(irrtum)}</li>
                        {/each}
                    </ul>
                </section>
            {/if}

            <!-- Abbildungen ohne Einbettung: Sie stehen nicht im Text, gehören aber zum
                 Eintrag. Die Hülle ist dieselbe wie im Fließtext. -->
            {#if nachgestellt.length > 0}
                <section class="mt-6">
                    <h2
                        class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-2"
                    >
                        Abbildungen
                    </h2>
                    {#each nachgestellt as abb (abb.datei)}
                        <span class="abbildung-block" data-datei={abb.datei}></span>
                    {/each}
                </section>
            {/if}

            <!-- Schaltzeichen eines Bauteils: bis 09/2026 nur im Bearbeiten-Modus
                 sichtbar — also für alle, die nicht bearbeiten dürfen, gar nicht. -->
            {#if schaltzeichen}
                <section class="mt-6">
                    <h2
                        class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-2"
                    >
                        Schaltzeichen
                        {#if node.metadata.schaltzeichen.norm}
                            <span
                                class="font-normal text-light-tx-2 dark:text-dark-tx-2"
                                >· {node.metadata.schaltzeichen.norm}</span
                            >
                        {/if}
                    </h2>
                    <span class="abbildung-block" data-datei={SCHALTZEICHEN}></span>
                </section>
            {/if}
        </div>

        <!-- Hinweis für strukturierte Typen (MVP: Details im Bearbeiten-Modus) -->
        {#if isStructured}
            <p class="mt-4 text-sm text-light-tx-2 dark:text-dark-tx-2">
                Die Funktionssignatur ist im Bearbeiten-Modus sichtbar.
            </p>
        {/if}
        <!-- ── Nachbarschaft (A3) + Verknüpfen (A8) ───────────────────────── -->
        <section class="mb-5 mt-2">
            <div class="flex items-center justify-between gap-3 mb-2">
                <h2 class="text-sm font-semibold text-light-tx dark:text-dark-tx">
                    Vernetzung
                </h2>
                <div class="flex items-center gap-3">
                    {#if kannVerknuepfenJetzt}
                        <button
                            onclick={() => (dialogOffen = !dialogOffen)}
                            class="text-sm text-light-bl dark:text-dark-bl hover:underline"
                        >
                            Verknüpfen
                        </button>
                    {/if}
                    <a
                        href={graphUrl}
                        class="text-sm text-light-bl dark:text-dark-bl hover:underline"
                    >
                        Graphansicht
                    </a>
                </div>
            </div>

            {#if nachbarnFehler}
                <ErrorBanner message={nachbarnFehler} />
            {/if}

            {#if dialogOffen}
                <div class="mb-3">
                    <VerknuepfenDialog
                        {node}
                        onclose={() => (dialogOffen = false)}
                        onverknuepft={() => ladeNachbarschaft($page.params.id)}
                    />
                </div>
            {/if}

            {#if gruppen.length === 0}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                    Noch nicht vernetzt.
                    {#if kannVerknuepfenJetzt}
                        Über „Verknüpfen“ lassen sich Beziehungen zu anderen Bausteinen
                        anlegen — etwa zu verwandten Begriffen oder zum Themengebiet.
                    {:else}
                        Verknüpfungen entstehen beim Import, im Curriculum-Editor und über
                        den Verknüpfen-Dialog der zuständigen Fachschaft.
                    {/if}
                </p>
            {:else}
                <!-- Mehrspaltig, sobald Platz ist: Die Gruppen sind kurz und stehen
                     sonst als schmale Säule untereinander. Grid statt CSS-Spalten,
                     damit keine Gruppe über den Spaltenumbruch zerrissen wird. -->
                <div class="grid gap-x-8 gap-y-4 md:grid-cols-2 2xl:grid-cols-3">
                    {#each gruppen as gruppe (gruppe.schluessel)}
                        <div class="min-w-0">
                            <p
                                class="text-xs uppercase tracking-wide font-medium
                                       text-light-tx-2 dark:text-dark-tx-2 mb-1"
                            >
                                {gruppe.label} · {gruppe.gesamt}
                            </p>

                            {#if gruppe.nurZahl}
                                <!-- Zu viele für eine Liste: Zwanzig Titel aus 940 wären
                                     eine willkürliche Stichprobe, die nach Auswahl
                                     aussieht. -->
                                <a
                                    href={graphUrl}
                                    class="text-sm text-light-bl dark:text-dark-bl hover:underline"
                                >
                                    {gruppe.gesamt} Bausteine — in der Graphansicht
                                </a>
                            {:else}
                                <ul class="space-y-0.5">
                                    {#each gruppe.sichtbar as eintrag (eintrag.kante.id)}
                                        <li class="flex items-center gap-1.5 text-sm min-w-0">
                                            <NodeTypeIcon
                                                category={eintrag.gegen.category}
                                                contentType={eintrag.gegen.content_type}
                                                size={16}
                                            />
                                            <a
                                                href="/knowledge/{eintrag.gegen.id}"
                                                title={eintrag.kante.metadata
                                                    ?.hinweis ?? eintrag.gegen.title}
                                                class="text-light-tx dark:text-dark-tx
                                                       hover:underline truncate"
                                            >
                                                {eintrag.gegen.title}
                                            </a>
                                            {#if istStub(eintrag.gegen)}
                                                <span
                                                    title="Angelegt, aber noch ohne Inhalt"
                                                    class="shrink-0 text-xs px-1.5 py-0.5
                                                           rounded-full border
                                                           border-light-ui-3 dark:border-dark-ui-3
                                                           text-light-tx-2 dark:text-dark-tx-2"
                                                    >unvollständig</span
                                                >
                                            {/if}
                                            {#if canEdit && eintrag.raus}
                                                <button
                                                    onclick={() => entferneKante(eintrag.kante.id)}
                                                    title="Verknüpfung entfernen — der Baustein bleibt"
                                                    class="shrink-0 text-xs text-light-tx-3
                                                           dark:text-dark-tx-3
                                                           hover:text-light-re dark:hover:text-dark-re"
                                                >
                                                    ×
                                                </button>
                                            {/if}
                                        </li>
                                    {/each}
                                </ul>
                                {#if gruppe.weitere > 0}
                                    <a
                                        href={graphUrl}
                                        class="text-xs text-light-bl dark:text-dark-bl hover:underline"
                                    >
                                        + {gruppe.weitere} weitere
                                    </a>
                                {/if}
                            {/if}
                        </div>
                    {/each}
                </div>
            {/if}
        </section>

        <!-- Metadaten: einklappbar. Sie beantworten Rückfragen (Wer darf das sehen?
             Bis wann gilt es?), sind aber nicht der Grund, warum jemand die Seite
             öffnet — deshalb hinter einem Griff statt über dem Inhalt. -->
        <details class="mb-6 group">
            <summary
                class="cursor-pointer text-sm font-semibold text-light-tx dark:text-dark-tx
                       mb-2 select-none"
            >
                Eigenschaften
            </summary>
            <dl
                class="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm
                       border border-light-ui-3 dark:border-dark-ui-3 rounded-lg p-4
                       bg-light-bg-2 dark:bg-dark-bg-2"
            >
                <dt class="text-light-tx-2 dark:text-dark-tx-2">Fach</dt>
                <dd class="text-light-tx dark:text-dark-tx">
                    {subjectName ?? "fächerübergreifend"}
                </dd>

                <dt class="text-light-tx-2 dark:text-dark-tx-2">Jahrgangsstufe</dt>
                <dd class="text-light-tx dark:text-dark-tx">
                    {#if node.min_grade && node.max_grade}
                        Klasse {node.min_grade}–{node.max_grade}
                    {:else if node.min_grade}
                        ab Klasse {node.min_grade}
                    {:else if node.max_grade}
                        bis Klasse {node.max_grade}
                    {:else}
                        alle Jahrgangsstufen
                    {/if}
                </dd>

                <dt class="text-light-tx-2 dark:text-dark-tx-2">Sichtbarkeit</dt>
                <dd class="text-light-tx dark:text-dark-tx">
                    {SCOPE_LABELS[node.read_scope] ?? node.read_scope}
                </dd>

                {#if node.schuljahr}
                    <dt class="text-light-tx-2 dark:text-dark-tx-2">Schuljahr</dt>
                    <dd class="text-light-tx dark:text-dark-tx">{node.schuljahr}</dd>
                {/if}

                {#if node.valid_until}
                    <dt class="text-light-tx-2 dark:text-dark-tx-2">Gültig bis</dt>
                    <dd class="text-light-tx dark:text-dark-tx">
                        {formatDate(node.valid_until)}
                    </dd>
                {/if}

                <!-- Die typeigenen Felder aus dem Schema (Prüfstatus, Herkunft,
                     Alltagsnamen, Nachweis …). Bis 09/2026 waren sie nur im Editor zu
                     sehen — also für alle, die nicht bearbeiten dürfen, gar nicht. -->
                {#each schemaFelder as [label, wert] (label)}
                    <dt class="text-light-tx-2 dark:text-dark-tx-2">{label}</dt>
                    <dd class="text-light-tx dark:text-dark-tx">
                        {@html renderInlineMath(wert)}
                    </dd>
                {/each}
            </dl>
        </details>

        <!-- Zeitstempel als Fußzeile: nützlich, aber nie der Grund für den Besuch. -->
        <p
            class="text-xs text-light-tx-3 dark:text-dark-tx-3 pt-4 mt-6
                   border-t border-light-ui-3 dark:border-dark-ui-3"
        >
            Erstellt: {formatDate(node.created_at)}
            {#if node.updated_at !== node.created_at}
                · Aktualisiert: {formatDate(node.updated_at)}
            {/if}
        </p>
    {:else}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Knoten nicht gefunden.
        </p>
    {/if}
</PageBody>
