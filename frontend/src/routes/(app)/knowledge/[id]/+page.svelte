<script>
    import { untrack } from "svelte";
    import { getNeighborhood, deleteContextEdge } from "$lib/api.js";
    import { kannVerknuepfen, istStub } from "$lib/collections.js";
    import VerknuepfenDialog from "$lib/components/VerknuepfenDialog.svelte";

    /** Die Kantenarten in der Sprache der Sache statt als Relationsname. */
    const RELATION_LABEL = {
        related_to: "Steht in Beziehung zu",
        part_of: "Gehört zu",
        references: "Verweist auf",
        develops: "Entwickelt",
        requires: "Setzt voraus",
        used_with: "Wird verwendet mit",
        supersedes: "Löst ab",
        follows: "Folgt auf",
        derived_from: "Abgeleitet aus",
        reflects_on: "Reflektiert",
    };

    import { sammlung } from "$lib/collections.js";
    import { page } from "$app/stores";
    import { goto } from "$app/navigation";
    import { CATEGORY_LABELS, CONTENT_TYPE_LABELS } from "$lib/taxonomy.js";
    import { getContextNode, getArchivedReferences, updateNodeTitle } from "$lib/api.js";
    import { renderInlineMath, renderMarkdown } from "$lib/markdown.js";
    import { renderDiagrams } from "$lib/diagrams.js";
    import { renderServerBlocks } from "$lib/serverRender.js";
    import { user } from "$lib/stores/user.js";
    import { subjectMap } from "$lib/stores/subjects.js";
    import { ArrowLeft, Pencil, Check, X } from "lucide-svelte";
    import WarningBanner from "$lib/components/WarningBanner.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";

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

    // Bearbeiten-Link trägt den back-Parameter weiter, damit die Edit-Seite
    // wieder hierher (und von hier zurück zur Ausgangsliste) navigieren kann.
    //
    // Gehört der Knoten zu einer Sammlung, führt er in **deren** Editor: Der baut sein
    // Formular aus dem Feldschema, während der allgemeine Editor `metadata` als rohes
    // JSON zeigt. Wer aus der Sammlung kommt, bekäme sonst zwei verschiedene Masken für
    // denselben Baustein.
    const editUrl = $derived.by(() => {
        const rueckweg = $page.url.searchParams.get("back");
        const query = rueckweg ? `?back=${encodeURIComponent(rueckweg)}` : "";
        return sammlung(node?.content_type)
            ? `/knowledge/collections/${node.content_type}/${$page.params.id}/edit${query}`
            : `/knowledge/${$page.params.id}/edit${query}`;
    });

    // ── Nachbarschaft (UI-Notiz A3) ──────────────────────────────────────────
    //
    // Ego-Graph der Tiefe 1, nach Relationstyp gruppiert. Die Leitplanke aus ADR-013
    // gilt: nie „alle Kanten" auf einmal — ab `KAPPUNG` Nachbarn je Relationstyp steht
    // „+ n weitere" und der Weg in die große Ansicht.
    const KAPPUNG = 20;

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

    /**
     * Die Kanten nach Relationstyp gruppieren — mit Richtung und Gegenknoten.
     *
     * Der Sichtbarkeitsfilter greift dabei von selbst: Die Nachbarschaft liefert nur
     * lesbare Knoten. Eine Kante, deren Gegenstück fehlt, wird deshalb ausgelassen —
     * nicht anonymisiert angedeutet.
     */
    const gruppen = $derived.by(() => {
        if (!nachbarschaft || !node) return [];
        const knoten = Object.fromEntries(
            (nachbarschaft.nodes ?? []).map((n) => [n.id, n]),
        );
        const nach = {};
        for (const kante of nachbarschaft.edges ?? []) {
            // ⚠️ Die Nachbarschaft liefert **alle** Kanten zwischen den sichtbaren
            // Knoten — auch solche, die zwei Nachbarn untereinander verbinden und diesen
            // Knoten gar nicht berühren. Ohne diese Prüfung stünden sie in der Liste, als
            // gingen sie von hier aus. Eine Liste kann sie nicht sinnvoll zeigen; ein
            // Graph könnte es (siehe Todo zur Graph-Vorschau).
            const raus = kante.from_node_id === node.id;
            const rein = kante.to_node_id === node.id;
            if (!raus && !rein) continue;
            const gegen = knoten[raus ? kante.to_node_id : kante.from_node_id];
            if (!gegen || gegen.id === node.id) continue;
            (nach[kante.relation] ??= []).push({ kante, gegen, raus });
        }
        return Object.entries(nach)
            .map(([relation, eintraege]) => ({
                relation,
                label: RELATION_LABEL[relation] ?? relation,
                gesamt: eintraege.length,
                sichtbar: eintraege.slice(0, KAPPUNG),
                weitere: Math.max(0, eintraege.length - KAPPUNG),
            }))
            .sort((a, b) => b.gesamt - a.gesamt);
    });

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

    const isStructured = $derived(
        node?.content_type === "funktion" || node?.content_type === "bauteil",
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

<!-- Breite wie bei den Geschwisterseiten (Suche, Archiv): `max-w-2xl` war schmaler als
     jede Liste und ließ die Seite gedrängt wirken. Der **Fließtext** bleibt trotzdem
     schmal — dafür sorgt unten die Vorgabe des Typografie-Plugins (65 Zeichen), denn
     eine Definition über die volle Breite zu lesen ist mühsamer, nicht leichter. -->
<div class="h-full overflow-y-auto p-6 max-w-4xl">
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
                </p>
            </div>
            {#if canEdit && !isImported}
                <a
                    href={editUrl}
                    class="shrink-0 flex items-center gap-1.5 px-4 py-2 text-sm rounded-md
                           bg-primary dark:bg-primary-dark text-white font-medium
                           hover:opacity-90 transition-opacity"
                >
                    <Pencil class="w-4 h-4" /> Bearbeiten
                </a>
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

        <!-- Inhalt -->
        {#if contentHtml}
            <div
                class="prose dark:prose-invert
                       prose-p:text-light-tx dark:prose-p:text-dark-tx
                       prose-headings:text-light-tx dark:prose-headings:text-dark-tx
                       prose-strong:text-light-tx dark:prose-strong:text-dark-tx
                       prose-li:text-light-tx dark:prose-li:text-dark-tx
                       prose-a:text-light-bl dark:prose-a:text-dark-bl"
                use:renderDiagrams use:renderServerBlocks
            >
                {@html contentHtml}
            </div>
        {:else}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 italic">
                Kein Inhalt hinterlegt.
            </p>
        {/if}

        <!-- Hinweis für strukturierte Typen (MVP: Details im Bearbeiten-Modus) -->
        {#if isStructured}
            <p class="mt-4 text-sm text-light-tx-2 dark:text-dark-tx-2">
                Strukturierte Details ({node.content_type === "funktion"
                    ? "Funktionssignatur"
                    : "Schaltzeichen"}) sind im Bearbeiten-Modus sichtbar.
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
                        Große Graphansicht →
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
                <div class="space-y-3">
                    {#each gruppen as gruppe (gruppe.relation)}
                        <div>
                            <p
                                class="text-xs uppercase tracking-wide text-light-tx-3
                                       dark:text-dark-tx-3 mb-1"
                            >
                                {gruppe.label} · {gruppe.gesamt}
                            </p>
                            <ul class="space-y-0.5">
                                {#each gruppe.sichtbar as eintrag (eintrag.kante.id)}
                                    <li class="flex items-center gap-2 text-sm">
                                        {#if !eintrag.raus}
                                            <span
                                                title="Verweist auf diesen Baustein"
                                                class="text-light-tx-3 dark:text-dark-tx-3"
                                                >←</span
                                            >
                                        {/if}
                                        <a
                                            href="/knowledge/{eintrag.gegen.id}"
                                            class="text-light-tx dark:text-dark-tx hover:underline"
                                        >
                                            {eintrag.gegen.title}
                                        </a>
                                        {#if istStub(eintrag.gegen)}
                                            <span
                                                title="Angelegt, aber noch ohne Inhalt"
                                                class="text-xs px-1.5 py-0.5 rounded-full
                                                       border border-light-ui-3
                                                       dark:border-dark-ui-3
                                                       text-light-tx-2 dark:text-dark-tx-2"
                                                >unvollständig</span
                                            >
                                        {/if}
                                        {#if canEdit && eintrag.raus}
                                            <button
                                                onclick={() => entferneKante(eintrag.kante.id)}
                                                title="Verknüpfung entfernen — der Baustein bleibt"
                                                class="text-xs text-light-tx-3 dark:text-dark-tx-3
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
</div>
