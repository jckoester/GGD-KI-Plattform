<script>
    import { page } from "$app/stores";
    import { goto } from "$app/navigation";
    import {
        getCurriculum,
        updateContextNode,
        createContextNode,
        deleteContextNode,
        createEdge,
        deleteEdge,
        getNodeEdges,
    } from "$lib/api.js";
    import { kapitelStd, curriculumStd } from "$lib/curriculum.js";
    import { extractNodeTargets } from "$lib/material.js";
    import { user } from "$lib/stores/user.js";
    import CurriculumTable from "$lib/components/CurriculumTable.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import { ArrowLeft } from "lucide-svelte";

    let curriculum = $state(null);
    let draft = $state(null);
    let dirty = $state(false);
    let loading = $state(true);
    let saving = $state(false);
    let saveError = $state(null);
    let saveSuccess = $state(false);
    let canEdit = $state(false);
    const totalStd = $derived(curriculumStd(draft));

    // Repräsentative Jahrgangsstufe (Int) aus der jahrgangsstufe-Angabe des
    // Curriculums (kann ein Band sein, z. B. "8/9/10" oder "8-10"). Wird für die
    // editionsbewusste IK/PK-Auflösung und den Stufenfilter der Suche gebraucht —
    // die Endpunkte erwarten eine Ganzzahl, kein Band-String.
    const gradeInt = $derived.by(() => {
        const m = String(curriculum?.metadata?.jahrgangsstufe ?? "").match(/\d+/);
        return m ? Number(m[0]) : null;
    });

    // Sticky-Footer: nur sichtbar, wenn die oberen Aktionen aus dem Scrollbereich sind
    let scrollEl = $state(null);
    let topActionsEl = $state(null);
    let showStickyFooter = $state(false);

    $effect(() => {
        if (!scrollEl || !topActionsEl) return;
        const obs = new IntersectionObserver(
            ([entry]) => {
                showStickyFooter = !entry.isIntersecting;
            },
            { root: scrollEl, threshold: 0 },
        );
        obs.observe(topActionsEl);
        return () => obs.disconnect();
    });

    // Lade Curriculum und prüfe Berechtigungen.
    // Der Effekt selbst ist synchron (liest $page.params.id als Dependency,
    // damit er bei Routenwechsel erneut läuft); die async-Arbeit passiert in
    // einer inneren Funktion. Ein cancelled-Flag verwirft veraltete Antworten,
    // falls die ID wechselt, bevor der Request zurückkommt.
    $effect(() => {
        const id = $page.params.id;
        let cancelled = false;

        loading = true;
        (async () => {
            try {
                const data = await getCurriculum(id);
                if (cancelled) return;
                curriculum = data;
                // Prüfe ob User editieren darf
                if (!data?.can_edit) {
                    // Weiterleitung zur Read-only-Ansicht
                    goto(`/knowledge/curriculum/${id}`, { replaceState: true });
                    return;
                }
                canEdit = true;
                draft = $state.snapshot(curriculum);
            } catch (e) {
                if (!cancelled) saveError = e.message;
            } finally {
                if (!cancelled) loading = false;
            }
        })();

        return () => {
            cancelled = true;
        };
    });

    // Speichern-Funktion
    async function save() {
        if (!dirty || saving) return;

        saving = true;
        saveError = null;
        saveSuccess = false;

        try {
            await flushDraftToApi(draft, curriculum);
            // Aktualisiere Original nach dem Speichern
            curriculum = await getCurriculum($page.params.id);
            draft = $state.snapshot(curriculum);
            dirty = false;
            saveSuccess = true;
            setTimeout(() => {
                saveSuccess = false;
            }, 3000);
        } catch (e) {
            saveError = e.message;
        } finally {
            saving = false;
        }
    }

    // Speicher-Logik: Vergleicht draft mit original und führt API-Calls aus
    async function flushDraftToApi(draft, original) {
        // 1. Curriculum-Knoten selbst aktualisieren
        if (
            draft.title !== original.title ||
            JSON.stringify(draft.metadata) !== JSON.stringify(original.metadata)
        ) {
            await updateContextNode(draft.id, {
                title: draft.title,
                metadata: draft.metadata,
            });
        }

        // 2. Kapitel verarbeiten
        const origKapMap = new Map(
            original.kapitel?.map((k) => [k.id, k]) || [],
        );
        const draftKapMap = new Map(draft.kapitel?.map((k) => [k.id, k]) || []);

        // Gelöschte Kapitel
        for (const origKap of original.kapitel || []) {
            if (!draftKapMap.has(origKap.id)) {
                // Kapitel und alle untergeordneten Knoten löschen (cascading)
                await deleteContextNode(origKap.id);
            }
        }

        // Neue oder aktualisierte Kapitel
        for (const draftKap of draft.kapitel || []) {
            // Kapitel-Stundenzahl = Summe der Lernsequenz-Stunden (abgeleitet, nie manuell)
            draftKap.metadata = {
                ...draftKap.metadata,
                std: kapitelStd(draftKap),
            };

            const origKap = origKapMap.get(draftKap.id);

            if (!origKap) {
                // Neues Kapitel erstellen
                const newKap = await createContextNode({
                    category: "knowledge",
                    content_type: "kapitel",
                    title: draftKap.title,
                    content: draftKap.metadata?.einleitung || "",
                    read_scope: "school",
                    write_scope: "subject",
                    write_scope_group_id: original.write_scope_group_id,
                    subject_id: original.subject_id,
                    metadata: {
                        std: draftKap.metadata?.std || "",
                        reihenfolge: draftKap.metadata?.reihenfolge || 0,
                        einleitung: draftKap.metadata?.einleitung || "",
                        breadcrumb: draftKap.metadata?.breadcrumb || "",
                    },
                });
                draftKap.id = newKap.id;
                draftKap.metadata.import_key = `temp_${newKap.id}`;

                // part_of-Kante zum Curriculum
                await createEdge({
                    from_node_id: newKap.id,
                    to_node_id: draft.id,
                    relation: "part_of",
                    metadata: {},
                });
            } else if (
                draftKap.title !== origKap.title ||
                JSON.stringify(draftKap.metadata) !==
                    JSON.stringify(origKap.metadata)
            ) {
                // Kapitel aktualisieren
                await updateContextNode(draftKap.id, {
                    title: draftKap.title,
                    content: draftKap.metadata?.einleitung || "",
                    metadata: draftKap.metadata,
                });
            }

            // Lernsequenzen im Kapitel verarbeiten
            const origLsMap = new Map(
                origKap?.lernsequenzen?.map((ls) => [ls.id, ls]) || [],
            );
            const draftLsMap = new Map(
                draftKap.lernsequenzen?.map((ls) => [ls.id, ls]) || [],
            );

            // Gelöschte Lernsequenzen
            for (const origLs of origKap?.lernsequenzen || []) {
                if (!draftLsMap.has(origLs.id)) {
                    await deleteContextNode(origLs.id);
                }
            }

            // Neue oder aktualisierte Lernsequenzen
            for (const draftLs of draftKap.lernsequenzen || []) {
                const origLs = origLsMap.get(draftLs.id);

                if (!origLs) {
                    // Neue Lernsequenz erstellen
                    const newLs = await createContextNode({
                        category: "knowledge",
                        content_type: "lernsequenz",
                        title: draftLs.title || "",
                        content: null,
                        read_scope: "school",
                        write_scope: "subject",
                        write_scope_group_id: original.write_scope_group_id,
                        subject_id: original.subject_id,
                        metadata: {
                            bp_leitidee: draftLs.metadata?.bp_leitidee || "",
                            reihenfolge: draftLs.metadata?.reihenfolge || 0,
                            std: draftLs.metadata?.std ?? 0,
                            eintraege: draftLs.metadata?.eintraege || [],
                        },
                    });
                    draftLs.id = newLs.id;
                    draftLs.metadata.import_key = `temp_${newLs.id}`;

                    // part_of-Kante zum Kapitel
                    await createEdge({
                        from_node_id: newLs.id,
                        to_node_id: draftKap.id,
                        relation: "part_of",
                        metadata: {},
                    });
                } else if (
                    draftLs.title !== origLs.title ||
                    JSON.stringify(draftLs.metadata) !==
                        JSON.stringify(origLs.metadata)
                ) {
                    // Lernsequenz aktualisieren
                    await updateContextNode(draftLs.id, {
                        title: draftLs.title || "",
                        metadata: draftLs.metadata,
                    });
                }

                // Kanten für IK/PK/Leitperspektiven aktualisieren
                await updateEdgesForLernsequenz(
                    draftLs,
                    origLs || {
                        id: null,
                        ik_refs: [],
                        pk_refs: [],
                        leitperspektive_refs: [],
                    },
                );
            }
        }
    }

    // Leitet IK/PK/LP-Refs aus den Einträgen einer Lernsequenz ab.
    // eintrag.ik: Array<{node_id, nr, partiell}> (neues Format nach E.1.b)
    // eintrag.pk: Array<{node_id, pk_id}>
    // eintrag.hinweise: Text mit @[Label](lp:uuid) und #[Label](ik:uuid) Tokens
    function deriveRefsFromEntries(eintraege) {
        const ikMap = new Map(); // node_id → {node_id, partiell}
        const pkSet = new Set(); // node_id
        const lpSet = new Set(); // node_id (Leitperspektive aus hinweise)
        const crossIkSet = new Set(); // node_id (Cross-Fach-IK aus hinweise)
        const usedWithSet = new Set(); // node_id (Knoten aus material)

        for (const eintrag of eintraege || []) {
            // IK-Array (neues Format: Array<{node_id, nr, partiell}>)
            const ikArray = Array.isArray(eintrag.ik) ? eintrag.ik : [];
            for (const ik of ikArray) {
                if (!ik.node_id) continue;
                const existing = ikMap.get(ik.node_id);
                // "partiell=false" gewinnt über "partiell=true" (volle Referenz schlägt partielle)
                if (!existing || (!ik.partiell && existing.partiell)) {
                    ikMap.set(ik.node_id, {
                        node_id: ik.node_id,
                        partiell: !!ik.partiell,
                    });
                }
            }

            // PK-Array (neues Format: Array<{node_id, pk_id}>)
            const pkArray = Array.isArray(eintrag.pk) ? eintrag.pk : [];
            for (const pk of pkArray) {
                if (pk.node_id) pkSet.add(pk.node_id);
            }

            // Hinweise: Token-Notation @[Label](lp:uuid), @[Label](lpa:uuid), #[Label](ik:uuid)
            const hinweiseText = eintrag.hinweise || "";
            for (const m of hinweiseText.matchAll(
                /@\[[^\]]*\]\(lpa:([0-9a-f-]{36})\)/g,
            )) {
                lpSet.add(m[1]);
            }
            for (const m of hinweiseText.matchAll(
                /@\[[^\]]*\]\(lp:([0-9a-f-]{36})\)/g,
            )) {
                lpSet.add(m[1]);
            }
            for (const m of hinweiseText.matchAll(
                /#\[[^\]]*\]\(ik:([0-9a-f-]{36})\)/g,
            )) {
                crossIkSet.add(m[1]);
            }

            // Material: @[Label](node:uuid) → used_with-Kanten
            for (const nodeId of extractNodeTargets(eintrag.material || "")) {
                usedWithSet.add(nodeId);
            }
        }

        return {
            ik: Array.from(ikMap.values()),
            pk: Array.from(pkSet).map((id) => ({ node_id: id })),
            // LP und cross-IK landen beide als 'references'-Kanten
            references: [
                ...Array.from(lpSet).map((id) => ({ node_id: id })),
                ...Array.from(crossIkSet).map((id) => ({ node_id: id })),
            ],
            // Material-Knoten → 'used_with'-Kanten mit via:'material'
            usedWith: Array.from(usedWithSet).map((id) => ({ node_id: id })),
        };
    }

    // Aktualisiert Kanten für eine Lernsequenz.
    // Soll-Menge wird aus den Einträgen abgeleitet, nicht aus LS-Top-Level-Feldern.
    // Nur 'references'- und 'develops'-Kanten werden verwaltet; 'part_of' bleibt unangetastet.
    async function updateEdgesForLernsequenz(draftLs, _origLs) {
        const lsId = draftLs.id;

        const derived = deriveRefsFromEntries(draftLs.metadata?.eintraege);

        // Bestehende Kanten laden (nur die verwalteten Relationen)
        const allEdges = await getNodeEdges(lsId);
        const managedEdges = allEdges.filter(
            (e) =>
                e.relation === "references" ||
                e.relation === "develops" ||
                (e.relation === "used_with" && e.metadata?.via === "material"),
        );

        const processedEdgeIds = new Set();

        // IK → 'references' mit partiell-Metadata
        for (const ikRef of derived.ik) {
            const existing = managedEdges.find(
                (e) =>
                    e.relation === "references" &&
                    e.to_node_id === ikRef.node_id,
            );
            if (existing) {
                if (existing.metadata?.partiell !== String(ikRef.partiell)) {
                    await deleteEdge(existing.id);
                    await createEdge({
                        from_node_id: lsId,
                        to_node_id: ikRef.node_id,
                        relation: "references",
                        metadata: { partiell: String(ikRef.partiell) },
                    });
                } else {
                    processedEdgeIds.add(existing.id);
                }
            } else {
                await createEdge({
                    from_node_id: lsId,
                    to_node_id: ikRef.node_id,
                    relation: "references",
                    metadata: { partiell: String(ikRef.partiell) },
                });
            }
        }

        // PK → 'develops'
        for (const pkRef of derived.pk) {
            const existing = managedEdges.find(
                (e) =>
                    e.relation === "develops" && e.to_node_id === pkRef.node_id,
            );
            if (existing) {
                processedEdgeIds.add(existing.id);
            } else {
                await createEdge({
                    from_node_id: lsId,
                    to_node_id: pkRef.node_id,
                    relation: "develops",
                    metadata: {},
                });
            }
        }

        // LP + Cross-IK → 'references' ohne partiell-Metadata
        for (const ref of derived.references) {
            const existing = managedEdges.find(
                (e) =>
                    e.relation === "references" && e.to_node_id === ref.node_id,
            );
            if (existing) {
                processedEdgeIds.add(existing.id);
            } else {
                await createEdge({
                    from_node_id: lsId,
                    to_node_id: ref.node_id,
                    relation: "references",
                    metadata: {},
                });
            }
        }

        // Material-Knoten → 'used_with' mit via:'material'
        for (const ref of derived.usedWith) {
            const existing = managedEdges.find(
                (e) =>
                    e.relation === "used_with" &&
                    e.to_node_id === ref.node_id &&
                    e.metadata?.via === "material",
            );
            if (existing) {
                processedEdgeIds.add(existing.id);
            } else {
                await createEdge({
                    from_node_id: lsId,
                    to_node_id: ref.node_id,
                    relation: "used_with",
                    metadata: { via: "material" },
                });
            }
        }

        // Veraltete Kanten entfernen (nur verwaltete Relationen, nie part_of)
        for (const edge of managedEdges) {
            if (!processedEdgeIds.has(edge.id)) {
                await deleteEdge(edge.id);
            }
        }
    }

    // Zurück-Navigation
    function goBack() {
        goto(`/knowledge/curriculum/${$page.params.id}`);
    }
