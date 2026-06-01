<script>
    import { goto } from "$app/navigation";
    import {
        CONTENT_TYPES,
        CATEGORY_LABELS,
        CONTENT_TYPE_LABELS,
        SCOPE_ANCHOR_CONTENT_TYPES,
    } from "$lib/taxonomy.js";
    import { getContextNodes, updateContextNode } from "$lib/api.js";
    import { subjects } from "$lib/stores/subjects.js";
    import NodeTypeIcon from "./NodeTypeIcon.svelte";
    import { Anchor } from "lucide-svelte";

    let {
        fixedSubjectSlug = null, // gesetzt im Subject-Kontext-Tab
        fixedGroupId = null, // gesetzt im Gruppen-Kontext-Tab
        showSubjectFilter = true, // false in Subject/Gruppen-Tabs
        showNewButton = true,
        onNodeClick = null, // optional: callback statt goto
        initialGrade = null, // voreingestellte Jahrgangsstufe
    } = $props();

    let nodes = $state([]);
    let loading = $state(false);
    let error = $state(null);

    // Filter-State
    let q = $state("");
    let selectedSubjectSlug = $state("");
    let selectedCategory = $state("");
    let selectedContentType = $state("");
    let selectedStatus = $state("active");
    let onlyEntryNodes = $state(false);
    let selectedGrade = $state(initialGrade);

    // Sortierung
    let sortCol = $state('subject_id'); // Default: Fach-Knoten vor Leitperspektiven
    let sortDir = $state('asc');

    const sortedNodes = $derived.by(() => {
        const arr = [...nodes];
        arr.sort((a, b) => {
            let av, bv;
            if (sortCol === 'subject_id') {
                // null (Leitperspektiven) immer ans Ende, unabhängig von sortDir
                if (a.subject_id == null && b.subject_id != null) return 1;
                if (a.subject_id != null && b.subject_id == null) return -1;
                av = a.title ?? '';
                bv = b.title ?? '';
            } else if (sortCol === 'title') {
                av = a.title ?? '';
                bv = b.title ?? '';
            } else if (sortCol === 'content_type') {
                av = (CATEGORY_LABELS[a.category] ?? a.category) + (a.content_type ?? '');
                bv = (CATEGORY_LABELS[b.category] ?? b.category) + (b.content_type ?? '');
            } else if (sortCol === 'updated_at') {
                av = a.updated_at ?? '';
                bv = b.updated_at ?? '';
            } else {
                av = a[sortCol] ?? '';
                bv = b[sortCol] ?? '';
            }
            const cmp = av < bv ? -1 : av > bv ? 1 : 0;
            return sortDir === 'asc' ? cmp : -cmp;
        });
        return arr;
    });

    function toggleSort(col) {
        if (sortCol === col) {
            sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        } else {
            sortCol = col;
            sortDir = 'asc';
        }
    }

    // Debounce-Timer für Suchfeld
    let searchTimer = null;

    const contentTypeOptions = $derived(
        selectedCategory ? (CONTENT_TYPES[selectedCategory] ?? []) : [],
    );

    async function load() {
        loading = true;
        error = null;
        try {
            const params = {
                status: selectedStatus || "active",
            };
            if (q.trim().length >= 2) params.q = q.trim();
            if (fixedSubjectSlug) params.subject_slug = fixedSubjectSlug;
            else if (selectedSubjectSlug) params.subject_slug = selectedSubjectSlug;
            if (fixedGroupId) params.group_id = fixedGroupId;
            if (selectedGrade) params.grade = Number(selectedGrade);
            if (onlyEntryNodes) {
                params.content_type = [...SCOPE_ANCHOR_CONTENT_TYPES];
            } else {
                if (selectedCategory) params.category = selectedCategory;
                if (selectedContentType)
                    params.content_type = selectedContentType;
            }
            nodes = await getContextNodes(params);
        } catch (e) {
            error = e.message;
        } finally {
            loading = false;
        }
    }

    $effect(() => {
        // Reaktiv auf alle Filter (fixedSubjectSlug/fixedGroupId sind stabil)
        selectedSubjectSlug;
        selectedCategory;
        selectedContentType;
        selectedStatus;
        onlyEntryNodes;
        selectedGrade;
        fixedSubjectSlug;
        fixedGroupId;
        load();
    });

    function onSearchInput(e) {
        q = e.target.value;
        clearTimeout(searchTimer);
        searchTimer = setTimeout(load, 300);
    }

    async function archiveNode(node) {
        await updateContextNode(node.id, { status: "archived" });
        nodes = nodes.filter((n) => n.id !== node.id);
    }
