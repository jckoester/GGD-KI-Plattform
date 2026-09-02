<script>
    /**
     * Sammlungs-Liste (UI-Notiz A1) — **eine** Seite für alle Sammlungen.
     *
     * Was hier steht, ist Darstellung; die Regeln (Spalten, Filter, Labels) kommen aus
     * `collections.js` und damit aus der Taxonomie. Eine neue Sammlung braucht deshalb
     * keinen Code, nur einen `collection:`-Block.
     */
    import { untrack } from "svelte";
    import { page } from "$app/stores";
    import { browser } from "$app/environment";
    import { goto } from "$app/navigation";
    import { Plus, Archive, Pencil } from "lucide-svelte";
    import { getContextNodes, updateContextNode } from "$lib/api.js";
    import { CONTENT_TYPE_LABELS } from "$lib/taxonomy.js";
    import { sammlung, spalten, filter, zellenwert } from "$lib/collections.js";
    import { subjects, subjectMap } from "$lib/stores/subjects.js";
    import { user } from "$lib/stores/user.js";
    import NodeTypeIcon from "$lib/components/NodeTypeIcon.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";

    const typ = $derived($page.params.type);
    const config = $derived(sammlung(typ));
    const label = $derived(CONTENT_TYPE_LABELS[typ] ?? typ);
    const tabellenspalten = $derived(spalten(typ));
    const angeboteneFilter = $derived(filter(typ));

    let nodes = $state([]);
    let loading = $state(false);
    let error = $state(null);
    let aktionsfehler = $state(null);

    // Filterzustand. `fach` kommt beim Absprung von der Fachseite als Query mit.
    let fachId = $state($page.url.searchParams.get("subject_id") ?? "");
    let status = $state($page.url.searchParams.get("status") ?? "active");
    let q = $state($page.url.searchParams.get("q") ?? "");
    let feldwert = $state($page.url.searchParams.get("wert") ?? "");
    let suchTimer = null;

    /**
     * Die Adresse, die diesen Filterzustand beschreibt.
     *
     * Sie **ist** der Rückweg: Die Detailansicht kennt einen `?back=`-Parameter, und nur
     * wenn die Filter darin stehen, führt „Zurück" in den gefilterten Ausschnitt statt an
     * den Anfang der Sammlung (UI-Notiz A3). Nebenbei übersteht der Zustand einen Reload.
     *
     * ⚠️ **Baut die Adresse aus dem Zustand, liest nicht `$page.url`.** Ein Lesen wäre
     * eine reaktive Abhängigkeit — und weil `goto()` die Adresse ändert, liefe jede
     * Reaktion darauf im Kreis. Genau das ist am 02.09.2026 passiert: Der Aufruf stand im
     * `$effect`, der `$page.url` las, und die Seite lud sekündlich neu.
     */
    const rueckweg = $derived.by(() => {
        const params = new URLSearchParams();
        for (const [name, wert] of [
            ["subject_id", fachId], ["status", status === "active" ? "" : status],
            ["q", q.trim()], ["wert", feldwert],
        ]) {
            if (wert) params.set(name, String(wert));
        }
        const query = params.toString();
        return `/knowledge/collections/${typ}${query ? `?${query}` : ""}`;
    });

    /**
     * Den Zustand in die Adresszeile spiegeln — **nur aus Bedienhandlungen heraus**,
     * nie aus einem Effekt (siehe oben). `replaceState`, damit nicht jeder Tastendruck
     * einen History-Eintrag hinterlässt.
     */
    function inDieUrl() {
        if (!browser) return;
        const ziel = rueckweg;
        if (ziel === location.pathname + location.search) return;
        goto(ziel, { replaceState: true, keepFocus: true, noScroll: true });
    }

    /** Filteränderung: Adresse spiegeln und neu laden. */
    function filterGeaendert() {
        inDieUrl();
        load();
    }

    // Das Feld, nach dem zusätzlich gefiltert werden kann (z. B. `ab_klasse`).
    const feldFilter = $derived(
        angeboteneFilter.find((f) => !["fach", "status", "titel"].includes(f)) ?? null,
    );
    const feldSpalte = $derived(
        tabellenspalten.find((s) => s.name === feldFilter) ?? null,
    );

    async function load() {
        // ⚠️ `untrack`: Alles, was hier **vor** dem ersten `await` gelesen wird, würde
        // sonst zur Abhängigkeit des aufrufenden Effekts. Über `q` hinge dann jeder
        // Tastendruck am Effekt — die Entprellung darüber liefe ins Leere, und die Seite
        // schickte je Zeichen eine Anfrage.
        const params = untrack(() => {
            const p = { content_type: typ, status };
            if (fachId) p.subject_id = Number(fachId);
            if (q.trim().length >= 2) p.q = q.trim();
            return p;
        });
        if (!untrack(() => config)) return;

        loading = true;
        error = null;
        try {
            nodes = await getContextNodes(params);
        } catch (e) {
            error = e.message;
        } finally {
            loading = false;
        }
    }

    // Lädt bei Typwechsel und geänderten Serverfiltern. **Kein `goto` hier** — die
    // Adresse schreiben die Bedienhandlungen, sonst entsteht der Zyklus von oben.
    $effect(() => {
        typ;
        fachId;
        status;
        load();
    });

    function onSuche(e) {
        q = e.target.value;
        clearTimeout(suchTimer);
        suchTimer = setTimeout(filterGeaendert, 300);
    }

    // Feldfilter clientseitig: Die Werte stehen in `metadata`, wofür es keinen
    // Serverfilter gibt — und die Sammlungen sind klein genug, dass das nichts kostet.
    const sichtbar = $derived.by(() => {
        const gefiltert = feldFilter && feldwert
            ? nodes.filter(
                  (n) => String((n.metadata ?? {})[feldFilter] ?? "") === feldwert,
              )
            : nodes;
        // Eigenes zuerst — dieselbe Sortierstufe wie in der Suche.
        return [...gefiltert].sort((a, b) => {
            const meins = (n) => (n.owner_pseudonym === $user?.pseudonym ? 0 : 1);
            return meins(a) - meins(b) || (a.title ?? "").localeCompare(b.title ?? "");
        });
    });

    const feldwerte = $derived(
        feldFilter
            ? [
                  ...new Set(
                      nodes
                          .map((n) => (n.metadata ?? {})[feldFilter])
                          .filter((v) => v !== undefined && v !== null && v !== ""),
                  ),
              ].sort((a, b) => (a > b ? 1 : -1))
            : [],
    );

    const darfAnlegen = $derived(nodes.some((n) => n.darf_schreiben) || nodes.length === 0);

    async function archivieren(node) {
        aktionsfehler = null;
        try {
            await updateContextNode(node.id, { status: "archived" });
            nodes = nodes.filter((n) => n.id !== node.id);
        } catch (e) {
            aktionsfehler = e.message;
        }
    }
