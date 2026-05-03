<script>
    import { onMount } from "svelte";
    import { goto } from "$app/navigation";
    import { page } from "$app/stores";
    import {
        Bot,
        Send,
        Pencil,
        Trash2,
        Download,
        X,
        Check,
        Loader2,
        AlertCircle,
        Play,
        RotateCcw,
        Eye,
        EyeOff,
    } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";
    import MessageBubble from "$lib/components/MessageBubble.svelte";
    import {
        getAdminAssistant,
        getAdminAssistants,
        createAssistant,
        updateAssistant,
        deleteAssistant,
        exportAssistant,
        activateAssistant,
        deactivateAssistant,
        getModels,
        streamChat,
        ApiError,
    } from "$lib/api.js";
    import { user } from "$lib/stores/user.js";

    // URL Parameter
    let { data } = $props();

    const assistantId = data.id;
    const isNew = assistantId === 'neu';

    // State für Formular
    let form = $state(emptyForm());
    let savedForm = $state(emptyForm());
    let loading = $state(true);
    let error = $state(null);
    let successMessage = $state(null);
    let availableModels = $state([]);

    // Testchat State
    let testConversationId = $state(null);
    let testMessages = $state([]);
    let testInput = $state("");
    let testIsStreaming = $state(false);
    let testError = $state(null);
    let testTextarea = $state(null);

    // Dirty State
    let dirty = $derived(
        JSON.stringify(form) !== JSON.stringify(savedForm)
    );

    // Status-Labels
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

    // Laden der Daten
    async function loadAssistant() {
        if (isNew) {
            form = emptyForm();
            savedForm = emptyForm();
            loading = false;
            return;
        }
        loading = true;
        error = null;
        try {
            const result = await getAdminAssistant(assistantId);
            const a = result;
            form = {
                name: a.name || "",
                description: a.description || "",
                subject_id: a.subject_id || null,
                system_prompt: a.system_prompt || "",
                model: a.model || "",
                temperature: a.temperature !== null ? String(a.temperature) : null,
                max_tokens: a.max_tokens !== null ? String(a.max_tokens) : null,
                audience: a.audience || "student",
                scope: a.scope || "private",
                min_grade: a.min_grade !== null ? String(a.min_grade) : null,
                max_grade: a.max_grade !== null ? String(a.max_grade) : null,
                tags: (a.tags ?? []).join(", "),
                icon: a.icon || null,
                available_from: a.available_from ? a.available_from.split("T")[0] : "",
                available_until: a.available_until ? a.available_until.split("T")[0] : "",
                sort_order: a.sort_order ?? 0,
                status: a.status || "draft",
            };
            savedForm = { ...form };
        } catch (e) {
            error = e.message ?? 'Assistent nicht gefunden';
        } finally {
            loading = false;
        }
    }

    // Speichern
    async function save() {
        if (!form.name.trim() || !form.system_prompt.trim() || !form.model.trim()) {
            error = "Name, System-Prompt und Modell sind Pflichtfelder.";
            return;
        }
        loading = true;
        error = null;
        const payload = {
            ...form,
            tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean) || null,
            temperature: form.temperature ? parseFloat(form.temperature) : null,
            max_tokens: form.max_tokens ? parseInt(form.max_tokens) : null,
            min_grade: form.min_grade ? parseInt(form.min_grade) : null,
            max_grade: form.max_grade ? parseInt(form.max_grade) : null,
            available_from: form.available_from || null,
            available_until: form.available_until || null,
            sort_order: parseInt(form.sort_order) || 0,
        };
        try {
            if (isNew) {
                const result = await createAssistant(payload);
                successMessage = "Assistent wurde erfolgreich angelegt.";
                savedForm = { ...form };
                // Navigiere zur Bearbeitungsseite mit der neuen ID
                goto(`/assistants/manage/${result.id}`);
            } else {
                await updateAssistant(assistantId, payload);
                successMessage = "Assistent wurde erfolgreich aktualisiert.";
                savedForm = { ...form };
            }
        } catch (e) {
            error = e.message ?? 'Fehler beim Speichern';
        } finally {
            loading = false;
        }
    }

    // Aktivieren/Deaktivieren
    async function toggleActivate() {
        if (!assistantId) return;
        loading = true;
        try {
            if (form.status === 'active') {
                await deactivateAssistant(assistantId);
                form.status = 'disabled';
                savedForm = { ...savedForm, status: 'disabled' };
                successMessage = 'Assistent wurde deaktiviert.';
            } else {
                await activateAssistant(assistantId);
                form.status = 'active';
                savedForm = { ...savedForm, status: 'active' };
                successMessage = 'Assistent wurde aktiviert.';
            }
        } catch (e) {
            error = e.message ?? 'Fehler beim Ändern des Status';
        } finally {
            loading = false;
        }
    }

    // Export
    async function doExport() {
        const a = await getAdminAssistant(assistantId);
        const slug = a.name.toLowerCase().replace(/\s+/g, "-");
        await exportAssistant(assistantId, `${slug}.yaml`);
    }

    // Testchat Funktionen
    let testAreaRows = $state(1);

    function adjustTestTextareaHeight() {
        if (!testTextarea) return;
        testTextarea.rows = 1;
        const rows = Math.min(Math.ceil(testTextarea.scrollHeight / 24), 6);
        testTextarea.rows = rows;
        testAreaRows = rows;
    }

    async function sendTestMessage() {
        if (!testInput.trim() || testIsStreaming) return;
        if (dirty) {
            // Unsaved changes - auto-save first
            await save();
            if (dirty) {
                // Save failed or still dirty
                error = "Bitte speichern Sie zuerst den Assistenten.";
                return;
            }
        }

        const userMessage = testInput.trim();
        testInput = "";
        adjustTestTextareaHeight();

        // Add user message to test messages
        testMessages = [...testMessages, { role: "user", content: userMessage }];
        testMessages = [...testMessages, { role: "assistant", content: "" }];

        testIsStreaming = true;
        testError = null;

        try {
            const messages = testMessages.slice(0, -1).map(m => ({ role: m.role, content: m.content }));
            
            for await (const item of streamChat(
                messages,
                testConversationId,
                null,
                Number(assistantId),
                true  // is_test = true
            )) {
                if (item.type === "start") {
                    testConversationId = item.conversationId;
                    continue;
                }
                if (item.type === "title" || item.type === "cost") {
                    continue;
                }
                // Token
                if (typeof item === 'string') {
                    const lastIndex = testMessages.length - 1;
                    testMessages[lastIndex] = {
                        ...testMessages[lastIndex],
                        content: testMessages[lastIndex].content + item
                    };
                    testMessages = testMessages;
                }
            }
        } catch (e) {
            testError = e.message ?? 'Fehler beim Testen';
            // Remove empty assistant message
            if (testMessages.length > 0 && testMessages[testMessages.length - 1].role === "assistant" && testMessages[testMessages.length - 1].content === "") {
                testMessages = testMessages.slice(0, -1);
            }
        } finally {
            testIsStreaming = false;
        }
    }

    function newTestChat() {
        testConversationId = null;
        testMessages = [];
        testInput = "";
        testError = null;
    }

    function handleTestKeydown(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendTestMessage();
        }
    }

    // Lebenszyklus
    onMount(async () => {
        const modelsResult = await getModels();
        availableModels = modelsResult.models.map((m) => m.id);
        await loadAssistant();
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
        class="flex items-center justify-between p-4 border-b border-light-ui-3 dark:border-dark-ui-3"
    >
        <div class="flex items-center gap-2">
            <button
                onclick={() => goto('/assistants/manage')}
                class="flex items-center gap-2 text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx"
            >
                <X class="w-4 h-4" />
                Zurück
            </button>
            <span class="text-light-tx-2 dark:text-dark-tx-2">/</span>
            <Bot class="w-5 h-5 text-light-bl dark:text-dark-bl" />
            <h1 class="text-xl font-bold text-light-tx dark:text-dark-tx">
                {isNew ? "Neuer Assistent" : form.name || "Assistent bearbeiten"}
            </h1>
        </div>
        <div class="flex items-center gap-2">
            {#if !isNew && assistantId}
                <button
                    onclick={newTestChat}
                    disabled={testIsStreaming}
                    class="px-3 py-1.5 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors disabled:opacity-50
                           flex items-center gap-1.5 text-sm"
                >
                    <RotateCcw class="w-4 h-4" />
                    Neuer Test
                </button>
            {/if}
            <button
                onclick={save}
                disabled={loading || !dirty || (!form.name.trim() || !form.system_prompt.trim() || !form.model.trim())}
                class="px-4 py-2 bg-primary text-white rounded-lg
                       hover:bg-primary-dark transition-colors disabled:opacity-50 flex items-center gap-2"
            >
                {#if loading}
                    <Loader2 class="w-4 h-4 animate-spin" />
                    Speichern...
                {:else}
                    <Check class="w-4 h-4" />
                    Speichern
                {/if}
            </button>
        </div>
    </div>

    <!-- Hauptbereich: Zweispaltiges Layout -->
    <div class="flex-1 flex overflow-y-auto">
        <!-- Linke Spalte: Editor (ca. 45%) -->
        <div class="flex-1 min-w-0 lg:w-[45%] border-r border-light-ui-3 dark:border-dark-ui-3 p-4 overflow-y-auto">
            {#if error}
                <div class="mb-4">
                    <ErrorBanner message={error} />
                </div>
            {/if}
            {#if successMessage}
                <div class="mb-4">
                    <SuccessBanner message={successMessage} />
                </div>
            {/if}

            <div class="space-y-4 max-w-md">
                <div class="space-y-2">
                    <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                    <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                    <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                    <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                    <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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
                    <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
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

                <!-- Status und Freigabe (nur bei bestehendem Assistenten) -->
                {#if !isNew && form.status}
                    <div class="space-y-2 pt-2 border-t border-light-ui-3 dark:border-dark-ui-3">
                        <label class="block text-sm font-medium text-light-tx dark:text-dark-tx">
                            Status
                        </label>
                        <div class="flex items-center gap-3">
                            <span
                                class="px-2 py-1 rounded-full text-xs {STATUS_CLASS[form.status] || STATUS_CLASS.draft}"
                            >
                                {STATUS_LABEL[form.status] || form.status}
                            </span>
                            {#if $user?.roles.includes('admin')}
                                <button
                                    onclick={toggleActivate}
                                    disabled={loading}
                                    class="px-3 py-1.5 text-sm rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                                   text-light-tx dark:text-dark-tx
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                                   flex items-center gap-1.5"
                                >
                                    {#if form.status === 'active'}
                                        <EyeOff class="w-4 h-4" />
                                        Deaktivieren
                                    {:else}
                                        <Eye class="w-4 h-4" />
                                        Aktivieren
                                    {/if}
                                </button>
                            {/if}
                        </div>
                    </div>
                {/if}

                <!-- Aktionen -->
                <div class="pt-2 border-t border-light-ui-3 dark:border-dark-ui-3">
                    <div class="flex gap-2">
                        {#if !isNew && assistantId}
                            <button
                                onclick={doExport}
                                class="flex-1 px-3 py-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors flex items-center justify-center gap-2"
                            >
                                <Download class="w-4 h-4" />
                                Exportieren
                            </button>
                        {/if}
                    </div>
                </div>
            </div>
        </div>

        <!-- Rechte Spalte: Testchat (ca. 55%) -->
        <div class="flex-1 min-w-0 lg:w-[55%] p-4 overflow-y-auto">
            <div class="h-full flex flex-col">
                <!-- Testchat Header -->
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-2">
                        <Play class="w-5 h-5 text-light-gr dark:text-dark-gr" />
                        <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx">
                            Testchat
                        </h2>
                    </div>
                    <span class="text-xs text-light-tx-3 dark:text-dark-tx-3">
                        Modell: {form.model || '—'}
                    </span>
                </div>

                {#if isNew}
                    <div class="flex-1 flex items-center justify-center text-light-tx-2 dark:text-dark-tx-2">
                        <p>Speichern Sie den Assistenten zuerst, um den Testchat zu nutzen.</p>
                    </div>
                {:else if !form.model}
                    <div class="flex-1 flex items-center justify-center text-light-tx-2 dark:text-dark-tx-2">
                        <p>Wählen Sie ein Modell aus, um den Testchat zu nutzen.</p>
                    </div>
                {:else}
                    <!-- Nachrichtenbereich -->
                    <div class="flex-1 overflow-y-auto space-y-4 mb-4">
                        {#if testMessages.length === 0}
                            <div class="flex items-center justify-center h-full text-light-tx-3 dark:text-dark-tx-3">
                                <p>Stellen Sie dem Assistenten eine Testfrage.</p>
                            </div>
                        {:else}
                            {#each testMessages as message, i}
                                <MessageBubble
                                    {message}
                                    isStreaming={testIsStreaming && i === testMessages.length - 1 && message.role === 'assistant'}
                                />
                            {/each}
                        {/if}
                        {#if testError}
                            <div class="flex justify-center">
                                <span class="text-light-re dark:text-dark-re text-sm">{testError}</span>
                            </div>
                        {/if}
                    </div>

                    <!-- Eingabebereich -->
                    <div class="border-t border-light-ui-3 dark:border-dark-ui-3 pt-4">
                        <div class="flex gap-2">
                            <textarea
                                bind:this={testTextarea}
                                bind:value={testInput}
                                rows={testAreaRows}
                                onkeydown={handleTestKeydown}
                                disabled={testIsStreaming}
                                placeholder={testIsStreaming ? "..." : "Testfrage eingeben..."}
                                class="flex-1 resize-none rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                                       px-3 py-2 disabled:opacity-50"
                            ></textarea>
                            <button
                                onclick={sendTestMessage}
                                disabled={testIsStreaming || !testInput.trim()}
                                class="p-2 bg-primary text-white rounded-lg
                                       hover:bg-primary-dark transition-colors disabled:opacity-50
                                       flex items-center justify-center min-w-[44px]"
                            >
                                {#if testIsStreaming}
                                    <Loader2 class="w-5 h-5 animate-spin" />
                                {:else}
                                    <Send class="w-5 h-5" />
                                {/if}
                            </button>
                        </div>
                    </div>
                {/if}
            </div>
        </div>
    </div>
</div>