</script>

<div class="h-full flex flex-col relative">
    <!-- Scrollbarer Inhaltsbereich -->
    <div
        bind:this={scrollEl}
        class="flex-1 overflow-y-auto p-6 pb-16 max-w-4xl"
    >
        {#if loading}
            <LoadingBanner />
        {:else if !canEdit}
            <!-- Sollte nicht passieren, aber als Fallback -->
            <ErrorBanner
                message="Keine Berechtigung zum Bearbeiten dieses Curriculums."
            />
        {:else}
            <!-- Kopfzeile -->
            <div class="flex items-center justify-between mb-6">
                <div>
                    <button
                        onclick={goBack}
                        class="flex items-center gap-1 mb-2 text-sm text-light-tx-2 dark:text-dark-tx-2
                             hover:text-light-tx dark:hover:text-dark-tx transition-colors"
                    >
                        <ArrowLeft class="w-4 h-4" /> Zurück
                    </button>
                    <input
                        type="text"
                        bind:value={draft.title}
                        oninput={() => (dirty = true)}
                        placeholder="Curriculum-Titel"
                        aria-label="Curriculum-Titel"
                        class="text-2xl font-bold text-light-tx dark:text-dark-tx bg-transparent w-full
                               border-b border-transparent hover:border-light-ui-3 dark:hover:border-dark-ui-3
                               focus:border-primary dark:focus:border-primary-dark
                               focus:outline-none transition-colors"
                    />
                    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                        Bearbeitungsmodus
                        {#if totalStd > 0}
                            · Gesamt: {totalStd} Std.
                        {/if}
                    </p>
                </div>
                <div bind:this={topActionsEl} class="flex gap-2 items-center">
                    {#if dirty}
                        <span class="text-sm text-light-ye dark:text-dark-ye">
                            Ungespeicherte Änderungen
                        </span>
                    {/if}
                    <button
                        onclick={goBack}
                        class="px-4 py-2 text-sm rounded-md
                           border border-light-ui-3 dark:border-dark-ui-3
                           text-light-tx dark:text-dark-tx
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                    >
                        Abbrechen
                    </button>
                    <button
                        onclick={save}
                        disabled={saving || !dirty}
                        class="px-4 py-2 text-sm rounded-md bg-primary dark:bg-primary-dark
                               text-white font-medium hover:opacity-90 transition-opacity
                               disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {saving ? "Wird gespeichert…" : "Speichern"}
                    </button>
                </div>
            </div>

            <!-- Fehler/Erfolg -->
            {#if saveError}
                <ErrorBanner message={saveError} />
            {/if}
            {#if saveSuccess}
                <SuccessBanner message="Curriculum erfolgreich gespeichert." />
            {/if}

            <!-- Curriculum-Tabelle im Edit-Mode -->
            {#if draft}
                <div
                    class="bg-white dark:bg-dark-bg rounded-lg border border-light-ui-3 dark:border-dark-ui-3"
                >
                    <CurriculumTable
                        curriculum={draft}
                        editMode={true}
                        subjectId={curriculum?.subject_id ?? null}
                        grade={gradeInt}
                        onchange={() => {
                            dirty = true;
                        }}
                    />
                </div>
            {/if}
        {/if}
    </div>

    <!-- Sticky-Footer: überlagert den Inhalt, nur sichtbar wenn obere Aktionen weggescrollt -->
    {#if canEdit && showStickyFooter}
        <div
            class="absolute bottom-0 left-0 right-0 border-t border-light-ui-3 dark:border-dark-ui-3 bg-light-bg/95 dark:bg-dark-bg/95 backdrop-blur px-6 py-2 flex gap-2 items-center justify-end"
        >
            {#if dirty}
                <span class="text-sm text-light-ye dark:text-dark-ye mr-2">
                    Ungespeicherte Änderungen
                </span>
            {/if}
            <button
                onclick={goBack}
                class="px-4 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx dark:text-dark-tx
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
            >
                Abbrechen
            </button>
            <button
                onclick={save}
                disabled={saving || !dirty}
                class="px-4 py-1.5 text-sm rounded-md bg-primary dark:bg-primary-dark
                       text-white font-medium hover:opacity-90 transition-opacity
                       disabled:opacity-50 disabled:cursor-not-allowed"
            >
                {saving ? "Wird gespeichert…" : "Speichern"}
            </button>
        </div>
    {/if}
</div>
