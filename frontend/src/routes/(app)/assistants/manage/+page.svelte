<script>
    import { onMount } from "svelte";
    import { goto } from "$app/navigation";
    import yaml from 'js-yaml';
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
        Eye,
    } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";
    import { pendingCount, refreshPendingCount } from "$lib/stores/pendingAssistants.js";
    import {
        getAdminAssistants,
        deleteAssistant,
        exportAssistant,
        exportAllAssistants,
        importAssistant,
        getModels,
        approveAssistant,
        rejectAssistant,
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
    let importPreview = $state(null);
    // { name: string, system_prompt: string, model: string }
    let importModelMismatch = $state(false);

    async function parseImportPreview(file) {
        importPreview = null;
        importModelMismatch = false;
        try {
            const text = await file.text();
            const data = yaml.load(text);
            if (!data || typeof data !== 'object') return;
            const name = data.metadata?.name ?? null;
            const system_prompt = data.config?.system_prompt ?? null;
            const model = data.config?.model ?? null;
            importPreview = { name, system_prompt, model };
            if (model && availableModels.length > 0) {
                importModelMismatch = !availableModels.includes(model);
            }
        } catch {
            // Parsing-Fehler werden beim eigentlichen Import behandelt
        }
    }

    // Löschen
    let deleteTarget = $state(null);
    let deleting = $state(false);
    let deleteError = $state(null);

    // Success Banner
    let successMessage = $state(null);

    // Pending Queue
    let pendingItems = $state([]);
    let loadingPending = $state(false);

    // Reject Modal
    let rejectTarget = $state(null);
    let rejectReason = $state("");
    let rejecting = $state(false);
    let rejectError = $state(null);

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
        pending_review: "bg-light-ye/20 dark:bg-dark-ye/20 text-light-ye dark:text-dark-ye",
        active: "bg-light-gr/20 dark:bg-dark-gr/20 text-light-gr dark:text-dark-gr",
        disabled: "bg-light-re/20 dark:bg-dark-re/20 text-light-re dark:text-dark-re",
        archived: "bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2",
    };
    const STATUS_LABEL = {
        draft: "Entwurf",
        pending_review: "In Prüfung",
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

    async function loadPending() {
        loadingPending = true;
        try {
            const result = await getAdminAssistants({ status: 'pending_review', limit: 100 });
            pendingItems = result.items;
        } catch (e) {
            // Fehler ignorieren - Pending-Queue ist optional
        } finally {
            loadingPending = false;
        }
    }

    async function doApprove(assistant) {
        // Zielgruppe ist ein bewusster Prüfpunkt (Phase 13): student/all sind für
        // Schüler:innen sichtbar — eine Fehlkonfiguration hätte pädagogische Folgen.
        if (assistant.audience === "student" || assistant.audience === "all") {
            const label = AUDIENCE_LABELS[assistant.audience] || assistant.audience;
            if (
                !confirm(
                    `„${assistant.name}" wird für Schüler:innen sichtbar ` +
                        `(Zielgruppe: ${label}). Zielgruppe geprüft und freigeben?`,
                )
            ) {
                return;
            }
        }
        try {
            await approveAssistant(assistant.id);
            successMessage = `"${assistant.name}" wurde freigegeben.`;
            await Promise.all([reload(), loadPending(), refreshPendingCount()]);
        } catch (e) {
            error = e.message;
        }
    }

    function openReject(assistant) {
        rejectTarget = assistant;
        rejectReason = "";
        rejectError = null;
    }

    function closeReject() {
        rejectTarget = null;
        rejectReason = "";
        rejectError = null;
    }

    async function confirmReject() {
        if (!rejectTarget) return;
        rejecting = true;
        try {
            await rejectAssistant(rejectTarget.id, rejectReason || null);
            successMessage = `"${rejectTarget.name}" wurde abgelehnt.`;
            closeReject();
            await Promise.all([reload(), loadPending(), refreshPendingCount()]);
        } catch (e) {
            rejectError = e.message;
        } finally {
            rejecting = false;
        }
    }

    // Export
    async function doExport(assistant) {
        const slug = assistant.name.toLowerCase().replace(/\s+/g, "-");
        await exportAssistant(assistant.id, `${slug}.yaml`);
    }

    async function doExportAll() {
        try {
            await exportAllAssistants("active");
        } catch (e) {
            error = e.message;
        }
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
            action: () => goto(`/assistants/manage/${assistant.id}`),
            icon: Pencil,
        });
        if (assistant.status === "pending_review") {
            actions.push({
                label: "Freigeben",
                action: () => doApprove(assistant),
                icon: Check,
            });
            actions.push({
                label: "Ablehnen",
                action: () => openReject(assistant),
                icon: X,
            });
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

    // Import-Dialog
    function openImport() {
        importOpen = true;
        importFile = null;
        importModelOverride = "";
        importError = null;
        importPreview = null;
        importModelMismatch = false;
    }

    function closeImport() {
        importOpen = false;
        importError = null;
        importPreview = null;
        importModelMismatch = false;
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

    async function handleFileDrop(event) {
        event.preventDefault();
        const files = event.dataTransfer?.files;
        if (files && files.length > 0) {
            importFile = files[0];
            await parseImportPreview(importFile);
        }
    }

    async function handleFileSelect(event) {
        const files = event.target.files;
        if (files && files.length > 0) {
            importFile = files[0];
            await parseImportPreview(importFile);
        }
    }

    // Lebenszyklus
    onMount(async () => {
        const [, , models] = await Promise.allSettled([
            reload(),
            loadPending(),
            getModels(),
        ]);
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
                Manage Assistants
            </h1>
        </div>
        <div class="flex items-center gap-2">
            <button
                onclick={doExportAll}
                class="px-4 py-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors flex items-center gap-2"
            >
                <Download class="w-4 h-4" />
                Alle exportieren
            </button>
            <button
                onclick={openImport}
                class="px-4 py-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors flex items-center gap-2"
            >
                <Upload class="w-4 h-4" />
                Importieren
            </button>
            <button
                onclick={() => goto('/assistants/manage/neu')}
                class="px-4 py-2 bg-primary text-white rounded-lg
                       hover:bg-primary-dark transition-colors flex items-center gap-2"
            >
                <Plus class="w-4 h-4" />
                Neu anlegen
            </button>
        </div>
    </div>

    <!-- Pending Queue (offene Freigaben) -->
    {#if pendingItems.length > 0}
        <div class="p-6 border-b border-light-ui-3 dark:border-dark-ui-3 bg-light-ye/5 dark:bg-dark-ye/5">
            <h2 class="text-sm font-semibold text-light-ye dark:text-dark-ye mb-3 flex items-center gap-2">
                <AlertCircle class="w-4 h-4" />
                Offene Freigaben ({pendingItems.length})
            </h2>
            <div class="space-y-2">
                {#each pendingItems as item}
                    <div class="flex items-center justify-between p-3 rounded-lg
                        bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3">
                        <div class="flex-1 min-w-0 mr-4">
                            <span class="font-medium text-light-tx dark:text-dark-tx">{item.name}</span>
                            <span
                                class="ml-2 px-1.5 py-0.5 rounded-full text-xs font-medium align-middle
                                    {item.audience === 'teacher'
                                    ? 'bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx-2 dark:text-dark-tx-2'
                                    : 'bg-light-or/20 dark:bg-dark-or/20 text-light-or dark:text-dark-or'}"
                                title="Zielgruppe"
                            >
                                {AUDIENCE_LABELS[item.audience] || item.audience}
                            </span>
                            {#if item.description}
                                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 truncate">{item.description}</p>
                            {/if}
                        </div>
                        <div class="flex items-center gap-2 shrink-0">
                            <button
                                onclick={() => goto(`/assistants/manage/${item.id}`)}
                                title="Ansehen"
                                class="p-1.5 rounded-md hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                                     text-light-tx-2 dark:text-dark-tx-2 transition-colors"
                            >
                                <Eye class="w-4 h-4" />
                            </button>
                            <button
                                onclick={() => doApprove(item)}
                                title="Freigeben"
                                class="p-1.5 rounded-md hover:bg-light-gr/10 dark:hover:bg-dark-gr/10
                                     text-light-gr dark:text-dark-gr transition-colors"
                            >
                                <Check class="w-4 h-4" />
                            </button>
                            <button
                                onclick={() => openReject(item)}
                                title="Ablehnen"
                                class="p-1.5 rounded-md hover:bg-light-re/10 dark:hover:bg-dark-re/10
                                     text-light-re dark:text-dark-re transition-colors"
                            >
                                <X class="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                {/each}
            </div>
        </div>
    {/if}

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
                    <option value="pending_review">In Prüfung</option>
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

        <!-- Vorschau-Block -->
        {#if importPreview}
            <div class="mb-4 p-3 rounded-lg bg-light-bg-2 dark:bg-dark-bg-2
                        border border-light-ui-3 dark:border-dark-ui-3 space-y-2">
                {#if importPreview.name}
                    <p class="text-sm font-medium text-light-tx dark:text-dark-tx">
                        {importPreview.name}
                    </p>
                {/if}
                {#if importPreview.model}
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                        Modell: <span class="font-mono">{importPreview.model}</span>
                    </p>
                {/if}
                {#if importModelMismatch}
                    <p class="text-xs text-light-ye dark:text-dark-ye flex items-center gap-1">
                        <AlertCircle class="w-3 h-3 shrink-0" />
                        Dieses Modell ist nicht freigeschaltet — bitte unten überschreiben.
                    </p>
                {/if}
                {#if importPreview.system_prompt}
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 line-clamp-3 whitespace-pre-wrap">
                        {importPreview.system_prompt}
                    </p>
                {/if}
            </div>
        {/if}

        <div class="space-y-2 mb-4">
            <label
                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
            >
                Modell überschreiben (optional)
            </label>
            <select
                bind:value={importModelOverride}
                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2"
            >
                <option value="">Modell aus Datei übernehmen</option>
                {#each availableModels as m}
                    <option value={m}>{m}</option>
                {/each}
            </select>
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

<!-- Ablehnen-Bestätigung (Modal) -->
{#if rejectTarget}
    <div class="fixed inset-0 bg-black/50 z-40" onclick={closeReject} />
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
                    Einreichung ablehnen
                </h2>
                <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
                    Möchten Sie die Einreichung "{rejectTarget.name}" wirklich ablehnen?
                </p>
                <p class="text-sm text-light-tx-3 dark:text-dark-tx-3 mt-1">
                    Begründung (optional) — wird der Lehrkraft im Editor angezeigt.
                </p>
            </div>
        </div>

        {#if rejectError}
            <div class="mb-4">
                <ErrorBanner message={rejectError} />
            </div>
        {/if}

        <div class="mb-4">
            <textarea
                bind:value={rejectReason}
                placeholder="Begründung für die Ablehnung (optional)"
                rows="3"
                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2 resize-none"
            ></textarea>
        </div>

        <div class="flex justify-end gap-2">
            <button
                onclick={closeReject}
                disabled={rejecting}
                class="px-4 py-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors disabled:opacity-50"
            >
                Abbrechen
            </button>
            <button
                onclick={confirmReject}
                disabled={rejecting}
                class="px-4 py-2 bg-light-re dark:bg-dark-re text-white rounded-lg
                       hover:bg-light-re-2 dark:hover:bg-dark-re-2 transition-colors disabled:opacity-50 flex items-center gap-2"
            >
                {#if rejecting}
                    <Loader2 class="w-4 h-4 animate-spin" />
                    Wird abgelehnt...
                {:else}
                    <X class="w-4 h-4" />
                    Ablehnen
                {/if}
            </button>
        </div>
    </div>
{/if}
