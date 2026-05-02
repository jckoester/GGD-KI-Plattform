<script>
    import {
        Send,
        Loader2,
        AlertCircle,
        Paperclip,
        Bot,
        X,
    } from "lucide-svelte";
    import MessageBubble from "$lib/components/MessageBubble.svelte";
    import AttachmentChip from "$lib/components/AttachmentChip.svelte";
    import AssistantPicker from "$lib/components/AssistantPicker.svelte";
    import { goto } from "$app/navigation";
    import { page } from "$app/stores";
    import {
        streamChat,
        ApiError,
        getConversationMessages,
        getModels,
        uploadFile,
        getAssistants,
    } from "$lib/api.js";
    import { refreshConversations } from "$lib/stores/conversations.js";
    import { user } from "$lib/stores/user.js";
    import { budget, refreshBudget } from "$lib/stores/budget.js";

    let messages = $state([]);
    let input = $state("");
    let textarea = $state(null);
    let isStreaming = $state(false);
    let error = $state(null);
    let scrollAnchor = $state(null);
    let conversationId = $state(null);
    let loadingConversation = $state(false);
    let conversationError = $state(null);
    let currentConversationModel = $state(null);
    let availableModels = $state([]);
    let selectedModelId = $state("");
    let modelsLoading = $state(false);
    let modelsError = $state(null);
    let totalCostUsd = $state(null);

    // Attachment-State
    let attachments = $state([]);
    let fileInput = $state(null);

    // Assistenten-State
    let availableAssistants = $state([]);
    let selectedAssistant = $state(null);
    let pickerOpen = $state(false);
    let conversationAssistant = $state(null); // Assistenten-Objekt für laufende Konversation

    const MAX_FILES = 3;
    const MAX_BYTES = 10 * 1024 * 1024; // 10 MB
    const ACCEPTED_EXTENSIONS = [
        ".pdf",
        ".txt",
        ".md",
        ".csv",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    ];

    const MODEL_STORAGE_KEY = "chat_model_id";

    let textAreaRows = $state(1);

    // Hilfsfunktion zur Kostenformatierung
    function formatCostEur(costUsd, rate) {
        if (costUsd == null || !rate) return null;
        const eur = costUsd / rate;
        if (eur < 0.01) return "< 0,01";
        return eur.toLocaleString("de-DE", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    let granularity = $derived($user?.preferences?.cost_granularity ?? "none");

    function adjustTextareaHeight() {
        if (!textarea) return;
        // Direktes DOM-Reset nötig: reaktiver State-Update ist async,
        // scrollHeight würde sonst noch die alte Höhe liefern.
        textarea.rows = 1;
        const rows = Math.min(Math.ceil(textarea.scrollHeight / 24), 6);
        textarea.rows = rows;
        textAreaRows = rows;
    }

    import { updateConversationTitle } from "$lib/stores/conversations.js";
    import { pageTitle, activeConversationId } from "$lib/stores/pageTitle.js";
    import { onDestroy, onMount } from "svelte";

    async function loadModels() {
        modelsLoading = true;
        modelsError = null;

        try {
            const data = await getModels();
            availableModels = data.models ?? [];

            const modelIds = availableModels.map((m) => m.id).filter(Boolean);
            const savedModel = sessionStorage.getItem(MODEL_STORAGE_KEY);

            if (savedModel && modelIds.includes(savedModel)) {
                selectedModelId = savedModel;
            } else if (
                data.default_model &&
                modelIds.includes(data.default_model)
            ) {
                selectedModelId = data.default_model;
            } else {
                selectedModelId = modelIds[0] ?? "";
            }

            if (selectedModelId) {
                sessionStorage.setItem(MODEL_STORAGE_KEY, selectedModelId);
            }
        } catch (err) {
            availableModels = [];
            modelsError =
                err?.message ?? "Modelle konnten nicht geladen werden.";
            selectedModelId = sessionStorage.getItem(MODEL_STORAGE_KEY) ?? "";
        } finally {
            modelsLoading = false;
        }
    }

    function handleModelChange() {
        if (selectedModelId) {
            sessionStorage.setItem(MODEL_STORAGE_KEY, selectedModelId);
        } else {
            sessionStorage.removeItem(MODEL_STORAGE_KEY);
        }
    }

    function handleUploadClick() {
        fileInput?.click();
    }

    async function handleFilesSelected(event) {
        const files = Array.from(event.target.files ?? []);
        event.target.value = ""; // Reset, damit dieselbe Datei erneut wählbar ist

        const remaining = MAX_FILES - attachments.length;
        if (remaining <= 0) return;

        for (const file of files.slice(0, remaining)) {
            // Client-seitige Validierung
            const ext = "." + file.name.split(".").pop().toLowerCase();
            if (!ACCEPTED_EXTENSIONS.includes(ext)) {
                const id = crypto.randomUUID();
                attachments = [
                    ...attachments,
                    {
                        id,
                        filename: file.name,
                        status: "error",
                        result: null,
                        error: `Format '${ext}' wird nicht unterstützt.`,
                    },
                ];
                continue;
            }
            if (file.size > MAX_BYTES) {
                const id = crypto.randomUUID();
                attachments = [
                    ...attachments,
                    {
                        id,
                        filename: file.name,
                        status: "error",
                        result: null,
                        error: `Datei zu groß (max. 10 MB).`,
                    },
                ];
                continue;
            }

            const id = crypto.randomUUID();
            attachments = [
                ...attachments,
                {
                    id,
                    filename: file.name,
                    status: "uploading",
                    result: null,
                    error: null,
                },
            ];

            uploadFile(file)
                .then((result) => {
                    attachments = attachments.map((a) =>
                        a.id === id ? { ...a, status: "ready", result } : a,
                    );
                })
                .catch((err) => {
                    attachments = attachments.map((a) =>
                        a.id === id
                            ? { ...a, status: "error", error: err.message }
                            : a,
                    );
                });
        }
    }

    function removeAttachment(id) {
        attachments = attachments.filter((a) => a.id !== id);
    }

    function buildUserContent(text, uploads) {
        if (!uploads.length) return text;

        const parts = [];
        for (const { filename, result } of uploads) {
            if (result.type === "text") {
                parts.push({
                    type: "text",
                    text: `[${filename}]\n${result.content}`,
                });
            } else {
                // Bild: base64-data-URL aus result.data + result.mime_type
                parts.push({
                    type: "image_url",
                    image_url: {
                        url: `data:${result.mime_type};base64,${result.data}`,
                    },
                });
            }
        }
        if (text) parts.push({ type: "text", text });
        return parts;
    }

    async function handleSubmit() {
        // Neu: auch senden, wenn nur Anhänge vorhanden (kein Text nötig)
        const readyAttachments = attachments.filter(
            (a) => a.status === "ready",
        );
        if ((!input.trim() && readyAttachments.length === 0) || isStreaming)
            return;
        // Neu: Senden blockieren, solange noch Uploads laufen
        if (attachments.some((a) => a.status === "uploading")) return;

        const userMessage = input.trim();
        input = "";
        adjustTextareaHeight();

        // Neu: Anhänge snapshotten und sofort leeren
        const snapshotAttachments = readyAttachments.map((a) => ({
            filename: a.filename,
            result: a.result,
        }));
        attachments = [];

        // Neu: message-Objekt mit Attachment-Metadaten für Anzeige
        messages = [
            ...messages,
            {
                role: "user",
                content: userMessage,
                uploadedAttachments: snapshotAttachments,
            },
        ];

        // Assistent-Placeholder (unverändert)
        const assistantIndex = messages.length;
        messages = [...messages, { role: "assistant", content: "" }];

        isStreaming = true;
        error = null;

        try {
            // Neu: Content je User-Nachricht aufbauen
            const apiMessages = messages
                .slice(0, assistantIndex)
                .filter((m) => m.role === "user" || m.role === "assistant")
                .map((m) => ({
                    role: m.role,
                    content:
                        m.role === "user"
                            ? buildUserContent(
                                  m.content,
                                  m.uploadedAttachments ?? [],
                              )
                            : m.content,
                }));

            const modelId =
                conversationId || selectedAssistant ? null : selectedModelId;
            const assistantId = conversationId
                ? null
                : (selectedAssistant?.id ?? null);

            for await (const item of streamChat(
                apiMessages,
                conversationId,
                modelId,
                assistantId,
            )) {
                // Start-Event mit conversationId
                if (item.type === "start") {
                    conversationId = item.conversationId;
                    currentConversationModel = selectedAssistant
                        ? selectedAssistant.name
                        : selectedModelId || currentConversationModel;
                    // Assistenten-Referenz für laufende Konversation speichern
                    if (selectedAssistant) {
                        conversationAssistant = selectedAssistant;
                    }
                    continue;
                }
                // Titel-Event
                if (item.type === "title") {
                    updateConversationTitle(conversationId, item.title);
                    pageTitle.set(item.title);
                    continue;
                }
                // Cost-Event
                if (item.type === "cost") {
                    messages[assistantIndex] = {
                        ...messages[assistantIndex],
                        cost_usd: item.cost_usd,
                    };
                    messages = messages;
                    if (item.cost_usd != null) {
                        totalCostUsd = (totalCostUsd ?? 0) + item.cost_usd;
                    }
                    continue;
                }
                // Token von Assistant
                messages[assistantIndex] = {
                    ...messages[assistantIndex],
                    content: messages[assistantIndex].content + item,
                };
                messages = messages;
            }
        } catch (err) {
            if (err instanceof ApiError && err.status === 401) {
                await goto("/");
                return;
            }

            // Leeren Assistent-Placeholder entfernen, falls kein Token ankam
            if (messages[assistantIndex]?.content === "") {
                messages = [
                    ...messages.slice(0, assistantIndex),
                    ...messages.slice(assistantIndex + 1),
                ];
            }

            const knownErrors = {
                0: "Verbindung zum Server fehlgeschlagen.",
                429: "Dein Budget ist erschöpft.",
                502: "Der KI-Dienst ist gerade nicht erreichbar.",
                503: "Der KI-Dienst ist vorübergehend nicht verfügbar.",
            };
            const errorMessage =
                err instanceof ApiError && knownErrors[err.status]
                    ? knownErrors[err.status]
                    : (err.message ??
                      "Ein unbekannter Fehler ist aufgetreten.");

            messages = [...messages, { role: "error", content: errorMessage }];
        } finally {
            isStreaming = false;
            // Konversationen in Sidebar neu laden
            triggerSidebarRefresh();
            refreshBudget(); // neu: Budget-Store aktualisieren
        }
    }

    function handleKeydown(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    }

    function handleInput(e) {
        adjustTextareaHeight();
        // /-Shortcut für Assistenten-Auswahl
        // e.target.value statt input: bind:value aktualisiert input erst nach dem Handler
        if (
            e.target.value === "/" &&
            !conversationId &&
            availableAssistants.length > 0
        ) {
            input = "";
            pickerOpen = true;
        }
    }

    // Picker-Callbacks
    function handleAssistantSelect(assistant) {
        selectedAssistant = assistant;
        pickerOpen = false;
        textarea?.focus();
    }

    function handlePickerClose() {
        pickerOpen = false;
        textarea?.focus();
    }

    // Laden der Konversation basierend auf URL-Parameter
    async function loadConversation() {
        const id = $page.url.searchParams.get("id");
        conversationError = null;

        if (id) {
            loadingConversation = true;
            try {
                const data = await getConversationMessages(id);
                messages = data.messages.map((m) => ({
                    role: m.role,
                    content: m.content,
                    cost_usd: m.cost_usd ?? null,
                }));
                conversationId = data.id;
                currentConversationModel = data.model_used;
                totalCostUsd = data.total_cost_usd ?? null;
                selectedAssistant = null;
                conversationAssistant = data.assistant_name
                    ? { id: data.assistant_id, name: data.assistant_name }
                    : null;
                pageTitle.set(data.title || "");
                activeConversationId.set(data.id);
            } catch (err) {
                if (err instanceof ApiError) {
                    conversationError = err.message;
                    // Bei 403 oder 404: Konversation nicht gefunden
                    if (err.status === 403 || err.status === 404) {
                        messages = [];
                        conversationId = null;
                        currentConversationModel = null;
                        pageTitle.set("");
                        activeConversationId.set(null);
                    }
                } else {
                    conversationError = "Fehler beim Laden der Konversation";
                    currentConversationModel = null;
                    pageTitle.set("");
                    activeConversationId.set(null);
                }
            } finally {
                loadingConversation = false;
            }
        } else {
            // Neue Konversation
            messages = [];
            conversationId = null;
            currentConversationModel = null;
            totalCostUsd = null;
            conversationError = null;
            pageTitle.set("");
            activeConversationId.set(null);
            selectedAssistant = null;
            conversationAssistant = null;
            pickerOpen = false;
        }
    }

    // Reagieren auf URL-Änderungen
    $effect(() => {
        $page.url;
        loadConversation();
    });

    // Assistenten laden (parallel zu Modellen)
    async function loadAssistants() {
        try {
            const data = await getAssistants();
            availableAssistants = data.items;
        } catch {
            // kein hard fail — Assistenten sind optional
        }
    }

    // Stores zurücksetzen beim Verlassen der Seite
    onMount(() => {
        loadModels();
        loadAssistants();
    });

    onDestroy(() => {
        pageTitle.set("");
        activeConversationId.set(null);
    });

    // Automatisch Konversationen neu laden nach Stream-Ende
    // (wird aus Sidebar aufgerufen via refreshConversations)
    function triggerSidebarRefresh() {
        const limit = $user?.preferences?.sidebar_recent_chats_limit ?? 10;
        refreshConversations(limit);
    }

    // Scroll to bottom when messages change (aber nicht beim initialen Laden)
    $effect(() => {
        messages;
        if (!loadingConversation) {
            requestAnimationFrame(() => {
                if (scrollAnchor) {
                    scrollAnchor.scrollIntoView({
                        behavior: "smooth",
                        block: "end",
                    });
                }
            });
        }
    });
</script>

<div class="h-full flex flex-col">
    <div class="flex-1 overflow-y-auto px-4 py-4">
        {#if loadingConversation}
            <div class="flex items-center justify-center h-full">
                <div
                    class="flex flex-col items-center gap-2 text-light-tx-2 dark:text-dark-tx-2"
                >
                    <Loader2 class="w-6 h-6 animate-spin" />
                    <p>Konversation wird geladen...</p>
                </div>
            </div>
        {:else if conversationError}
            <div class="flex items-center justify-center h-full">
                <div
                    class="flex items-start gap-2 bg-red-50 dark:bg-red-950/20
                            border border-red-200 dark:border-red-900
                            rounded-lg px-4 py-3 text-light-re dark:text-dark-re max-w-md"
                >
                    <AlertCircle class="w-4 h-4 mt-0.5 shrink-0" />
                    <p class="text-sm">{conversationError}</p>
                </div>
            </div>
        {:else if messages.length === 0}
            <div class="flex items-center justify-center h-full">
                <div class="text-center text-light-tx-2 dark:text-dark-tx-2">
                    <p class="text-lg">Womit kann ich helfen?</p>
                </div>
            </div>
        {:else}
            <div class="space-y-4 max-w-4xl mx-auto">
                {#each messages as message, i}
                    <MessageBubble
                        {message}
                        isStreaming={isStreaming && i === messages.length - 1}
                        costEur={granularity === "message" ||
                        granularity === "both"
                            ? formatCostEur(
                                  message.cost_usd,
                                  $budget?.eur_usd_rate,
                              )
                            : null}
                    />
                {/each}
            </div>
        {/if}
        <div bind:this={scrollAnchor} class="h-0"></div>
    </div>

    <div
        class="flex-shrink-0 border-t border-light-ui-3 dark:border-dark-ui-3 px-4 pt-3 pb-4"
    >
        <div class="max-w-4xl mx-auto space-y-2 relative">
            <!-- AssistantPicker Overlay -->
            {#if pickerOpen}
                <AssistantPicker
                    assistants={availableAssistants}
                    onselect={handleAssistantSelect}
                    onclose={handlePickerClose}
                />
            {/if}

            <!-- Konversationskosten -->
            {#if (granularity === "conversation" || granularity === "both") && totalCostUsd != null}
                <div
                    class="text-xs text-right text-light-tx-2 dark:text-dark-tx-2"
                >
                    Kosten dieses Chats: {formatCostEur(
                        totalCostUsd,
                        $budget?.eur_usd_rate,
                    )} €
                </div>
            {/if}

            <!-- Assistent-Chip (nur bei neuer Konversation mit gewähltem Assistenten) -->
            {#if selectedAssistant && !conversationId && !conversationAssistant}
                <div class="flex items-center gap-1.5">
                    <span
                        class="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs
                                 bg-light-bl/15 dark:bg-dark-bl/15
                                 text-light-bl dark:text-dark-bl
                                 border border-light-bl/30 dark:border-dark-bl/30"
                    >
                        <Bot class="w-3 h-3" />
                        {selectedAssistant.name}
                    </span>
                    <button
                        onclick={() => {
                            selectedAssistant = null;
                        }}
                        class="text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx"
                        title="Assistenten entfernen"
                    >
                        <X class="w-3 h-3" />
                    </button>
                </div>
            {/if}

            <!-- Eingabe-Zeile: Upload + Textarea + Send -->
            <div class="flex gap-2 items-start">
                <input
                    bind:this={fileInput}
                    type="file"
                    multiple
                    accept={ACCEPTED_EXTENSIONS.join(",")}
                    onchange={handleFilesSelected}
                    class="sr-only"
                    aria-hidden="true"
                />
                <!-- Upload-Button -->
                <button
                    type="button"
                    onclick={handleUploadClick}
                    disabled={isStreaming || attachments.length >= MAX_FILES}
                    title={attachments.length >= MAX_FILES
                        ? `Maximal ${MAX_FILES} Anhänge`
                        : "Datei hochladen"}
                    aria-label="Datei hochladen"
                    class="p-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                         text-light-tx-2 dark:text-dark-tx-2
                         hover:bg-light-ui dark:hover:bg-dark-ui
                         disabled:opacity-40 disabled:cursor-not-allowed shrink-0
                         transition-colors"
                >
                    <Paperclip class="w-5 h-5" />
                </button>

                <!-- Textarea -->
                <textarea
                    bind:this={textarea}
                    rows={textAreaRows}
                    onkeydown={handleKeydown}
                    oninput={handleInput}
                    bind:value={input}
                    disabled={isStreaming}
                    placeholder={isStreaming ? "" : "Nachricht eingeben…"}
                    class="flex-1 resize-none rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                           px-3 py-2
                           disabled:opacity-50 disabled:cursor-not-allowed
                           focus:outline-none focus:ring-2 focus:ring-primary"
                ></textarea>

                <!-- Send-Button -->
                <button
                    onclick={handleSubmit}
                    disabled={isStreaming ||
                        attachments.some((a) => a.status === "uploading") ||
                        (!input.trim() &&
                            !attachments.some((a) => a.status === "ready"))}
                    class="p-2 bg-primary text-white rounded-lg
                         hover:bg-primary-dark disabled:opacity-50 disabled:cursor-not-allowed
                         transition-colors flex items-center justify-center min-w-[44px] shrink-0"
                >
                    {#if isStreaming}
                        <Loader2 class="w-5 h-5 animate-spin" />
                    {:else}
                        <Send class="w-5 h-5" />
                    {/if}
                </button>
            </div>

            <!-- Attachment-Chips (nur wenn Anhänge vorhanden) -->
            {#if attachments.length > 0}
                <div class="flex flex-wrap gap-1.5">
                    {#each attachments as att (att.id)}
                        <AttachmentChip
                            filename={att.filename}
                            status={att.status}
                            error={att.error}
                            onremove={() => removeAttachment(att.id)}
                        />
                    {/each}
                </div>
            {/if}

            <!-- Toolbar-Zeile: Modell-Auswahl / Assistenten-Anzeige + Hinweistexte -->
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
                {#if conversationAssistant || selectedAssistant}
                    <!-- Assistenten-Anzeige statt Modell -->
                    <span
                        class="flex items-center gap-1.5 text-xs text-light-bl dark:text-dark-bl shrink-0"
                    >
                        <Bot class="w-3.5 h-3.5" />
                        {conversationAssistant?.name || selectedAssistant?.name}
                    </span>
                {:else}
                    <!-- Modell-Auswahl -->
                    <div class="flex items-center gap-1.5 shrink-0">
                        <label
                            for="chat-model"
                            class="text-xs text-light-tx-2 dark:text-dark-tx-2 whitespace-nowrap"
                        >
                            Modell
                        </label>
                        {#if conversationId}
                            <select
                                id="chat-model"
                                disabled={true}
                                class="rounded border border-light-ui-3 dark:border-dark-ui-3
                                       bg-light-ui dark:bg-dark-ui
                                       px-1.5 py-0.5 text-xs text-light-tx dark:text-dark-tx
                                       opacity-60 cursor-not-allowed"
                                value={currentConversationModel || ""}
                            >
                                {#if currentConversationModel}
                                    <option value={currentConversationModel}
                                        >{currentConversationModel}</option
                                    >
                                {:else}
                                    <option value="">Unbekannt</option>
                                {/if}
                            </select>
                        {:else}
                            <select
                                id="chat-model"
                                bind:value={selectedModelId}
                                disabled={isStreaming || modelsLoading}
                                onchange={handleModelChange}
                                class="rounded border border-light-ui-3 dark:border-dark-ui-3
                                       bg-light-bg-2 dark:bg-dark-bg-2
                                       px-1.5 py-0.5 text-xs text-light-tx dark:text-dark-tx
                                       disabled:opacity-60"
                            >
                                {#if availableModels.length > 0}
                                    {#each availableModels as model}
                                        <option value={model.id}
                                            >{model.id}</option
                                        >
                                    {/each}
                                {:else}
                                    <option value={selectedModelId || ""}>
                                        {selectedModelId ||
                                            "Standardmodell (Backend)"}
                                    </option>
                                {/if}
                            </select>
                        {/if}
                    </div>
                {/if}

                <!-- Modell-Statustexte (Laden / Fehler / Fix-Hinweis) -->
                {#if conversationId && !conversationAssistant}
                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                        Im laufenden Chat kann das Modell nicht geändert werden.
                    </span>
                {:else if modelsLoading}
                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                        Modelle werden geladen…
                    </span>
                {:else if modelsError}
                    <span class="text-xs text-light-re dark:text-dark-re"
                        >{modelsError}</span
                    >
                {/if}
            </div>
            <div>
                <!-- Globaler Hinweistext -->
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                    KI kann Fehler machen. Ergebnisse immer kritisch prüfen.
                    Verwende <code>/</code> um Assistenten zu starten.
                </p>
            </div>
        </div>
    </div>
</div>
