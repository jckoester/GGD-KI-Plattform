<script>
    import { onMount } from "svelte";
    import { goto } from "$app/navigation";
    import {
        Bot,
        Plus,
        Pencil,
        Trash2,
        Download,
        Upload,
        X,
        Check,
        Loader2,
        AlertCircle,
    } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";
    import {
        getAdminAssistants,
        deleteAssistant,
        exportAssistant,
        importAssistant,
        getModels,
        ApiError,
    } from "$lib/api.js";

    let availableModels = $state([]); // string[]

    // State-Variablen
    let assistants = $state([]);
    let total = $state(0);
    let loading = $state(true);
    let error = $state(null);

    // Filter
    let filterStatus = $state(""); // '' | 'draft' | 'active' | 'disabled' | 'archived'
    let filterAudience = $state(""); // '' | 'student' | 'teacher' | 'all'

    // Import
    let importOpen = $state(false);
    let importFile = $state(null);
    let importModelOverride = $state("");
    let importing = $state(false);
    let importError = $state(null);

    // Löschen
    let deleteTarget = $state(null);
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
        disabled: "bg-light-ye/20 dark:bg-dark-ye/20 text-light-ye dark:text-dark-ye",
        archived: "bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2",
    };
    const STATUS_LABEL = {
        draft: "Entwurf",
        active: "Aktiv",
        disabled: "Deaktiviert",
        archived: "Archiviert",
    };

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

    // Aktionsschaltflächen pro Zeile
    function getActions(assistant) {
        const actions = [];
        actions.push({
            label: "Bearbeiten",
            action: () => goto(`/assistants/verwalten/${assistant.id}`),
            icon: Pencil,
        });
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

<div class="h-full flex flex-col">
    <!-- Kopfzeile -->
    <div
        class="flex items-center justify-between p-6 border-b border-light-ui-3 dark:border-dark-ui-3"
    >
        <div class="flex items-center gap-2">
            <Bot class="w-6 h-6 text-light-bl dark:text-dark-bl" />
            <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
                Assistenten verwalten
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
                onclick={() => goto('/assistants/verwalten/neu')}
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
                <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">Status</span>
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
                <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">Zielgruppe</span>
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
                                <th class="pb-3 pr-4 font-medium">Zielgruppe</th>
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
                    Möchten Sie den Assistenten "{deleteTarget.name}" wirklich
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
