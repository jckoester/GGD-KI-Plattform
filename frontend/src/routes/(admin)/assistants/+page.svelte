<script>
    import { onMount } from "svelte";
    import {
        Bot,
        Plus,
        Pencil,
        Trash2,
        Eye,
        EyeOff,
        Download,
        Upload,
        X,
        Check,
        Loader2,
        ChevronDown,
        AlertCircle,
        FileText,
    } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";
    import {
        getAdminAssistants,
        createAssistant,
        updateAssistant,
        deleteAssistant,
        activateAssistant,
        deactivateAssistant,
        exportAssistant,
        importAssistant,
        getModels,
        ApiError,
    } from "$lib/api.js";

    let availableModels = $state([]); // string[] — aus /api/models

    // State-Variablen
    let assistants = $state([]); // AssistantResponse[]
    let total = $state(0);
    let loading = $state(true);
    let error = $state(null);

    // Filter
    let filterStatus = $state(""); // '' | 'draft' | 'active' | 'disabled' | 'archived'
    let filterAudience = $state(""); // '' | 'student' | 'teacher' | 'all'

    // Formular-Panel
    let panelOpen = $state(false);
    let editTarget = $state(null); // null = Neu anlegen, AssistantResponse = Bearbeiten
    let form = $state(emptyForm());
    let saving = $state(false);
    let formError = $state(null);

    // Import
    let importOpen = $state(false);
    let importFile = $state(null);
    let importModelOverride = $state("");
    let importing = $state(false);
    let importError = $state(null);

    // Löschen
    let deleteTarget = $state(null); // AssistantResponse | null
    let deleting = $state(false);
    let deleteError = $state(null);

    // Success Banner
    let successMessage = $state(null);

    // Übersetzungen für UI
    const AUDIENCE_LABELS = {
        student: "Schüler:innen",
        teacher: "Lehrkräfte",
        all: "Alle",
    };
    const SCOPE_LABELS = {
        private: "Privat (Entwurf)",
        teachers: "Lehrkräfte",
        all_students: "Alle Schüler:innen",
        all: "Alle",
    };

    // Status-Badge-Farben
    const STATUS_CLASS = {
        draft: "bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2",
        active: "bg-light-gr/20 dark:bg-dark-gr/20 text-light-gr dark:text-dark-gr",
        disabled:
            "bg-light-ye/20 dark:bg-dark-ye/20 text-light-ye dark:text-dark-ye",
        archived:
            "bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2",
    };
    const STATUS_LABEL = {
        draft: "Entwurf",
        active: "Aktiv",
        disabled: "Deaktiviert",
        archived: "Archiviert",
    };

    // Formular-Felder
    function emptyForm() {
        return {
            name: "",
            description: "",
            subject_id: null,
            system_prompt: "",
            model: "",
            temperature: null,
            max_tokens: null,
            audience: "student",
            scope: "private",
            min_grade: null,
            max_grade: null,
            tags: "",
            icon: null,
            available_from: "",
            available_until: "",
            sort_order: 0,
        };
    }

    // Laden und Filtern
    async function reload() {
        loading = true;
        error = null;
        try {
            const params = {};
            if (filterStatus) params.status = filterStatus;
            if (filterAudience) params.audience = filterAudience;
            const result = await getAdminAssistants(params);
            assistants = result.items;
            total = result.total;
        } catch (e) {
            error = e.message;
        } finally {
            loading = false;
        }
    }

    // Panel öffnen (neu oder bearbeiten)
    function openPanel(target = null) {
        editTarget = target;
        if (target) {
            form = {
                name: target.name || "",
                description: target.description || "",
                subject_id: target.subject_id || null,
                system_prompt: target.system_prompt || "",
                model: target.model || "",
                temperature:
                    target.temperature !== null &&
                    target.temperature !== undefined
                        ? String(target.temperature)
                        : null,
                max_tokens:
                    target.max_tokens !== null &&
                    target.max_tokens !== undefined
                        ? String(target.max_tokens)
                        : null,
                audience: target.audience || "student",
                scope: target.scope || "private",
                min_grade:
                    target.min_grade !== null && target.min_grade !== undefined
                        ? String(target.min_grade)
                        : null,
                max_grade:
                    target.max_grade !== null && target.max_grade !== undefined
                        ? String(target.max_grade)
                        : null,
                tags: (target.tags ?? []).join(", "),
                icon: target.icon || null,
                available_from: target.available_from
                    ? target.available_from.split("T")[0]
                    : "",
                available_until: target.available_until
                    ? target.available_until.split("T")[0]
                    : "",
                sort_order: target.sort_order ?? 0,
            };
        } else {
            form = emptyForm();
        }
        panelOpen = true;
        formError = null;
    }

    // Panel schließen
    function closePanel() {
        panelOpen = false;
        formError = null;
    }

    // Speichern-Logik
    async function save() {
        saving = true;
        formError = null;
        const payload = {
            ...form,
            tags:
                form.tags
                    .split(",")
                    .map((t) => t.trim())
                    .filter(Boolean) || null,
            temperature: form.temperature ? parseFloat(form.temperature) : null,
            max_tokens: form.max_tokens ? parseInt(form.max_tokens) : null,
            min_grade: form.min_grade ? parseInt(form.min_grade) : null,
            max_grade: form.max_grade ? parseInt(form.max_grade) : null,
            available_from: form.available_from || null,
            available_until: form.available_until || null,
            sort_order: parseInt(form.sort_order) || 0,
        };
        try {
            if (editTarget) {
                await updateAssistant(editTarget.id, payload);
                successMessage = "Assistent wurde erfolgreich aktualisiert.";
            } else {
                await createAssistant(payload);
                successMessage = "Assistent wurde erfolgreich angelegt.";
            }
            panelOpen = false;
            await reload();
        } catch (e) {
            formError = e.message;
        } finally {
            saving = false;
        }
    }

    // Import-Dialog
    function openImport() {
        importOpen = true;
        importFile = null;
        importModelOverride = "";
        importError = null;
    }

    function closeImport() {
        importOpen = false;
        importError = null;
    }

    async function doImport() {
        if (!importFile) return;
        importing = true;
        importError = null;
        try {
            await importAssistant(importFile, importModelOverride || null);
            importOpen = false;
            successMessage = "Assistent wurde erfolgreich importiert.";
            await reload();
        } catch (e) {
            importError = e.message;
        } finally {
            importing = false;
        }
    }

    function handleFileDrop(event) {
        event.preventDefault();
        const files = event.dataTransfer?.files;
        if (files && files.length > 0) {
            importFile = files[0];
        }
    }

    function handleFileSelect(event) {
        const files = event.target.files;
        if (files && files.length > 0) {
            importFile = files[0];
        }
    }

    // Export
    async function doExport(assistant) {
        const slug = assistant.name.toLowerCase().replace(/\s+/g, "-");
        await exportAssistant(assistant.id, `${slug}.yaml`);
    }

    // Löschen-Dialog
    function openDelete(target) {
        deleteTarget = target;
        deleteError = null;
    }

    function closeDelete() {
        deleteTarget = null;
        deleteError = null;
    }

    async function confirmDelete() {
        if (!deleteTarget) return;
        deleting = true;
        deleteError = null;
        try {
            await deleteAssistant(deleteTarget.id);
            deleteTarget = null;
            successMessage = "Assistent wurde erfolgreich gelöscht.";
            await reload();
        } catch (e) {
            deleteError = e.message;
        } finally {
            deleting = false;
        }
    }

    // Aktivieren/Deaktivieren
    async function toggleActivate(assistant) {
        try {
            if (assistant.status === "active") {
                await deactivateAssistant(assistant.id);
                successMessage = "Assistent wurde deaktiviert.";
            } else {
                await activateAssistant(assistant.id);
                successMessage = "Assistent wurde aktiviert.";
            }
            await reload();
        } catch (e) {
            error = e.message;
        }
    }

    // Aktionsschaltflächen pro Zeile
    function getActions(assistant) {
        const actions = [];
        actions.push({
            label: "Bearbeiten",
            action: () => openPanel(assistant),
            icon: Pencil,
        });
        if (assistant.status === "active") {
            actions.push({
                label: "Deaktivieren",
                action: () => toggleActivate(assistant),
                icon: EyeOff,
            });
        } else if (
            assistant.status === "draft" ||
            assistant.status === "disabled" ||
            assistant.status === "archived"
        ) {
            if (assistant.status !== "active") {
                actions.push({
                    label: "Aktivieren",
                    action: () => toggleActivate(assistant),
                    icon: Eye,
                });
            }
        }
        actions.push({
            label: "Exportieren",
            action: () => doExport(assistant),
            icon: Download,
        });
        if (assistant.status !== "active") {
            actions.push({
                label: "Löschen",
                action: () => openDelete(assistant),
                icon: Trash2,
            });
        }
        return actions;
    }

    // Lebenszyklus
    onMount(async () => {
        const [, models] = await Promise.allSettled([reload(), getModels()]);
        if (models.status === "fulfilled") {
            availableModels = models.value.models.map((m) => m.id);
        }
    });
    $effect(() => {
        filterStatus;
        filterAudience;
        reload();
    });

    $effect(() => {
        if (successMessage) {
            const t = setTimeout(() => (successMessage = null), 3000);
            return () => clearTimeout(t);
        }
    });