</script>

<!-- Filterleiste -->
<div class="flex flex-wrap gap-2 mb-4 items-center">
    <!-- Suchfeld -->
    <input
        type="search"
        placeholder="Titel suchen…"
        value={q}
        oninput={onSearchInput}
        class="flex-1 min-w-48 px-3 py-1.5 text-sm rounded-md border
           border-light-ui-3 dark:border-dark-ui-3
           bg-light-bg dark:bg-dark-bg
           text-light-tx dark:text-dark-tx
           focus:outline-none focus:border-primary dark:focus:border-primary-dark"
    />

    <!-- Fach-Filter (nur im globalen /knowledge-Kontext) -->
    {#if showSubjectFilter && $subjects.length > 0}
        <select
            bind:value={selectedSubjectSlug}
            class="px-3 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
        >
            <option value="">Alle Fächer</option>
            {#each $subjects as subject}
                <option value={subject.slug}>{subject.name}</option>
            {/each}
        </select>
    {/if}

    <!-- Toggle: Nur Einstiegsknoten -->
    <button
        onclick={() => {
            onlyEntryNodes = !onlyEntryNodes;
            selectedCategory = "";
            selectedContentType = "";
        }}
        class="px-3 py-1.5 text-sm rounded-md border transition-colors
           {onlyEntryNodes
            ? 'bg-primary/10 dark:bg-primary-dark/10 border-primary dark:border-primary-dark text-primary dark:text-primary-dark font-medium'
            : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 hover:border-primary dark:hover:border-primary-dark'}"
    >
        ⚓ Einstiegsknoten
    </button>

    <!-- Category-Filter (nur wenn nicht onlyEntryNodes) -->
    {#if !onlyEntryNodes}
        <select
            bind:value={selectedCategory}
            onchange={() => {
                selectedContentType = "";
            }}
            class="px-3 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
             bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
        >
            <option value="">Alle Typen</option>
            {#each Object.keys(CONTENT_TYPES) as cat}
                <option value={cat}>{CATEGORY_LABELS[cat]}</option>
            {/each}
        </select>

        {#if contentTypeOptions.length > 0}
            <select
                bind:value={selectedContentType}
                class="px-3 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
            >
                <option value="">Alle Untertypen</option>
                {#each contentTypeOptions as ct}
                    <option value={ct}>{ct}</option>
                {/each}
            </select>
        {/if}
    {/if}

    <!-- Status-Filter -->
    <select
        bind:value={selectedStatus}
        class="px-3 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
           bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
    >
        <option value="active">Aktiv</option>
        <option value="archived">Archiviert</option>
    </select>

    <!-- Jahrgangsstufe -->
    <select
        bind:value={selectedGrade}
        class="px-3 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
           bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
    >
        <option value={null}>Alle Jahrgangsstufen</option>
        {#each Array.from({ length: 13 }, (_, i) => i + 1) as g}
            <option value={g}>Klasse {g}</option>
        {/each}
    </select>

    <!-- Neuer-Knoten-Button -->
    {#if showNewButton}
        {@const newUrl = fixedGroupId
            ? `/knowledge/new?group_id=${fixedGroupId}&read_scope=group`
            : fixedSubjectSlug
              ? `/knowledge/new?subject_slug=${fixedSubjectSlug}&read_scope=school`
              : "/knowledge/new"}
        <a
            href={newUrl}
            class="ml-auto px-3 py-1.5 text-sm rounded-md bg-primary dark:bg-primary-dark
             text-white font-medium hover:opacity-90 transition-opacity whitespace-nowrap"
        >
            + Neuer Knoten
        </a>
    {/if}
</div>

<!-- Tabelle -->
{#if loading}
    <div class="py-8 text-center text-sm text-light-tx-2 dark:text-dark-tx-2">
        Wird geladen…
    </div>
{:else if error}
    <div class="py-4 text-sm text-light-re dark:text-dark-re">{error}</div>
{:else if nodes.length === 0}
    <div class="py-8 text-center text-sm text-light-tx-2 dark:text-dark-tx-2">
        Keine Knoten gefunden.
        {#if showNewButton}
            <a
                href="/knowledge/new"
                class="ml-1 text-primary dark:text-dark-bl underline"
                >Ersten Knoten anlegen</a
            >
        {/if}
    </div>
{:else}
    <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse text-sm">
            <thead>
                <tr class="border-b border-light-ui-3 dark:border-dark-ui-3">
                    {#each [
                        { col: 'title',        label: 'Titel'       },
                        { col: 'content_type', label: 'Typ'         },
                        { col: 'updated_at',   label: 'Aktualisiert'},
                    ] as h (h.col)}
                        <th class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2">
                            <button
                                onclick={() => toggleSort(h.col)}
                                class="flex items-center gap-1 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
                            >
                                {h.label}
                                <span class="text-xs opacity-50">
                                    {#if sortCol === h.col}
                                        {sortDir === 'asc' ? '▲' : '▼'}
                                    {:else}
                                        ⇅
                                    {/if}
                                </span>
                            </button>
                        </th>
                    {/each}
                    <th class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2">Sichtbarkeit</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                {#each sortedNodes as node (node.id)}
                    <tr
                        class="border-b border-light-ui-3 dark:border-dark-ui-3
                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors cursor-pointer"
                        onclick={() =>
                            onNodeClick
                                ? onNodeClick(node)
                                : goto(`/knowledge/${node.id}`)}
                    >
                        <!-- Titel mit Icon -->
                        <td
                            class="px-3 py-2 text-light-tx dark:text-dark-tx font-medium"
                        >
                            <div class="flex items-center gap-2">
                                <NodeTypeIcon
                                    category={node.category}
                                    contentType={node.content_type}
                                    size={16}
                                />
                                {#if SCOPE_ANCHOR_CONTENT_TYPES.has(node.content_type)}
                                    <Anchor name="anchor" size={16} />
                                {/if}
                                {node.title}
                            </div>
                        </td>
                        <!-- category / content_type -->
                        <td
                            class="px-3 py-2 text-light-tx-2 dark:text-dark-tx-2 whitespace-nowrap"
                        >
                            {CATEGORY_LABELS[node.category] ?? node.category}
                            {#if node.content_type}
                                <span class="opacity-60">
                                    / {CONTENT_TYPE_LABELS[node.content_type] ?? node.content_type}</span
                                >
                            {/if}
                        </td>
                        <!-- Datum -->
                        <td
                            class="px-3 py-2 text-light-tx-3 dark:text-dark-tx-3 whitespace-nowrap text-xs"
                        >
                            {new Date(node.updated_at).toLocaleDateString(
                                "de-DE",
                                {
                                    day: "2-digit",
                                    month: "2-digit",
                                    year: "numeric",
                                },
                            )}
                        </td>
                        <!-- read_scope Badge -->
                        <td class="px-3 py-2">
                            <span
                                class="text-xs px-2 py-0.5 rounded-full bg-light-ui-2 dark:bg-dark-ui-2
                           text-light-tx-2 dark:text-dark-tx-2"
                            >
                                {node.read_scope}
                            </span>
                        </td>
                        <!-- Aktionen -->
                        <td
                            class="px-3 py-2"
                            onclick={(e) => e.stopPropagation()}
                        >
                            {#if node.status === "active"}
                                <button
                                    onclick={() => archiveNode(node)}
                                    title="Archivieren"
                                    class="text-xs text-light-tx-2 dark:text-dark-tx-2
                         hover:text-light-re dark:hover:text-dark-re transition-colors"
                                >
                                    Archivieren
                                </button>
                            {:else}
                                <span
                                    class="text-xs text-light-tx-3 dark:text-dark-tx-3 italic"
                                    >archiviert</span
                                >
                            {/if}
                        </td>
                    </tr>
                {/each}
            </tbody>
        </table>
    </div>
{/if}