</script>

<div class="h-full overflow-y-auto p-6 max-w-5xl">
    {#if !config}
        <ErrorBanner message="Für „{typ}“ gibt es keine Sammlung." />
    {:else}
        <a
            href="/knowledge"
            class="text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx
                   dark:hover:text-dark-tx transition-colors mb-1 block"
        >
            ← Wissensgraph
        </a>

        <div class="flex items-start justify-between gap-4 mb-4">
            <div>
                <h1
                    class="text-2xl font-bold text-light-tx dark:text-dark-tx
                           flex items-center gap-2"
                >
                    <NodeTypeIcon contentType={typ} size={22} />
                    {label}
                </h1>
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1 max-w-2xl">
                    {config.beschreibung}
                </p>
                <p class="text-xs text-light-tx-3 dark:text-dark-tx-3 mt-1">
                    {sichtbar.length}
                    {sichtbar.length === 1 ? "Eintrag" : "Einträge"}
                    {status === "archived" ? " im Archiv" : ""}
                </p>
            </div>
            {#if darfAnlegen}
                <a
                    href="/knowledge/collections/{typ}/new?back={encodeURIComponent(
                        rueckweg,
                    )}{fachId ? `&subject_id=${fachId}` : ''}"
                    class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm
                           bg-primary dark:bg-primary-dark text-white hover:opacity-90"
                >
                    <Plus size="16" /> Neuer Eintrag
                </a>
            {/if}
        </div>

        {#if aktionsfehler}
            <div class="mb-3"><ErrorBanner message={aktionsfehler} /></div>
        {/if}

        <!-- Filterzeile -->
        <div class="flex flex-wrap gap-2 mb-4">
            {#if angeboteneFilter.includes("titel")}
                <input
                    type="search"
                    placeholder="Titel suchen…"
                    value={q}
                    oninput={onSuche}
                    class="flex-1 min-w-48 px-3 py-1.5 text-sm rounded-md border
                           border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                           text-light-tx dark:text-dark-tx"
                />
            {/if}
            {#if angeboteneFilter.includes("fach")}
                <select
                    bind:value={fachId}
                    onchange={inDieUrl}
                    aria-label="Fach"
                    class="px-3 py-1.5 text-sm rounded-md border border-light-ui-3
                           dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                           text-light-tx dark:text-dark-tx"
                >
                    <option value="">Alle Fächer</option>
                    {#each $subjects as fach}
                        <option value={String(fach.id)}>{fach.name}</option>
                    {/each}
                </select>
            {/if}
            {#if feldFilter && feldwerte.length > 0}
                <select
                    bind:value={feldwert}
                    onchange={inDieUrl}
                    aria-label={feldSpalte?.label ?? feldFilter}
                    class="px-3 py-1.5 text-sm rounded-md border border-light-ui-3
                           dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                           text-light-tx dark:text-dark-tx"
                >
                    <option value="">Alle ({feldSpalte?.label ?? feldFilter})</option>
                    {#each feldwerte as wert}
                        <option value={String(wert)}>{wert}</option>
                    {/each}
                </select>
            {/if}
            {#if angeboteneFilter.includes("status")}
                <select
                    bind:value={status}
                    onchange={inDieUrl}
                    aria-label="Status"
                    class="px-3 py-1.5 text-sm rounded-md border border-light-ui-3
                           dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
                           text-light-tx dark:text-dark-tx"
                >
                    <option value="active">Aktiv</option>
                    <option value="archived">Archiv</option>
                </select>
            {/if}
        </div>

        {#if loading}
            <LoadingBanner />
        {:else if error}
            <ErrorBanner message={error} />
        {:else if sichtbar.length === 0}
            <InfoBanner
                message={darfAnlegen
                    ? `Noch kein Eintrag. Lege den ersten an — ${config.beschreibung}`
                    : "Noch kein Eintrag. Diese Sammlung pflegt die zuständige Fachschaft."}
            />
        {:else}
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead>
                        <tr class="border-b border-light-ui-3 dark:border-dark-ui-3 text-left">
                            {#each tabellenspalten as spalte}
                                <th
                                    class="px-3 py-2 font-medium text-light-tx-2
                                           dark:text-dark-tx-2 whitespace-nowrap"
                                >
                                    {spalte.label}
                                </th>
                            {/each}
                            <th class="px-3 py-2"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each sichtbar as node (node.id)}
                            <tr
                                class="border-b border-light-ui-3 dark:border-dark-ui-3
                                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                                       transition-colors cursor-pointer"
                                onclick={() =>
                                    goto(
                                        `/knowledge/${node.id}?back=${encodeURIComponent(rueckweg)}`,
                                    )}
                            >
                                {#each tabellenspalten as spalte}
                                    <td
                                        class="px-3 py-2 {spalte.name === 'titel'
                                            ? 'text-light-tx dark:text-dark-tx font-medium'
                                            : 'text-light-tx-2 dark:text-dark-tx-2'}"
                                    >
                                        {zellenwert(node, spalte, {
                                            fachname: node.subject_id
                                                ? ($subjectMap[node.subject_id]?.name ?? null)
                                                : null,
                                        })}
                                    </td>
                                {/each}
                                <td class="px-3 py-2" onclick={(e) => e.stopPropagation()}>
                                    {#if node.darf_schreiben}
                                        <div class="flex items-center gap-2">
                                            <a
                                                href="/knowledge/collections/{typ}/{node.id}/edit?back={encodeURIComponent(
                                                    rueckweg,
                                                )}"
                                                title="Bearbeiten"
                                                class="text-light-tx-2 dark:text-dark-tx-2
                                                       hover:text-light-tx dark:hover:text-dark-tx"
                                            >
                                                <Pencil size="16" />
                                            </a>
                                            {#if node.status === "active"}
                                                <button
                                                    onclick={() => archivieren(node)}
                                                    title="Archivieren"
                                                    class="text-light-tx-2 dark:text-dark-tx-2
                                                           hover:text-light-tx dark:hover:text-dark-tx"
                                                >
                                                    <Archive size="16" />
                                                </button>
                                            {/if}
                                        </div>
                                    {:else}
                                        <span
                                            title="Pflege durch die zuständige Fachschaft
                                                   oder die Administration"
                                            class="text-xs text-light-tx-3 dark:text-dark-tx-3"
                                        >
                                            🔒
                                        </span>
                                    {/if}
                                </td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        {/if}
    {/if}
</div>
