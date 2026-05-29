<script>
    import { page } from "$app/stores";
    import { goto } from "$app/navigation";
    import { CONTENT_TYPES, CATEGORY_LABELS } from "$lib/taxonomy.js";
    import {
        getContextNode,
        updateContextNode,
        getArchivedReferences,
        copyContextNode,
    } from "$lib/api.js";
    import { user } from "$lib/stores/user.js";
    import { myTeachingGroups } from "$lib/stores/myGroups.js";
    import { ArrowLeft } from "lucide-svelte";

    // ── Knoten laden ────────────────────────────────────────────────────────
    let node = $state(null);
    let loadingNode = $state(true);

    // ── Formularfelder ──────────────────────────────────────────────────────
    let title = $state("");
    let category = $state("");
    let contentType = $state("");
    let content = $state("");
    let readScope = $state("school");
    let writeScope = $state("private");
    let readScopeGroupId = $state(null);
    let writeScopeGroupId = $state(null);
    let validUntil = $state("");
    let schuljahr = $state("");
    let metadata = $state("{}");

    // Strukturierte Metadaten
    let signatur = $state({
        name: "",
        sprache: "arduino_cpp",
        parameter: [],
        rueckgabe: { typ: "", beschreibung: "" },
    });
    let schaltzeichen = $state({
        beschreibung: "",
        norm: "",
        kennung: "",
        svg: "",
    });

    let saving = $state(false);
    let errors = $state({});
    let savedMessage = $state(null);

    // Archivierte Referenzen
    let archivedRefs = $state([]);

    // Kopieren-Dialog
    let showCopyDialog = $state(false);
    let copySchuljahr = $state("");
    let copyValidUntil = $state("");
    let copyLoading = $state(false);
    let copyError = $state(null);

    // Archivieren-Bestätigung
    let showArchiveConfirm = $state(false);
    let archiveLoading = $state(false);

    // ── Rollen & Berechtigungen ────────────────────────────────────────────
    const isAdmin = $derived($user?.roles?.includes("admin") ?? false);
    const isTeacher = $derived($user?.roles?.includes("teacher") ?? false);

    const canEdit = $derived(
        node && (isAdmin || node.owner_pseudonym === $user?.pseudonym),
    );

    // ── Content-Type-Optionen je Category ──────────────────────────────────
    const contentTypeOptions = $derived(
        category ? (CONTENT_TYPES[category] ?? []) : [],
    );

    // ── Zulässige write_scope-Optionen je Rolle ─────────────────────────────
    const writeScopes = $derived.by(() => {
        const all = ["private", "group", "subject", "school"];
        if (isAdmin) return all;
        return ["private", "group", "subject"];
    });

    // ── Schuljahr-Hilfsfunktion ─────────────────────────────────────────────
    function currentSchuljahr() {
        const now = new Date();
        const year = now.getFullYear();
        return now.getMonth() >= 7
            ? `${year}/${year + 1}`
            : `${year - 1}/${year}`;
    }

    function schuljahresEnde() {
        const year = parseInt(
            schuljahr.split("/")[1] ?? new Date().getFullYear() + 1,
        );
        return `${year}-07-31`;
    }

    // ── Metadata zusammenbauen ──────────────────────────────────────────────
    function buildMetadata() {
        if (category === "concept" && contentType === "funktion") {
            return { signatur };
        }
        if (category === "concept" && contentType === "bauteil") {
            return { schaltzeichen };
        }
        try {
            return JSON.parse(metadata);
        } catch {
            return {};
        }
    }

    // ── Parameter-Manipulation ────────────────────────────────────────────
    function addParameter() {
        signatur.parameter = [
            ...signatur.parameter,
            { name: "", typ: "", beschreibung: "" },
        ];
    }

    function removeParameter(index) {
        signatur.parameter = signatur.parameter.filter((_, i) => i !== index);
    }

    function updateParameter(index, field, value) {
        signatur.parameter[index][field] = value;
        signatur.parameter = [...signatur.parameter];
    }

    // ── Knoten laden beim Mount ────────────────────────────────────────────
    $effect(() => {
        const id = $page.params.id;
        loadingNode = true;
        getContextNode(id)
            .then((n) => {
                node = n;
                // Formularfelder befüllen
                title = n.title;
                category = n.category;
                contentType = n.content_type ?? "";
                content = n.content ?? "";
                readScope = n.read_scope;
                writeScope = n.write_scope;
                readScopeGroupId = n.read_scope_group_id;
                writeScopeGroupId = n.write_scope_group_id;
                validUntil = n.valid_until ?? "";
                schuljahr = n.schuljahr ?? currentSchuljahr();
                // Metadata deserialisieren
                if (
                    n.category === "concept" &&
                    n.content_type === "funktion" &&
                    n.metadata?.signatur
                ) {
                    signatur = n.metadata.signatur;
                } else if (
                    n.category === "concept" &&
                    n.content_type === "bauteil" &&
                    n.metadata?.schaltzeichen
                ) {
                    schaltzeichen = n.metadata.schaltzeichen;
                } else {
                    metadata = JSON.stringify(n.metadata ?? {}, null, 2);
                }
                // Archivierte Referenzen laden
                if (n.status === "active") {
                    getArchivedReferences(n.id).then((refs) => {
                        archivedRefs = refs;
                    });
                }
            })
            .catch((e) => {
                errors.general = e.message;
            })
            .finally(() => {
                loadingNode = false;
            });
    });

    // ── Speichern ──────────────────────────────────────────────────────────
    async function save() {
        errors = {};
        if (!title.trim()) errors.title = "Pflichtfeld";
        if (!category) errors.category = "Pflichtfeld";
        if (!contentType) errors.contentType = "Pflichtfeld";
        if (Object.keys(errors).length > 0) return;

        saving = true;
        try {
            const id = $page.params.id;
            const payload = {
                title: title.trim(),
                category,
                content_type: contentType,
                content: content.trim() || null,
                metadata: buildMetadata(),
                read_scope: readScope,
                write_scope: writeScope,
                read_scope_group_id: ["subject", "group"].includes(readScope)
                    ? readScopeGroupId
                    : null,
                write_scope_group_id: ["subject", "group"].includes(writeScope)
                    ? writeScopeGroupId
                    : null,
                valid_until: validUntil || null,
                schuljahr: schuljahr || null,
            };
            await updateContextNode(id, payload);
            // Erfolgsmeldung
            savedMessage = "Gespeichert";
            setTimeout(() => {
                savedMessage = null;
            }, 2000);
        } catch (e) {
            if (e.status === 422) {
                errors.general = e.message;
            } else {
                errors.general = e.message;
            }
        } finally {
            saving = false;
        }
    }

    // ── Group-Optionen für Selects ────────────────────────────────────────
    const groupOptions = $derived(
        $myTeachingGroups.map((g) => ({
            id: g.id,
            name: g.name,
            subject_id: g.subject_id,
        })),
    );

    // ── Formatierungsfunktionen ─────────────────────────────────────────────
    function formatDate(dateString) {
        if (!dateString) return "";
        return new Date(dateString).toLocaleDateString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        });
    }

    // ── Lifecycle-Funktionen ──────────────────────────────────────────────
    async function archive() {
        archiveLoading = true;
        try {
            node = await updateContextNode(node.id, { status: "archived" });
            showArchiveConfirm = false;
            archivedRefs = [];
        } catch (e) {
            errors.general = e.message;
        } finally {
            archiveLoading = false;
        }
    }

    async function restore() {
        node = await updateContextNode(node.id, { status: "active" });
    }

    async function confirmCopy() {
        copyLoading = true;
        copyError = null;
        try {
            const created = await copyContextNode(node.id, {
                schuljahr: copySchuljahr || null,
                valid_until: copyValidUntil || null,
            });
            showCopyDialog = false;
            goto(`/knowledge/${created.id}`);
        } catch (e) {
            copyError = e.message;
        } finally {
            copyLoading = false;
        }
    }
