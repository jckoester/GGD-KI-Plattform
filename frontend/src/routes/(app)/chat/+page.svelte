<script>
    import { Send, Loader2, AlertCircle } from "lucide-svelte";
    import { goto } from "$app/navigation";
    import { page } from "$app/stores";
    import {
        streamChat,
        ApiError,
        getConversationMessages,
        getModels,
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

    async function handleSubmit() {
        if (!input.trim() || isStreaming) return;

        const userMessage = input.trim();
        input = "";
        adjustTextareaHeight();

        // Add user message
        messages = [...messages, { role: "user", content: userMessage }];

        // Add placeholder for assistant response
        const assistantIndex = messages.length;
        messages = [...messages, { role: "assistant", content: "" }];

        isStreaming = true;
        error = null;

        try {
            // Nur user/assistant-Nachrichten senden — error-Einträge sind reine UI-Elemente
            const apiMessages = messages
                .slice(0, assistantIndex)
                .filter((m) => m.role === "user" || m.role === "assistant");

            const modelId = conversationId ? null : selectedModelId;
            for await (const item of streamChat(
                apiMessages,
                conversationId,
                modelId,
            )) {
                // Start-Event mit conversationId
                if (item.type === "start") {
                    conversationId = item.conversationId;
                    currentConversationModel =
                        selectedModelId || currentConversationModel;
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

    function handleInput() {
        adjustTextareaHeight();
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
        }
    }

    // Reagieren auf URL-Änderungen
    $effect(() => {
        $page.url;
        loadConversation();
    });

    // Stores zurücksetzen beim Verlassen der Seite
    onMount(() => {
        loadModels();
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
                <div class="flex flex-col items-center gap-2 text-gray-500">
                    <Loader2 class="w-6 h-6 animate-spin" />
                    <p>Konversation wird geladen...</p>
                </div>
            </div>
        {:else if conversationError}
            <div class="flex items-center justify-center h-full">
                <div
                    class="bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-red-600 max-w-md"
                >
                    <p class="flex items-center gap-2">
                        <AlertCircle class="w-5 h-5 flex-shrink-0" />
                        {conversationError}
                    </p>
                </div>
            </div>
        {:else if messages.length === 0}
            <div class="flex items-center justify-center h-full">
                <div class="text-center text-gray-500">
                    <p class="text-lg">Womit kann ich helfen?</p>
                </div>
            </div>
        {:else}
            <div class="space-y-4 max-w-4xl mx-auto">
                {#each messages as message, i}
                    {#if message.role === "user"}
                        <div class="flex justify-end">
                            <div
                                class="bg-blue-500 text-white rounded-xl rounded-br-none px-4 py-2 max-w-[80%]"
                            >
                                <p class="whitespace-pre-wrap">
                                    {message.content}
                                </p>
                            </div>
                        </div>
                    {:else if message.role === "assistant"}
                        <div class="flex justify-start">
                            <div
                                class="bg-gray-100 dark:bg-gray-800 rounded-xl rounded-bl-none px-4 py-2 max-w-[80%]"
                            >
                                <p class="whitespace-pre-wrap">
                                    {message.content}
                                </p>

                                {#if (granularity === "message" || granularity === "both") && message.cost_usd != null}
                                    <p
                                        class="text-xs text-gray-500 dark:text-gray-400 mt-1"
                                    >
                                        {formatCostEur(
                                            message.cost_usd,
                                            $budget?.eur_usd_rate,
                                        )} €
                                    </p>
                                {/if}
                                {#if isStreaming && i === messages.length - 1}
                                    <span class="animate-pulse cursor-default"
                                        >|</span
                                    >
                                {/if}
                            </div>
                        </div>
                    {:else if message.role === "error"}
                        <div class="w-full">
                            <div
                                class="bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-red-600"
                            >
                                <p class="whitespace-pre-wrap">
                                    {message.content}
                                </p>
                            </div>
                        </div>
                    {/if}
                {/each}
                {#if (granularity === "conversation" || granularity === "both") && totalCostUsd != null}
                    <div
                        class="text-xs text-right text-gray-500 dark:text-gray-400 mt-2"
                    >
                        Konversation: {formatCostEur(
                            totalCostUsd,
                            $budget?.eur_usd_rate,
                        )} €
                    </div>
                {/if}
            </div>
        {/if}
        <div bind:this={scrollAnchor} class="h-0"></div>
    </div>

    <div class="flex-shrink-0 px-4 pb-4">
        <div class="max-w-4xl mx-auto mb-2">
            <div class="flex flex-wrap items-center gap-2">
                <label
                    for="chat-model"
                    class="text-sm text-gray-600 dark:text-gray-300"
                    >Modell</label
                >
                {#if conversationId}
                    <select
                        id="chat-model"
                        disabled={true}
                        class="min-w-[220px] rounded-md border border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-700 px-2 py-1 text-sm text-gray-700 dark:text-gray-200"
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
                    <span class="text-xs text-gray-500"
                        >In laufenden Konversationen bleibt das Modell fix.</span
                    >
                {:else}
                    <select
                        id="chat-model"
                        bind:value={selectedModelId}
                        disabled={isStreaming || modelsLoading}
                        onchange={handleModelChange}
                        class="min-w-[220px] rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-sm text-gray-800 dark:text-gray-100 disabled:opacity-60"
                    >
                        {#if availableModels.length > 0}
                            {#each availableModels as model}
                                <option value={model.id}>{model.id}</option>
                            {/each}
                        {:else}
                            <option value={selectedModelId || ""}>
                                {selectedModelId || "Standardmodell (Backend)"}
                            </option>
                        {/if}
                    </select>
                    {#if modelsLoading}
                        <span class="text-xs text-gray-500"
                            >Modelle werden geladen...</span
                        >
                    {:else if modelsError}
                        <span class="text-xs text-red-600">{modelsError}</span>
                    {/if}
                {/if}
            </div>
        </div>

        <div class="flex gap-2 max-w-4xl mx-auto">
            <textarea
                bind:this={textarea}
                rows={textAreaRows}
                onkeydown={handleKeydown}
                oninput={handleInput}
                bind:value={input}
                disabled={isStreaming}
                placeholder={isStreaming ? "" : "Nachricht eingeben..."}
                class="flex-1 resize-none rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-blue-500"
            ></textarea>
            <button
                onclick={handleSubmit}
                disabled={isStreaming || !input.trim()}
                class="p-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-blue-300 disabled:cursor-not-allowed transition-colors flex items-center justify-center min-w-[44px]"
            >
                {#if isStreaming}
                    <Loader2 class="w-5 h-5 animate-spin" />
                {:else}
                    <Send class="w-5 h-5" />
                {/if}
            </button>
        </div>
    </div>
</div>