</script>

<svelte:head>
    <title>Assistenten</title>
</svelte:head>

<div class="h-full flex flex-col">
    <!-- Kopfzeile -->
    <div
        class="flex items-center justify-between p-6 border-b border-light-ui-3 dark:border-dark-ui-3"
    >
        <div class="flex items-center gap-2">
            <Bot class="w-6 h-6 text-light-bl dark:text-dark-bl" />
            <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
                Assistenten
            </h1>
        </div>
        <div class="flex items-center gap-2">
            <button
                onclick={openImport}
                class="px-4 py-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors flex items-center gap-2"
            >
                <Upload class="w-4 h-4" />
                Importieren
            </button>
            <button
                onclick={() => openPanel()}
                class="px-4 py-2 bg-primary text-white rounded-lg
                       hover:bg-primary-dark transition-colors flex items-center gap-2"
            >
                <Plus class="w-4 h-4" />
                Neu anlegen
            </button>
        </div>
    </div>

    <!-- Filterzeile -->
    <div class="p-6 border-b border-light-ui-3 dark:border-dark-ui-3">
        <div class="flex flex-wrap items-center gap-4">
            <div class="flex items-center gap-2">
                <span class="text-sm text-light-tx-2 dark:text-dark-tx-2"
                    >Status</span
                >
                <select
                    bind:value={filterStatus}
                    class="rounded border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                           px-2 py-1 text-sm"
                >
                    <option value="">Alle</option>
                    <option value="draft">Entwurf</option>
                    <option value="active">Aktiv</option>
                    <option value="disabled">Deaktiviert</option>
                    <option value="archived">Archiviert</option>
                </select>
            </div>
            <div class="flex items-center gap-2">
                <span class="text-sm text-light-tx-2 dark:text-dark-tx-2"
                    >Zielgruppe</span
                >
                <select
                    bind:value={filterAudience}
                    class="rounded border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                           px-2 py-1 text-sm"
                >
                    <option value="">Alle</option>
                    <option value="student">Schüler:innen</option>
                    <option value="teacher">Lehrkräfte</option>
                    <option value="all">Alle</option>
                </select>
            </div>
            <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                {total} Assistenten
            </span>
        </div>
    </div>

    <!-- Fehler und Ladezustand -->
    {#if error}
        <div class="p-6">
            <ErrorBanner message={error} />
        </div>
    {/if}

    {#if loading}
        <div class="p-6">
            <LoadingBanner />
        </div>
    {:else if !error}
        <!-- Tabelle -->
        <div class="p-6 flex-1 overflow-y-auto">
            {#if successMessage}
                <div class="mb-4">
                    <SuccessBanner
                        message={successMessage}
                        onclose={() => (successMessage = null)}
                    />
                </div>
            {/if}

            {#if assistants.length === 0}
                <div
                    class="text-center text-light-tx-2 dark:text-dark-tx-2 py-8"
                >
                    <p>Keine Assistenten gefunden.</p>
                </div>
            {:else}
                <div class="overflow-x-auto">
                    <table class="w-full text-sm">
                        <thead
                            class="text-left text-light-tx-2 dark:text-dark-tx-2"
                        >
                            <tr
                                class="border-b border-light-ui-3 dark:border-dark-ui-3"
                            >
                                <th class="pb-3 pr-4 font-medium">Name</th>
                                <th class="pb-3 pr-4 font-medium">Zielgruppe</th
                                >
                                <th class="pb-3 pr-4 font-medium">Status</th>
                                <th class="pb-3 pr-4 font-medium">Aktionen</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each assistants as assistant}
                                <tr
                                    class="border-b border-light-ui-3 dark:border-dark-ui-3"
                                >
                                    <td class="py-3 pr-4">
                                        <div
                                            class="font-medium text-light-tx dark:text-dark-tx"
                                        >
                                            {assistant.name}
                                        </div>
                                        {#if assistant.description}
                                            <div
                                                class="text-xs text-light-tx-2 dark:text-dark-tx-2 truncate max-w-[200px]"
                                            >
                                                {assistant.description}
                                            </div>
                                        {/if}
                                    </td>
                                    <td class="py-3 pr-4">
                                        {AUDIENCE_LABELS[assistant.audience] ||
                                            assistant.audience}
                                    </td>
                                    <td class="py-3 pr-4">
                                        <span
                                            class="px-2 py-1 rounded-full text-xs {STATUS_CLASS[
                                                assistant.status
                                            ] || STATUS_CLASS.draft}"
                                        >
                                            {STATUS_LABEL[assistant.status] ||
                                                assistant.status}
                                        </span>
                                    </td>
                                    <td class="py-3 pr-4">
                                        <div class="flex items-center gap-2">
                                            {#each getActions(assistant) as action}
                                                <button
                                                    onclick={action.action}
                                                    title={action.label}
                                                    class="p-1.5 rounded-lg hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                                                           text-light-tx-2 dark:text-dark-tx-2 transition-colors"
                                                >
                                                    <action.icon
                                                        class="w-4 h-4"
                                                    />
                                                </button>
                                            {/each}
                                        </div>
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            {/if}
        </div>
    {/if}
</div>

<!-- Formular-Panel (Slide-in von rechts) -->
{#if panelOpen}
    <div class="fixed inset-0 bg-black/50 z-40" onclick={closePanel} />
    <div
        class="fixed top-0 right-0 h-full w-full max-w-2xl bg-light-bg dark:bg-dark-bg shadow-2xl z-50 transform translate-x-0 transition-transform"
    >
        <div
            class="flex items-center justify-between p-4 border-b border-light-ui-3 dark:border-dark-ui-3"
        >
            <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx">
                {editTarget
                    ? "Assistent bearbeiten"
                    : "Neuen Assistenten anlegen"}
            </h2>
            <button
                onclick={closePanel}
                class="p-1 rounded-lg hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
            >
                <X class="w-5 h-5 text-light-tx-2 dark:text-dark-tx-2" />
            </button>
        </div>

        <div class="p-4 space-y-4 max-h-[calc(100vh-120px)] overflow-y-auto">
            {#if formError}
                <ErrorBanner message={formError} />
            {/if}

            <div class="space-y-2">
                <label
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                >
                    Name *
                </label>
                <input
                    bind:value={form.name}
                    type="text"
                    placeholder="Name des Assistenten"
                    class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                           px-3 py-2"
                />
            </div>

            <div class="space-y-2">
                <label
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                >
                    Beschreibung
                </label>
                <textarea
                    bind:value={form.description}
                    rows="2"
                    placeholder="Kurze Beschreibung des Assistenten"
                    class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                           px-3 py-2 resize-none"
                ></textarea>
            </div>

            <div class="space-y-2">
                <label
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                >
                    System-Prompt *
                </label>
                <textarea
                    bind:value={form.system_prompt}
                    rows="8"
                    placeholder="System-Prompt für den Assistenten..."
                    class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                           px-3 py-2 resize-none font-mono text-sm"
                ></textarea>
            </div>

            <div class="space-y-2">
                <label
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                >
                    Modell *
                </label>
                {#if availableModels.length > 0}
                    <select
                        bind:value={form.model}
                        class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                               px-3 py-2"
                    >
                        <option value="">— Modell auswählen —</option>
                        {#each availableModels as modelId}
                            <option value={modelId}>{modelId}</option>
                        {/each}
                        {#if form.model && !availableModels.includes(form.model)}
                            <option value={form.model}
                                >{form.model} (nicht verfügbar)</option
                            >
                        {/if}
                    </select>
                {:else}
                    <input
                        bind:value={form.model}
                        type="text"
                        placeholder="openai/gpt-4o-mini"
                        class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                               px-3 py-2"
                    />
                {/if}
            </div>

            <div class="grid grid-cols-2 gap-4">
                <div class="space-y-2">
                    <label
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                    >
                        Temperatur
                    </label>
                    <input
                        bind:value={form.temperature}
                        type="number"
                        min="0"
                        max="2"
                        step="0.1"
                        placeholder="0.7"
                        class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                               px-3 py-2"
                    />
                </div>
                <div class="space-y-2">
                    <label
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                    >
                        Max. Tokens
                    </label>
                    <input
                        bind:value={form.max_tokens}
                        type="number"
                        min="1"
                        placeholder="1000"
                        class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                               px-3 py-2"
                    />
                </div>
            </div>

            <div class="grid grid-cols-2 gap-4">
                <div class="space-y-2">
                    <label
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                    >
                        Zielgruppe
                    </label>
                    <select
                        bind:value={form.audience}
                        class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                               px-3 py-2"
                    >
                        <option value="student">Schüler:innen</option>
                        <option value="teacher">Lehrkräfte</option>
                        <option value="all">Alle</option>
                    </select>
                </div>
                <div class="space-y-2">
                    <label
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                    >
                        Sichtbarkeit
                    </label>
                    <select
                        bind:value={form.scope}
                        class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                               px-3 py-2"
                    >
                        <option value="private">Privat (Entwurf)</option>
                        <option value="teachers">Lehrkräfte</option>
                        <option value="all_students">Alle Schüler:innen</option>
                        <option value="all">Alle</option>
                    </select>
                </div>
            </div>

            <div class="grid grid-cols-2 gap-4">
                <div class="space-y-2">
                    <label
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                    >
                        Min. Jahrgang
                    </label>
                    <input
                        bind:value={form.min_grade}
                        type="number"
                        min="1"
                        max="13"
                        placeholder="5"
                        class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                               px-3 py-2"
                    />
                </div>
                <div class="space-y-2">
                    <label
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                    >
                        Max. Jahrgang
                    </label>
                    <input
                        bind:value={form.max_grade}
                        type="number"
                        min="1"
                        max="13"
                        placeholder="10"
                        class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                               px-3 py-2"
                    />
                </div>
            </div>

            <div class="space-y-2">
                <label
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                >
                    Tags (kommagetrennt)
                </label>
                <input
                    bind:value={form.tags}
                    type="text"
                    placeholder="mathe, physik, hilfe"
                    class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                           px-3 py-2"
                />
            </div>

            <div class="grid grid-cols-2 gap-4">
                <div class="space-y-2">
                    <label
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                    >
                        Verfügbar von
                    </label>
                    <input
                        bind:value={form.available_from}
                        type="date"
                        class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                               px-3 py-2"
                    />
                </div>
                <div class="space-y-2">
                    <label
                        class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                    >
                        Verfügbar bis
                    </label>
                    <input
                        bind:value={form.available_until}
                        type="date"
                        class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                               bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                               px-3 py-2"
                    />
                </div>
            </div>

            <div class="space-y-2">
                <label
                    class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                >
                    Sortier-Reihenfolge
                </label>
                <input
                    bind:value={form.sort_order}
                    type="number"
                    placeholder="0"
                    class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                           px-3 py-2"
                />
            </div>
        </div>

        <div
            class="p-4 border-t border-light-ui-3 dark:border-dark-ui-3 flex justify-end gap-2"
        >
            <button
                onclick={closePanel}
                disabled={saving}
                class="px-4 py-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors disabled:opacity-50"
            >
                Abbrechen
            </button>
            <button
                onclick={save}
                disabled={saving ||
                    !form.name.trim() ||
                    !form.system_prompt.trim() ||
                    !form.model.trim()}
                class="px-4 py-2 bg-primary text-white rounded-lg
                       hover:bg-primary-dark transition-colors disabled:opacity-50 flex items-center gap-2"
            >
                {#if saving}
                    <Loader2 class="w-4 h-4 animate-spin" />
                    Wird gespeichert...
                {:else}
                    <Check class="w-4 h-4" />
                    Speichern
                {/if}
            </button>
        </div>
    </div>
{/if}

<!-- Import-Dialog (Modal) -->
{#if importOpen}
    <div class="fixed inset-0 bg-black/50 z-40" onclick={closeImport} />
    <div
        class="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 bg-light-bg dark:bg-dark-bg rounded-xl shadow-2xl z-50 p-6"
    >
        <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx">
                Assistenten importieren
            </h2>
            <button
                onclick={closeImport}
                class="p-1 rounded-lg hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
            >
                <X class="w-5 h-5 text-light-tx-2 dark:text-dark-tx-2" />
            </button>
        </div>

        {#if importError}
            <div class="mb-4">
                <ErrorBanner message={importError} />
            </div>
        {/if}

        <div
            class="border-2 border-dashed border-light-ui-3 dark:border-dark-ui-3 rounded-xl p-8 text-center
                   mb-4 transition-colors
                   {importFile
                ? 'border-light-gr dark:border-dark-gr bg-light-gr/10 dark:bg-dark-gr/10'
                : 'hover:border-light-ui-3 dark:hover:border-dark-ui-3'}"
            ondragenter={(e) => {
                e.preventDefault();
            }}
            ondragover={(e) => {
                e.preventDefault();
            }}
            ondrop={handleFileDrop}
        >
            <input
                type="file"
                accept=".yaml,.yml"
                onchange={handleFileSelect}
                class="hidden"
                id="import-file-input"
            />
            <label for="import-file-input" class="cursor-pointer">
                <Upload
                    class="w-12 h-12 mx-auto text-light-tx-2 dark:text-dark-tx-2 mb-2"
                />
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                    Datei auswählen oder hier ablegen
                </p>
                <p class="text-xs text-light-tx-3 dark:text-dark-tx-3 mt-1">
                    {importFile?.name || "Keine Datei ausgewählt"}
                </p>
            </label>
        </div>

        <div class="space-y-2 mb-4">
            <label
                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
            >
                Modell überschreiben (optional)
            </label>
            <input
                bind:value={importModelOverride}
                type="text"
                placeholder="openai/gpt-4o-mini"
                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2"
            />
        </div>

        <div class="flex justify-end gap-2">
            <button
                onclick={closeImport}
                disabled={importing}
                class="px-4 py-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors disabled:opacity-50"
            >
                Abbrechen
            </button>
            <button
                onclick={doImport}
                disabled={importing || !importFile}
                class="px-4 py-2 bg-primary text-white rounded-lg
                       hover:bg-primary-dark transition-colors disabled:opacity-50 flex items-center gap-2"
            >
                {#if importing}
                    <Loader2 class="w-4 h-4 animate-spin" />
                    Wird importiert...
                {:else}
                    <Upload class="w-4 h-4" />
                    Importieren
                {/if}
            </button>
        </div>
    </div>
{/if}

<!-- Lösch-Bestätigung (Modal) -->
{#if deleteTarget}
    <div class="fixed inset-0 bg-black/50 z-40" onclick={closeDelete} />
    <div
        class="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 bg-light-bg dark:bg-dark-bg rounded-xl shadow-2xl z-50 p-6"
    >
        <div class="flex items-start gap-3 mb-4">
            <AlertCircle
                class="w-5 h-5 text-light-ye dark:text-dark-ye shrink-0 mt-0.5"
            />
            <div>
                <h2
                    class="text-lg font-semibold text-light-tx dark:text-dark-tx"
                >
                    Assistenten löschen
                </h2>
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    Möchten Sie den Assistenten „{deleteTarget.name}“ wirklich
                    löschen? Diese Aktion kann nicht rückgängig gemacht werden.
                </p>
            </div>
        </div>

        {#if deleteError}
            <div class="mb-4">
                <ErrorBanner message={deleteError} />
            </div>
        {/if}

        <div class="flex justify-end gap-2">
            <button
                onclick={closeDelete}
                disabled={deleting}
                class="px-4 py-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors disabled:opacity-50"
            >
                Abbrechen
            </button>
            <button
                onclick={confirmDelete}
                disabled={deleting}
                class="px-4 py-2 bg-light-re dark:bg-dark-re text-white rounded-lg
                       hover:bg-light-re-2 dark:hover:bg-dark-re-2 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
                {#if deleting}
                    <Loader2 class="w-4 h-4 animate-spin" />
                    Wird gelöscht...
                {:else}
                    <Trash2 class="w-4 h-4" />
                    Löschen
                {/if}
            </button>
        </div>
    </div>
{/if}
