<script>
    /**
     * IK-Selektor-Komponente für den Curriculum-Editor
     *
     * Props:
     * - subjectId: ID des Fachs (zum Laden der IK-Kompetenzknoten)
     * - selected: Array der aktuell ausgewählten IKs [{node_id, title, nr, partiell}]
     * - onchange: Callback bei Änderung (newSelectedArray)
     */

    import { X, Search, Check } from "lucide-svelte";

    let {
        subjectId = null,
        grade = null,
        bpVersion = null,
        selected = $bindable([]),
        onchange = () => {},
    } = $props();

    let searchQuery = $state("");
    let searchResults = $state([]);
    let loading = $state(false);
    let showDropdown = $state(false);
    let warnings = $state([]); // Array von nicht gefundenen IK-Nummern

    // Lade IK-Knoten basierend auf der Suche
    $effect(() => {
        if (!searchQuery.trim() || searchQuery.length < 1) {
            searchResults = [];
            return;
        }

        const timer = setTimeout(async () => {
            loading = true;
            try {
                const params = new URLSearchParams();
                params.set("q", searchQuery);
                params.append("content_type", "ik_kompetenz");
                if (subjectId) params.set("subject_id", subjectId);
                if (grade) params.set("grade", grade);
                if (bpVersion) params.set("bp_version", bpVersion);
                params.set("limit", "20");

                const res = await fetch(`/api/context/nodes?${params}`, {
                    credentials: "include",
                });
                if (res.ok) {
                    searchResults = await res.json();
                } else {
                    searchResults = [];
                }
            } catch (e) {
                console.error("Suche fehlgeschlagen:", e);
                searchResults = [];
            } finally {
                loading = false;
            }
        }, 300);

        return () => clearTimeout(timer);
    });

    // Direkteingabe: Wenn User eine Nummer eingibt, suche danach
    function handleDirectInput(value) {
        searchQuery = value;
        showDropdown = true;
    }

    // IK auswählen
    function selectIK(ikNode) {
        const alreadySelected = selected.some((s) => s.node_id === ikNode.id);
        if (!alreadySelected) {
            selected = [
                ...selected,
                {
                    node_id: ikNode.id,
                    title: ikNode.title,
                    nr: extractNrFromTitle(ikNode.title),
                    partiell: false,
                },
            ];
            emitChange();
        }
        searchQuery = "";
        showDropdown = false;
    }

    // IK entfernen
    function removeIK(nr) {
        selected = selected.filter((s) => s.nr !== nr);
        emitChange();
    }

    // Partiell-Flag toggeln
    function togglePartiell(nr) {
        selected = selected.map((s) =>
            s.nr === nr ? { ...s, partiell: !s.partiell } : s,
        );
        emitChange();
    }

    // Extrahiere IK-Nummer aus Titel, z.B. "3.1.1(2)" aus "3.1.1(2) …" oder "3.1.1.(2) …"
    function extractNrFromTitle(title) {
        const match = title.match(/(\d+\.\d+(?:\.\d+)*(?:\.?\(\d+\))?)/);
        return match ? match[1].replace(/\.\(/, '(') : title;
    }

    // Change-Event auslösen
    function emitChange() {
        onchange(selected);
    }

    // Füge IK per Direkteingabe hinzu
    function addByNumber() {
        if (!searchQuery.trim()) return;

        const nr = searchQuery.trim();

        // Prüfe ob bereits ausgewählt
        const alreadySelected = selected.some((s) => s.nr === nr);
        if (alreadySelected) {
            searchQuery = "";
            showDropdown = false;
            return;
        }

        // Prüfe ob wir den Knoten in den Ergebnissen haben
        const found = searchResults.find(
            (r) => extractNrFromTitle(r.title) === nr,
        );
        if (found) {
            selectIK(found);
        } else {
            // Nicht gefunden - trotzdem hinzufügen mit Warnung
            warnings = [...warnings, nr];
            selected = [
                ...selected,
                {
                    node_id: null,
                    title: `Unbekannte IK: ${nr}`,
                    nr: nr,
                    partiell: false,
                },
            ];
            emitChange();
            searchQuery = "";
            showDropdown = false;
        }
    }

    // Blur-Handler
    function handleBlur() {
        // Kurze Verzögerung, damit Klicks auf Dropdown-Items funktionieren
        setTimeout(() => {
            showDropdown = false;
        }, 200);
    }
</script>

<div class="space-y-2">
    <!-- Ausgewählte IKs -->
    {#if selected.length > 0}
        <div class="flex flex-wrap gap-2">
            {#each selected as ik}
                <div
                    class="flex items-center gap-1 px-2 py-1 rounded-full bg-light-bl/20 dark:bg-dark-bl/20"
                >
                    <input
                        type="checkbox"
                        checked={ik.partiell}
                        onchange={() => togglePartiell(ik.nr)}
                        class="w-3 h-3 cursor-pointer"
                        title="Partiell (Häkchen = nur Teilaspekte dieser Kompetenz werden behandelt)"
                    />
                    <span class="text-sm text-light-tx dark:text-dark-tx">
                        {ik.nr}
                    </span>
                    {#if !ik.node_id}
                        <span
                            class="text-xs text-light-ye dark:text-dark-ye"
                            title="Nicht in Datenbank gefunden"
                        >
                            ⚠
                        </span>
                    {/if}
                    <button
                        onclick={() => removeIK(ik.nr)}
                        class="text-light-re dark:text-dark-re hover:text-light-re/80"
                        title="Entfernen"
                    >
                        <X class="w-3 h-3" />
                    </button>
                </div>
            {/each}
        </div>
    {/if}

    <!-- Warnungen für unbekannte IKs -->
    {#if warnings.length > 0}
        <div class="text-xs text-light-ye dark:text-dark-ye">
            IK-Nummern nicht gefunden: {warnings.join(", ")}
        </div>
    {/if}

    <!-- Suchfeld -->
    <div class="relative">
        <div class="relative">
            <Search
                class="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-light-tx-2 dark:text-dark-tx-2"
            />
            <input
                type="text"
                bind:value={searchQuery}
                oninput={(e) => handleDirectInput(e.target.value)}
                onfocus={() => (showDropdown = true)}
                onblur={handleBlur}
                onkeydown={(e) => {
                    if (e.key === "Enter") {
                        e.preventDefault();
                        addByNumber();
                    }
                }}
                placeholder="IK-Nummer suchen (z.B. 3.1.1)"
                class="w-full pl-8 pr-10 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       focus:outline-none focus:border-primary dark:focus:border-primary-dark"
            />
        </div>

        <!-- Dropdown mit Suchergebnissen -->
        {#if showDropdown && (searchResults.length > 0 || loading)}
            <div
                class="absolute top-full left-0 right-0 mt-1 z-50 bg-white dark:bg-dark-bg-2
                        border border-light-ui-3 dark:border-dark-ui-3 rounded-md shadow-lg max-h-60 overflow-y-auto"
            >
                {#if loading}
                    <div
                        class="p-3 text-sm text-light-tx-2 dark:text-dark-tx-2"
                    >
                        Suche…
                    </div>
                {:else if searchResults.length === 0}
                    <div
                        class="p-3 text-sm text-light-tx-2 dark:text-dark-tx-2"
                    >
                        Keine IK-Kompetenz gefunden. Drücken Sie Enter, um die
                        Nummer trotzdem hinzuzufügen.
                    </div>
                {:else}
                    {#each searchResults as node (node.id)}
                        <button
                            onclick={() => selectIK(node)}
                            class="w-full px-3 py-2 text-left text-sm hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                                   flex items-center gap-2 transition-colors"
                        >
                            <div
                                class="w-4 h-4 rounded-full border border-light-ui-3 dark:border-dark-ui-3 flex items-center justify-center"
                            >
                                {#if selected.some((s) => s.node_id === node.id)}
                                    <Check
                                        class="w-3 h-3 text-primary dark:text-primary-dark"
                                    />
                                {/if}
                            </div>
                            <div class="min-w-0 flex-1">
                                <div
                                    class="font-medium text-light-tx dark:text-dark-tx"
                                >
                                    {node.title}
                                </div>
                                <div
                                    class="text-xs text-light-tx-2 dark:text-dark-tx-2 truncate"
                                >
                                    {extractNrFromTitle(node.title)}
                                </div>
                            </div>
                        </button>
                    {/each}
                {/if}
            </div>
        {/if}
    </div>
</div>