</script>

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2
         hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>
<div class="h-full overflow-y-auto p-6 max-w-2xl">
    {#if loadingNode}
        <div
            class="py-8 text-center text-sm text-light-tx-2 dark:text-dark-tx-2"
        >
            Wird geladen…
        </div>
    {:else if errors.general && !node}
        <div class="py-8 text-center text-sm text-light-re dark:text-dark-re">
            {errors.general}
        </div>
    {:else}
        <div class="mb-4">
            <div class="flex items-center gap-3">
                <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
                    Knoten bearbeiten
                </h1>
                {#if node}
                    <span class="text-xs px-2 py-0.5 rounded-full
                        {node.status === 'active'
                            ? 'bg-light-gr/20 dark:bg-dark-gr/20 text-light-gr dark:text-dark-gr'
                            : 'bg-light-ye/20 dark:bg-dark-ye/20 text-light-ye dark:text-dark-ye'}">
                        {node.status === 'active' ? 'Aktiv' : 'Archiviert'}
                    </span>
                {/if}
            </div>
            {#if node}
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    Erstellt: {formatDate(node.created_at)}
                    {#if node.updated_at !== node.created_at}
                        · Aktualisiert: {formatDate(node.updated_at)}
                    {/if}
                </p>
                <a
                    href="/knowledge/{$page.params.id}/graph"
                    class="text-sm text-primary dark:text-dark-bl underline mt-1 inline-block"
                >
                    Graphansicht öffnen →
                </a>
            {/if}
        </div>

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
                            {#if ref.suggested_successor_id}
                                <span
                                    class="ml-2 text-xs text-light-tx-2 dark:text-dark-tx-2"
                                >
                                    → Möglicher Nachfolger:
                                    <a
                                        href="/knowledge/{ref.suggested_successor_id}"
                                        class="underline hover:text-primary dark:hover:text-primary-dark"
                                    >
                                        Knoten anzeigen
                                    </a>
                                </span>
                            {/if}
                        </li>
                    {/each}
                </ul>
            </div>
        {/if}

        <form
            onsubmit={(e) => {
                e.preventDefault();
                save();
            }}
            class="space-y-6"
        >
            <!-- Titel -->
            <div>
                <label
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                >
                    Titel *
                </label>
                <input
                    type="text"
                    bind:value={title}
                    disabled={!canEdit}
                    class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
               focus:outline-none focus:border-primary dark:focus:border-primary-dark
               disabled:opacity-50 disabled:cursor-not-allowed"
                    placeholder="z. B. Lehrplan Informatik Sek II"
                />
                {#if errors.title}
                    <p class="mt-1 text-sm text-light-re dark:text-dark-re">
                        {errors.title}
                    </p>
                {/if}
            </div>

            <!-- Kategorie -->
            <div>
                <label
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                >
                    Kategorie *
                </label>
                <select
                    bind:value={category}
                    onchange={() => {
                        contentType = "";
                    }}
                    disabled={!canEdit}
                    class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
               bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
               disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    <option value="">-- Bitte wählen --</option>
                    {#each Object.entries(CATEGORY_LABELS) as [cat, label]}
                        <option value={cat}>{label}</option>
                    {/each}
                </select>
                {#if errors.category}
                    <p class="mt-1 text-sm text-light-re dark:text-dark-re">
                        {errors.category}
                    </p>
                {/if}
            </div>

            <!-- Typ -->
            {#if category}
                <div>
                    <label
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                    >
                        Typ *
                    </label>
                    <select
                        bind:value={contentType}
                        disabled={!canEdit}
                        class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                   disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <option value="">-- Bitte wählen --</option>
                        {#each contentTypeOptions as ct}
                            <option value={ct}>{ct}</option>
                        {/each}
                    </select>
                    {#if errors.contentType}
                        <p class="mt-1 text-sm text-light-re dark:text-dark-re">
                            {errors.contentType}
                        </p>
                    {/if}
                </div>
            {/if}

            <!-- Inhalt -->
            {#if contentType}
                <div>
                    <label
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                    >
                        Inhalt
                    </label>
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-1">
                        Markdown wird unterstützt
                    </p>
                    <textarea
                        bind:value={content}
                        rows="6"
                        disabled={!canEdit}
                        class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                   focus:outline-none focus:border-primary dark:focus:border-primary-dark
                   disabled:opacity-50 disabled:cursor-not-allowed"
                        placeholder="Beschreibe den Knoten (Markdown möglich)..."
                    ></textarea>
                </div>
            {/if}

            <!-- Strukturierte Metadaten: Funktion -->
            {#if category === "concept" && contentType === "funktion"}
                <div
                    class="border border-light-ui-3 dark:border-dark-ui-3 rounded-lg p-4"
                >
                    <h3
                        class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-3"
                    >
                        Funktionssignatur
                    </h3>
                    <div class="space-y-3">
                        <div>
                            <label
                                class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                            >
                                Funktionsname
                            </label>
                            <input
                                type="text"
                                bind:value={signatur.name}
                                disabled={!canEdit}
                                class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       disabled:opacity-50 disabled:cursor-not-allowed"
                                placeholder="z. B. berechneDurchschnitt"
                            />
                        </div>
                        <div>
                            <label
                                class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                            >
                                Sprache
                            </label>
                            <select
                                bind:value={signatur.sprache}
                                disabled={!canEdit}
                                class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <option value="arduino_cpp">Arduino C++</option>
                                <option value="python">Python</option>
                                <option value="javascript">JavaScript</option>
                            </select>
                        </div>
                        <div>
                            <label
                                class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                            >
                                Parameter
                            </label>
                            {#if signatur.parameter.length === 0}
                                <p
                                    class="text-xs text-light-tx-3 dark:text-dark-tx-3 italic mb-2"
                                >
                                    Keine Parameter definiert
                                </p>
                            {/if}
                            {#each signatur.parameter as param, index (index)}
                                <div class="flex gap-2 items-end mb-2">
                                    <input
                                        type="text"
                                        value={param.name}
                                        oninput={(e) =>
                                            updateParameter(
                                                index,
                                                "name",
                                                e.target.value,
                                            )}
                                        disabled={!canEdit}
                                        class="flex-1 px-2 py-1 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                           disabled:opacity-50 disabled:cursor-not-allowed"
                                        placeholder="Name"
                                    />
                                    <input
                                        type="text"
                                        value={param.typ}
                                        oninput={(e) =>
                                            updateParameter(
                                                index,
                                                "typ",
                                                e.target.value,
                                            )}
                                        disabled={!canEdit}
                                        class="flex-1 px-2 py-1 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                           disabled:opacity-50 disabled:cursor-not-allowed"
                                        placeholder="Typ"
                                    />
                                    <input
                                        type="text"
                                        value={param.beschreibung}
                                        oninput={(e) =>
                                            updateParameter(
                                                index,
                                                "beschreibung",
                                                e.target.value,
                                            )}
                                        disabled={!canEdit}
                                        class="flex-1 px-2 py-1 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                           disabled:opacity-50 disabled:cursor-not-allowed"
                                        placeholder="Beschreibung"
                                    />
                                    {#if canEdit}
                                        <button
                                            type="button"
                                            onclick={() =>
                                                removeParameter(index)}
                                            class="px-2 py-1 text-xs text-light-re dark:text-dark-re
                             hover:bg-light-re/10 dark:hover:bg-dark-re/10 rounded"
                                        >
                                            ×
                                        </button>
                                    {/if}
                                </div>
                            {/each}
                            {#if canEdit}
                                <button
                                    type="button"
                                    onclick={addParameter}
                                    class="text-xs text-primary dark:text-dark-bl underline"
                                >
                                    + Parameter hinzufügen
                                </button>
                            {/if}
                        </div>
                        <div>
                            <label
                                class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                            >
                                Rückgabetyp
                            </label>
                            <input
                                type="text"
                                bind:value={signatur.rueckgabe.typ}
                                disabled={!canEdit}
                                class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       disabled:opacity-50 disabled:cursor-not-allowed"
                                placeholder="z. B. int"
                            />
                        </div>
                        <div>
                            <label
                                class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                            >
                                Rückgabebeschreibung
                            </label>
                            <input
                                type="text"
                                bind:value={signatur.rueckgabe.beschreibung}
                                disabled={!canEdit}
                                class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       disabled:opacity-50 disabled:cursor-not-allowed"
                                placeholder="z. B. Der berechnete Durchschnittswert"
                            />
                        </div>
                    </div>
                </div>
            {/if}

            <!-- Strukturierte Metadaten: Bauteil -->
            {#if category === "concept" && contentType === "bauteil"}
                <div
                    class="border border-light-ui-3 dark:border-dark-ui-3 rounded-lg p-4"
                >
                    <h3
                        class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-3"
                    >
                        Schaltzeichen
                    </h3>
                    <div class="space-y-3">
                        <div>
                            <label
                                class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                            >
                                Beschreibung
                            </label>
                            <textarea
                                bind:value={schaltzeichen.beschreibung}
                                rows="2"
                                disabled={!canEdit}
                                class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       disabled:opacity-50 disabled:cursor-not-allowed"
                                placeholder="Beschreibung des Bauteils für das Embedding"
                            ></textarea>
                        </div>
                        <div>
                            <label
                                class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                            >
                                Norm
                            </label>
                            <input
                                type="text"
                                bind:value={schaltzeichen.norm}
                                disabled={!canEdit}
                                class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       disabled:opacity-50 disabled:cursor-not-allowed"
                                placeholder="z. B. DIN EN IEC 60617"
                            />
                        </div>
                        <div>
                            <label
                                class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                            >
                                Kennung
                            </label>
                            <input
                                type="text"
                                bind:value={schaltzeichen.kennung}
                                disabled={!canEdit}
                                class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       disabled:opacity-50 disabled:cursor-not-allowed"
                                placeholder="z. B. R, LED, U"
                            />
                        </div>
                        <div>
                            <label
                                class="block text-sm font-medium text-light-tx-2 dark:text-dark-tx-2 mb-1"
                            >
                                SVG (optional)
                            </label>
                            <textarea
                                bind:value={schaltzeichen.svg}
                                rows="4"
                                disabled={!canEdit}
                                class="w-full px-2 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       font-family:monospace disabled:opacity-50 disabled:cursor-not-allowed"
                                placeholder="Inline SVG-Code"
                            ></textarea>
                        </div>
                    </div>
                </div>
            {/if}

            <!-- Generisches JSON-Feld für andere Typen -->
            {#if category && contentType && !["funktion", "bauteil"].includes(contentType)}
                <div>
                    <label
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                    >
                        Metadaten (JSON)
                    </label>
                    <textarea
                        bind:value={metadata}
                        rows="4"
                        disabled={!canEdit}
                        class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                   font-family:monospace disabled:opacity-50 disabled:cursor-not-allowed"
                        placeholder={{}}
                    ></textarea>
                </div>
            {/if}

            <!-- erweitere Einstellungen -->
            <details
                class="border-t border-light-ui-3 dark:border-dark-ui-3 pt-4"
            >
                <summary
                    class="cursor-pointer text-sm font-medium text-light-tx-2 dark:text-dark-tx-2"
                >
                    Erweiterte Einstellungen
                </summary>
                <div class="mt-4 space-y-4">
                    <!-- Lese-Scope -->
                    <div>
                        <label
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                        >
                            Lese-Sichtbarkeit
                        </label>
                        <select
                            bind:value={readScope}
                            disabled={!canEdit}
                            class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                     disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <option value="private">Privat</option>
                            <option value="group">Gruppe</option>
                            <option value="subject">Fach</option>
                            <option value="school">Schule</option>
                        </select>
                    </div>

                    <!-- Gruppen-Auswahl für read_scope -->
                    {#if ["subject", "group"].includes(readScope)}
                        <div>
                            <label
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                            >
                                {readScope === "group"
                                    ? "Gruppe"
                                    : "Fachgruppe"}
                            </label>
                            <select
                                bind:value={readScopeGroupId}
                                disabled={!canEdit}
                                class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <option value={null}>-- Keine Auswahl --</option
                                >
                                {#each groupOptions as group}
                                    <option value={group.id}
                                        >{group.name}</option
                                    >
                                {/each}
                            </select>
                        </div>
                    {/if}

                    <!-- Schreib-Scope -->
                    <div>
                        <label
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                        >
                            Schreib-Sichtbarkeit
                        </label>
                        <select
                            bind:value={writeScope}
                            disabled={!canEdit}
                            class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                     disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {#each writeScopes as scope}
                                <option value={scope}>{scope}</option>
                            {/each}
                        </select>
                    </div>

                    <!-- Gruppen-Auswahl für write_scope -->
                    {#if ["subject", "group"].includes(writeScope)}
                        <div>
                            <label
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                            >
                                {writeScope === "group"
                                    ? "Gruppe"
                                    : "Fachgruppe"}
                            </label>
                            <select
                                bind:value={writeScopeGroupId}
                                disabled={!canEdit}
                                class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <option value={null}>-- Keine Auswahl --</option
                                >
                                {#each groupOptions as group}
                                    <option value={group.id}
                                        >{group.name}</option
                                    >
                                {/each}
                            </select>
                        </div>
                    {/if}

                    <!-- Ablaufdatum -->
                    <div>
                        <label
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                        >
                            Ablaufdatum
                        </label>
                        <div class="flex gap-2 items-center">
                            <input
                                type="date"
                                bind:value={validUntil}
                                disabled={!canEdit}
                                class="px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                       disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                            {#if canEdit}
                                <button
                                    type="button"
                                    onclick={() => {
                                        validUntil = schuljahresEnde();
                                    }}
                                    class="text-xs px-2 py-1.5 rounded-md bg-light-ui-2 dark:bg-dark-ui-2
                         text-light-tx dark:text-dark-tx hover:bg-light-ui-3 dark:hover:bg-dark-ui-3"
                                >
                                    Schuljahresende (31.07.)
                                </button>
                            {/if}
                        </div>
                    </div>

                    <!-- Schuljahr -->
                    <div>
                        <label
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx mb-1"
                        >
                            Schuljahr
                        </label>
                        <input
                            type="text"
                            bind:value={schuljahr}
                            disabled={!canEdit}
                            class="w-full px-3 py-2 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx
                     disabled:opacity-50 disabled:cursor-not-allowed"
                            placeholder="z. B. 2024/2025"
                        />
                    </div>
                </div>
            </details>

            <!-- Buttons -->
            <div class="flex gap-3 pt-4">
                {#if canEdit}
                    <button
                        type="submit"
                        disabled={saving}
                        class="px-4 py-2 text-sm rounded-md bg-primary dark:bg-primary-dark
                   text-white font-medium hover:opacity-90 transition-opacity
                   disabled:opacity-50"
                    >
                        {saving ? "Speichern…" : "Speichern"}
                    </button>
                {:else}
                    <p
                        class="text-sm text-light-tx-2 dark:text-dark-tx-2 italic"
                    >
                        Du kannst diesen Knoten nur lesen.
                    </p>
                {/if}
            </div>

            <!-- Lifecycle-Aktionen -->
            {#if canEdit && node}
                <div
                    class="mt-6 pt-6 border-t border-light-ui-2 dark:border-dark-ui-2 flex flex-wrap gap-3"
                >
                    {#if node.status === "active"}
                        <button
                            onclick={() => {
                                showArchiveConfirm = true;
                            }}
                            class="text-sm px-3 py-1.5 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     text-light-tx-2 dark:text-dark-tx-2
                     hover:border-light-re dark:hover:border-dark-re
                     hover:text-light-re dark:hover:text-dark-re transition-colors"
                        >
                            Archivieren
                        </button>
                    {:else}
                        <button
                            onclick={restore}
                            class="text-sm px-3 py-1.5 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     text-light-tx-2 dark:text-dark-tx-2
                     hover:border-primary dark:hover:border-primary-dark transition-colors"
                        >
                            Wiederherstellen
                        </button>
                    {/if}

                    <button
                        onclick={() => {
                            copySchuljahr = schuljahr;
                            copyValidUntil = "";
                            showCopyDialog = true;
                        }}
                        class="text-sm px-3 py-1.5 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                   text-light-tx-2 dark:text-dark-tx-2
                   hover:border-primary dark:hover:border-primary-dark transition-colors"
                    >
                        Als Vorlage kopieren
                    </button>
                </div>
            {/if}

            <!-- Erfolgsmeldung -->
            {#if savedMessage}
                <div
                    class="mt-4 p-3 text-sm text-green-700 dark:text-green-400
                    bg-green-100 dark:bg-green-900/30 rounded-md"
                >
                    {savedMessage}
                </div>
            {/if}

            <!-- Fehler -->
            {#if errors.general}
                <div
                    class="mt-4 p-3 text-sm text-light-re dark:text-dark-re
                    bg-light-re/10 dark:bg-dark-re/10 rounded-md"
                >
                    {errors.general}
                </div>
            {/if}

            <!-- Bestätigungsdialog: Archivieren -->
            {#if showArchiveConfirm}
                <div
                    class="mt-3 px-4 py-3 rounded-md border border-light-ye dark:border-dark-ye
                    bg-light-ye/10 dark:bg-dark-ye/10 text-sm"
                >
                    <p class="text-light-tx dark:text-dark-tx mb-3">
                        Dieser Knoten wird für Assistenten und Schüler
                        unsichtbar. Kanten und Konfigurationen bleiben erhalten.
                        Fortfahren?
                    </p>
                    <div class="flex gap-2">
                        <button
                            onclick={archive}
                            disabled={archiveLoading}
                            class="px-3 py-1.5 rounded-md bg-light-re dark:bg-dark-re text-white text-sm
                     hover:opacity-90 transition-opacity disabled:opacity-50"
                        >
                            {archiveLoading
                                ? "Wird archiviert…"
                                : "Ja, archivieren"}
                        </button>
                        <button
                            onclick={() => {
                                showArchiveConfirm = false;
                            }}
                            class="px-3 py-1.5 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     text-sm text-light-tx-2 dark:text-dark-tx-2 hover:border-primary transition-colors"
                        >
                            Abbrechen
                        </button>
                    </div>
                </div>
            {/if}

            <!-- Dialog: Vorlage kopieren -->
            {#if showCopyDialog}
                <div
                    class="mt-3 px-4 py-4 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                    bg-light-bg-2 dark:bg-dark-bg-2 text-sm space-y-3"
                >
                    <p class="font-medium text-light-tx dark:text-dark-tx">
                        Kopie erstellen
                    </p>

                    <label class="block">
                        <span
                            class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-1 block"
                            >Schuljahr</span
                        >
                        <input
                            type="text"
                            bind:value={copySchuljahr}
                            placeholder="z. B. 2026/27"
                            class="w-full px-3 py-1.5 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx text-sm
                     focus:outline-none focus:border-primary dark:focus:border-primary-dark"
                        />
                    </label>

                    <label class="block">
                        <span
                            class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-1 block"
                        >
                            Ablaufdatum (leer = permanent)
                        </span>
                        <input
                            type="date"
                            bind:value={copyValidUntil}
                            class="px-3 py-1.5 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx text-sm
                     focus:outline-none focus:border-primary dark:focus:border-primary-dark"
                        />
                    </label>

                    {#if copyError}
                        <p class="text-light-re dark:text-dark-re text-xs">
                            {copyError}
                        </p>
                    {/if}

                    <div class="flex gap-2 pt-1">
                        <button
                            onclick={confirmCopy}
                            disabled={copyLoading}
                            class="px-3 py-1.5 rounded-md bg-primary dark:bg-primary-dark text-white text-sm
                     hover:opacity-90 transition-opacity disabled:opacity-50"
                        >
                            {copyLoading ? "Wird kopiert…" : "Kopie erstellen"}
                        </button>
                        <button
                            onclick={() => {
                                showCopyDialog = false;
                                copyError = null;
                            }}
                            class="px-3 py-1.5 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                     text-sm text-light-tx-2 dark:text-dark-tx-2 hover:border-primary transition-colors"
                        >
                            Abbrechen
                        </button>
                    </div>
                </div>
            {/if}
        </form>
    {/if}
</div>
