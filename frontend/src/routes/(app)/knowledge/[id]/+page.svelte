<script>
    import { page } from "$app/stores";
    import { goto } from "$app/navigation";
    import { CATEGORY_LABELS, CONTENT_TYPE_LABELS } from "$lib/taxonomy.js";
    import { getContextNode, getArchivedReferences } from "$lib/api.js";
    import { renderMarkdown } from "$lib/markdown.js";
    import { renderDiagrams } from "$lib/diagrams.js";
    import { renderServerBlocks } from "$lib/serverRender.js";
    import { user } from "$lib/stores/user.js";
    import { subjectMap } from "$lib/stores/subjects.js";
    import { ArrowLeft, Pencil } from "lucide-svelte";
    import WarningBanner from "$lib/components/WarningBanner.svelte";

    let node = $state(null);
    let loadingNode = $state(true);
    let error = $state(null);
    let archivedRefs = $state([]);

    const backUrl = $derived(
        $page.url.searchParams.get("back") ?? "/knowledge",
    );

    // Bearbeiten-Link trägt den back-Parameter weiter, damit die Edit-Seite
    // wieder hierher (und von hier zurück zur Ausgangsliste) navigieren kann.
    const editUrl = $derived(
        `/knowledge/${$page.params.id}/edit` +
            ($page.url.searchParams.get("back")
                ? `?back=${encodeURIComponent($page.url.searchParams.get("back"))}`
                : ""),
    );

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

<div class="h-full overflow-y-auto p-6 max-w-2xl">
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
            <div class="min-w-0">
                <div class="flex items-center gap-3 flex-wrap">
                    <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
                        {node.title}
                    </h1>
                    <span
                        class="text-xs px-2 py-0.5 rounded-full
                        {node.status === 'active'
                            ? 'bg-light-gr/20 dark:bg-dark-gr/20 text-light-gr dark:text-dark-gr'
                            : 'bg-light-ye/20 dark:bg-dark-ye/20 text-light-ye dark:text-dark-ye'}"
                    >
                        {node.status === "active" ? "Aktiv" : "Archiviert"}
                    </span>
                </div>
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    {CATEGORY_LABELS[node.category] ?? node.category}
                    {#if node.content_type}
                        · {CONTENT_TYPE_LABELS[node.content_type] ??
                            node.content_type}
                    {/if}
                </p>
            </div>
            {#if canEdit}
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

        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-1">
            Erstellt: {formatDate(node.created_at)}
            {#if node.updated_at !== node.created_at}
                · Aktualisiert: {formatDate(node.updated_at)}
            {/if}
        </p>
        <a
            href="/knowledge/{$page.params.id}/graph"
            class="text-sm text-primary dark:text-dark-bl underline mb-4 inline-block"
        >
            Graphansicht öffnen →
        </a>

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

        <!-- Metadaten -->
        <dl
            class="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm mb-6
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

        <!-- Inhalt -->
        {#if contentHtml}
            <div
                class="prose dark:prose-invert max-w-none
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
    {:else}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Knoten nicht gefunden.
        </p>
    {/if}
</div>
