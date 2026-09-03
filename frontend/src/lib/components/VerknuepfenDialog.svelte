<script>
    /**
     * Kanten anlegen (UI-Notiz A8) — ein Formular, kein Graph-Editor.
     *
     * Die ADR-013-Entscheidung bleibt: Der Graph ist Anzeige. Gepflegt wird hier, und
     * zwar in der Sprache der Sache statt in Pfeil-Abstraktionen — „‚Oxidation‘ steht in
     * Beziehung zu …".
     *
     * **Das Wiki-Muster:** Findet die Suche nichts Passendes, legt der Dialog den
     * fehlenden Begriff im Hintergrund an (Titel + Fach des Ausgangsknotens) und setzt
     * die Kante sofort. Kein Fokuswechsel — die Fachschaft kann erst das Netz aufspannen
     * und später definieren. Solche Stubs tragen `metadata.unvollstaendig` und sind
     * dadurch zählbar und filterbar; ein stillschweigend leerer Eintrag wäre es nicht.
     */
    import { searchContextNodes, createContextNode, createContextEdge } from "$lib/api.js";
    import { CONTENT_TYPE_LABELS, SCOPE_DEFAULTS } from "$lib/taxonomy.js";
    import { relationen, kategorieVon, STUB_MARKIERUNG } from "$lib/collections.js";
    import { subjectMap } from "$lib/stores/subjects.js";
    import NodeTypeIcon from "$lib/components/NodeTypeIcon.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";

    let { node, onclose, onverknuepft } = $props();

    const moeglich = $derived(relationen(node.content_type));
    let relation = $state(relationen(node.content_type)[0]?.relation ?? "");
    const gewaehlt = $derived(moeglich.find((r) => r.relation === relation) ?? null);

    let frage = $state("");
    let treffer = $state([]);
    let sucht = $state(false);
    let fehler = $state(null);
    let laeuft = $state(false);
    let suchTimer = null;
    let lauf = 0;

    /** Zielsuche über die Identifikations-Stufe — dieselbe Mechanik wie `@` im Chat. */
    async function suchen() {
        const q = frage.trim();
        if (q.length < 2) {
            treffer = [];
            return;
        }
        const meiner = ++lauf;
        sucht = true;
        try {
            const umschlag = await searchContextNodes(q, null, {
                identification_only: true,
                conversation_subject_id: node.subject_id ?? null,
            });
            if (meiner !== lauf) return;
            const erlaubt = gewaehlt?.ziel ?? [];
            treffer = (umschlag?.identifikation?.treffer ?? [])
                .filter((k) => k.node_id !== node.id)
                .filter((k) => erlaubt.length === 0 || erlaubt.includes(k.content_type))
                .slice(0, 8);
        } catch (e) {
            if (meiner === lauf) fehler = e.message;
        } finally {
            if (meiner === lauf) sucht = false;
        }
    }

    function beiEingabe(e) {
        frage = e.target.value;
        clearTimeout(suchTimer);
        suchTimer = setTimeout(suchen, 300);
    }

    async function verknuepfeMit(zielId) {
        laeuft = true;
        fehler = null;
        try {
            await createContextEdge({
                from_node_id: node.id,
                to_node_id: zielId,
                relation,
            });
            frage = "";
            treffer = [];
            onverknuepft?.();
        } catch (e) {
            fehler = e.message;
        } finally {
            laeuft = false;
        }
    }

    /**
     * Den fehlenden Baustein anlegen und sofort verknüpfen.
     *
     * Der Typ ergibt sich aus der Relation (`ziel`), das Fach vom Ausgangsknoten. Ohne
     * Inhalt — deshalb die Markierung, die ihn von einem vergessenen Eintrag
     * unterscheidbar macht.
     */
    async function anlegenUndVerknuepfen() {
        const zielTyp = gewaehlt?.ziel?.[0];
        if (!zielTyp) return;
        laeuft = true;
        fehler = null;
        try {
            const [defRead, defWrite] = SCOPE_DEFAULTS[zielTyp] ?? ["school", "private"];
            const neu = await createContextNode({
                category: kategorieVon(zielTyp),
                content_type: zielTyp,
                title: frage.trim(),
                content: null,
                metadata: { [STUB_MARKIERUNG]: true },
                subject_id: node.subject_id ?? null,
                read_scope: defRead,
                write_scope: defWrite,
                write_scope_group_id: ["subject", "group"].includes(defWrite)
                    ? node.write_scope_group_id
                    : null,
            });
            await verknuepfeMit(neu.id);
        } catch (e) {
            fehler = e.message;
            laeuft = false;
        }
    }

    const kannAnlegen = $derived(
        frage.trim().length >= 2 &&
            !sucht &&
            treffer.length === 0 &&
            Boolean(gewaehlt?.ziel?.[0]),
    );
</script>

<div
    class="p-4 rounded-md border border-light-ui-3 dark:border-dark-ui-3
           bg-light-bg-2 dark:bg-dark-bg-2"
>
    <div class="flex items-start justify-between gap-3 mb-3">
        <h3 class="text-sm font-semibold text-light-tx dark:text-dark-tx">Verknüpfen</h3>
        <button
            onclick={onclose}
            class="text-xs text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx
                   dark:hover:text-dark-tx"
        >
            Schließen
        </button>
    </div>

    {#if fehler}
        <div class="mb-3"><ErrorBanner message={fehler} /></div>
    {/if}

    <!-- Richtung als Satz, nicht als Pfeil -->
    <p class="text-sm text-light-tx dark:text-dark-tx mb-2">
        „{node.title}“
        <select
            bind:value={relation}
            onchange={suchen}
            class="mx-1 px-2 py-1 text-sm rounded-md border border-light-ui-3
                   dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                   text-light-tx dark:text-dark-tx"
        >
            {#each moeglich as r}
                <option value={r.relation}>{r.label}</option>
            {/each}
        </select>
        …
    </p>

    <input
        type="search"
        placeholder="Baustein suchen…"
        value={frage}
        oninput={beiEingabe}
        class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3
               dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
               text-light-tx dark:text-dark-tx"
    />

    {#if sucht}
        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-2">Sucht…</p>
    {:else if treffer.length > 0}
        <ul class="mt-2 space-y-1">
            {#each treffer as k}
                <li>
                    <button
                        onclick={() => verknuepfeMit(k.node_id)}
                        disabled={laeuft}
                        class="w-full text-left px-2 py-1.5 rounded-md text-sm
                               text-light-tx dark:text-dark-tx
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                               disabled:opacity-50 flex items-center gap-2"
                    >
                        <NodeTypeIcon contentType={k.content_type} size={16} />
                        <span class="flex-1">{k.titel ?? k.title}</span>
                        {#if k.subject_id}
                            <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                {$subjectMap[k.subject_id]?.name ?? ""}
                            </span>
                        {/if}
                        <span class="text-xs text-light-tx-3 dark:text-dark-tx-3">
                            {CONTENT_TYPE_LABELS[k.content_type] ?? k.content_type}
                        </span>
                    </button>
                </li>
            {/each}
        </ul>
    {:else if kannAnlegen}
        <!-- Wiki-Muster: anlegen, verknüpfen, weitermachen -->
        <button
            onclick={anlegenUndVerknuepfen}
            disabled={laeuft}
            class="mt-2 w-full text-left px-2 py-1.5 rounded-md text-sm
                   text-light-bl dark:text-dark-bl hover:bg-light-ui-2
                   dark:hover:bg-dark-ui-2 disabled:opacity-50"
        >
            „{frage.trim()}“ als
            {CONTENT_TYPE_LABELS[gewaehlt.ziel[0]] ?? gewaehlt.ziel[0]}
            anlegen und verknüpfen
        </button>
        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-1">
            Wird ohne Inhalt angelegt und als „unvollständig“ geführt — nachtragen lässt
            er sich jederzeit.
        </p>
    {:else if frage.trim().length >= 2}
        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-2">Nichts gefunden.</p>
    {/if}
</div>
