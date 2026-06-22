<script>
    import { onMount, onDestroy } from "svelte";
    import { goto } from "$app/navigation";
    import { page } from "$app/stores";
    import {
        Bot,
        Send,
        Check,
        Loader2,
        AlertCircle,
        Play,
        RotateCcw,
        X,
        Eye,
        EyeOff,
        Download,
        Upload,
        Trash2,
    } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";
    import MessageBubble from "$lib/components/MessageBubble.svelte";
    import {
        getModels,
        getSubjects,
        getMyGroups,
        getAllGroups,
        getMyAssistant,
        createAssistant,
        updateAssistant,
        activateAssistant,
        deactivateAssistant,
        submitMyAssistant,
        exportAssistant,
        approveAssistant,
        rejectAssistant,
        streamChat,
        getAssistantDocuments,
        uploadAssistantDocument,
        deleteAssistantDocument,
        getContextAnchors,
        addContextAnchor,
        deleteContextAnchor,
        searchContextNodesLegacy,
        getAugmentations,
        ApiError,
    } from "$lib/api.js";
    import { user } from "$lib/stores/user.js";
    import { refreshPendingCount } from "$lib/stores/pendingAssistants.js";

    // ── Props ─────────────────────────────────────────────────────────────────
    let {
        assistantId, // string: "neu" oder numerische ID
        isAdmin, // boolean: steuert Admin-spezifische UI
        backUrl, // string: Ziel des Schließen-Buttons
    } = $props();

    // ── State ─────────────────────────────────────────────────────────────────
    let form = $state(emptyForm());
    let savedForm = $state(emptyForm());
    let loading = $state(true);
    let saving = $state(false);
    let submitting = $state(false);
    let error = $state(null);
    let success = $state(null);

    // Daten für Dropdowns
    let models = $state([]);
    let subjects = $state([]);
    let groups = $state([]);
    let augmentations = $state([]); // [{ key, label }] — Lernverhalten-Leitplanken

    // Augmentierungs-Abschnitt nur bei Schüler-Zielgruppen (student/all) zeigen.
    let showAugmentations = $derived(
        (form.audience === "student" || form.audience === "all") &&
            augmentations.length > 0,
    );

    function isAugmentationActive(key) {
        return !form.disabled_augmentations.includes(key);
    }

    function toggleAugmentation(key, active) {
        const without = form.disabled_augmentations.filter((k) => k !== key);
        form.disabled_augmentations = active ? without : [...without, key];
    }

    // Testchat State
    let testConversationId = $state(null);
    let testMessages = $state([]);
    let testInput = $state("");
    let testIsStreaming = $state(false);
    let testError = $state(null);
    let testTextarea = $state(null);
    let testAreaRows = $state(1);

    // Admin: Approve/Reject State
    let rejectDialogOpen = $state(false);
    let rejectReason = $state("");
    let approving = $state(false);
    let rejecting = $state(false);

    // Dokument-State
    let documents = $state([]);
    let docUploading = $state(false);
    let docError = $state(null);

    // Kontext-Anker State (KS-Phase-3 Schritt 5)
    let retrievalAnchors = $state([]);
    let anchorQuery = $state("");
    let anchorSearchResults = $state([]);
    let anchorSearchLoading = $state(false);
    let anchorError = $state(null);

    // Content-Types für Retrieval-Scope
    const SCOPE_CONTENT_TYPES = [
        "fachplan", "leitidee", "pk_gruppe", "curriculum", "themengebiet",
        "unterrichtseinheit", "unterrichtsstunde",
    ];

    const MAX_DOCS = 3;
    const MAX_TOTAL_TOKENS = 15_000;
    const WARN_TOKENS = 10_000;

    let totalTokens = $derived(documents.reduce((sum, d) => sum + d.token_estimate, 0));

    // Verfügbarkeits-Zusammenfassung
    function formatAvailDate(dateStr) {
        if (!dateStr) return null;
        const [year, month, day] = dateStr.split("-").map(Number);
        return new Date(year, month - 1, day).toLocaleDateString("de-DE", {
            day: "numeric",
            month: "short",
            year: "numeric",
        });
    }

    let availabilitySummary = $derived((() => {
        const from = form.available_from;
        const until = form.available_until;
        if (!from && !until) return "Zeitlich unbegrenzt";
        if (from && !until) return `Ab ${formatAvailDate(from)} verfügbar`;
        if (!from && until) return `Verfügbar bis ${formatAvailDate(until)}`;
        return `Aktiv vom ${formatAvailDate(from)} bis ${formatAvailDate(until)}`;
    })());

    // Dokumente laden wenn Assistent bekannt (nicht neu)
    async function loadDocuments() {
      if (!form.id) return;
      try {
        documents = await getAssistantDocuments(form.id);
      } catch {
        // Fehler nicht anzeigen — UI-Einschränkung bei fehlendem Zugriff
      }
    }

    // ── Kontext-Anker Funktionen (KS-Phase-3 Schritt 5) ───────────────────────

    /**
     * Lädt die Kontext-Anker für den Assistenten
     */
    async function loadContextAnchors() {
      if (!form.id) return;
      try {
        const anchors = await getContextAnchors(form.id);
        retrievalAnchors = anchors.filter((a) => a.role === "retrieval_scope");
      } catch (e) {
        // Fehler nicht anzeigen
      }
    }

    /**
     * Sucht nach Kontext-Knoten (mit Debounce)
     */
    let searchTimeout;
    async function searchAnchorNodes() {
      if (anchorQuery.length < 2) {
        anchorSearchResults = [];
        return;
      }
      anchorSearchLoading = true;
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(async () => {
        try {
          anchorSearchResults = await searchContextNodesLegacy(anchorQuery, SCOPE_CONTENT_TYPES);
        } catch (e) {
          anchorError = e.message ?? "Suche fehlgeschlagen";
          anchorSearchResults = [];
        } finally {
          anchorSearchLoading = false;
        }
      }, 300);
    }

    /**
     * Fügt einen neuen Kontext-Anker hinzu
     */
    async function addAnchor(node) {
      if (!form.id) return;
      
      const already = retrievalAnchors.some((a) => a.node_id === node.id);
      if (already) return;

      try {
        const anchor = await addContextAnchor(form.id, node.id, "retrieval_scope");
        retrievalAnchors = [...retrievalAnchors, anchor];
        anchorQuery = "";
        anchorSearchResults = [];
        anchorError = null;
      } catch (e) {
        anchorError = e.message ?? "Fehler beim Hinzufügen";
      }
    }

    /**
     * Entfernt einen Kontext-Anker
     */
    async function removeAnchor(anchor) {
      if (!form.id) return;
      
      try {
        await deleteContextAnchor(form.id, anchor.node_id, "retrieval_scope");
        retrievalAnchors = retrievalAnchors.filter((a) => a.node_id !== anchor.node_id);
        anchorError = null;
      } catch (e) {
        anchorError = e.message ?? "Fehler beim Entfernen";
      }
    }

    async function handleDocUpload(event) {
      const file = event.target.files?.[0];
      if (!file) return;
      docError = null;
      docUploading = true;
      try {
        // Neuen Assistenten automatisch speichern, bevor das erste Dokument hochgeladen wird
        if (!form.id) {
          if (!form.name.trim() || !form.system_prompt.trim() || !form.model) {
            docError = "Bitte zuerst Name, System-Prompt und Modell ausfüllen.";
            return;
          }
          const result = await createAssistant(buildPayload());
          form.id = result.id;
          savedForm = { ...form };
          // URL aktualisieren ohne SvelteKit-Navigation (Komponente bleibt gemountet)
          history.replaceState({}, "", `${backUrl}/${result.id}`);
        }
        await uploadAssistantDocument(form.id, file);
        documents = await getAssistantDocuments(form.id);
      } catch (e) {
        docError = e.message ?? "Upload fehlgeschlagen.";
      } finally {
        docUploading = false;
        event.target.value = "";
      }
    }

    async function handleDocDelete(docId) {
      docError = null;
      try {
        await deleteAssistantDocument(form.id, docId);
        documents = documents.filter((d) => d.id !== docId);
      } catch (e) {
        docError = e.message ?? "Löschen fehlgeschlagen.";
      }
    }

    // ── Abgeleitete Werte ─────────────────────────────────────────────────────
    let isNew = $derived(assistantId === "neu");
    const SCHOOLWIDE_SCOPES = new Set(["grade", "all_students", "all"]);
    let isDraft = $derived(isNew || form.status === "draft");
    // Lehrkräfte können auch aktive Assistenten bearbeiten, sofern kein schulweiter Scope
    // (schulweite Assistenten wurden bereits von einem Admin freigegeben)
    let canEdit = $derived(
        isAdmin ||
            isDraft ||
            (form.status === "active" && !SCHOOLWIDE_SCOPES.has(form.scope)),
    );
    let dirty = $derived(
        JSON.stringify(form) !== JSON.stringify(savedForm) || isNew,
    );

    // Scope-Optionen (alle 8 Werte für alle Rollen)
    const SCOPE_OPTIONS = [
        { value: "private", label: "Privat (Entwurf)" },
        { value: "subject_department", label: "Fachschaft" },
        { value: "teachers", label: "Alle Lehrkräfte" },
        { value: "activity_group", label: "AG / Kursgruppe" },
        { value: "teaching_group", label: "Unterrichtsgruppe" },
        { value: "grade", label: "Jahrgang" },
        { value: "all_students", label: "Alle Schüler:innen" },
        { value: "all", label: "Alle" },
    ];

    const AUDIENCE_OPTIONS = [
        { value: "student", label: "Schüler:innen" },
        { value: "teacher", label: "Lehrkräfte" },
        { value: "all", label: "Alle" },
    ];

    // Status-Stile
    const STATUS_CLASS = {
        draft: "bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2",
        pending_review:
            "bg-light-ye/20 dark:bg-dark-ye/20 text-light-ye dark:text-dark-ye",
        active: "bg-light-gr/20 dark:bg-dark-gr/20 text-light-gr dark:text-dark-gr",
        disabled:
            "bg-light-re/20 dark:bg-dark-re/20 text-light-re dark:text-dark-re",
        archived:
            "bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2",
    };
    const STATUS_LABEL = {
        draft: "Entwurf",
        pending_review: "In Prüfung",
        active: "Aktiv",
        disabled: "Deaktiviert",
        archived: "Archiviert",
    };

    // ━━━━━━━━━━━━━━━━━━━━━━ Formular-Funktionen ━━━━━━━━━━━━━━━━━━━━

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
            scope_group_id: null,
            min_grade: null,
            max_grade: null,
            tags: "",
            icon: null,
            available_from: "",
            available_until: "",
            sort_order: 0,
            tool_groups: [],
            disabled_augmentations: [],
            status: "draft",
            reject_reason: null,
        };
    }

    function needsGroup(scope) {
        return [
            "subject_department",
            "activity_group",
            "teaching_group",
        ].includes(scope);
    }

    function getFilteredGroups(scope) {
        if (!groups || groups.length === 0) return [];

        switch (scope) {
            case "teaching_group":
                return groups.filter((g) => g.type === "teaching_group");
            case "subject_department":
                return groups.filter((g) => g.type === "subject_department");
            case "activity_group":
                return groups.filter((g) => g.type === "activity_group");
            default:
                return groups;
        }
    }

    function mapAssistantToForm(a) {
        return {
            id: a.id,
            name: a.name || "",
            description: a.description || "",
            subject_id: a.subject_id || null,
            system_prompt: a.system_prompt || "",
            model: a.model || "",
            temperature: a.temperature !== null ? String(a.temperature) : null,
            max_tokens: a.max_tokens !== null ? String(a.max_tokens) : null,
            audience: a.audience || "student",
            scope: a.scope || "private",
            scope_group_id:
                a.scope_group_id !== null && a.scope_group_id !== undefined
                    ? String(a.scope_group_id)
                    : null,
            min_grade: a.min_grade !== null ? String(a.min_grade) : null,
            max_grade: a.max_grade !== null ? String(a.max_grade) : null,
            tags: (a.tags ?? []).join(", "),
            icon: a.icon || null,
            available_from: a.available_from
                ? a.available_from.split("T")[0]
                : "",
            available_until: a.available_until
                ? a.available_until.split("T")[0]
                : "",
            sort_order: a.sort_order ?? 0,
            tool_groups: a.tool_groups ?? [],
            disabled_augmentations: a.disabled_augmentations ?? [],
            status: a.status || "draft",
            reject_reason: a.reject_reason || null,
        };
    }

    function buildPayload() {
        const p = {
            name: form.name,
            description: form.description || null,
            subject_id: form.subject_id || null,
            system_prompt: form.system_prompt,
            model: form.model,
            temperature: form.temperature ? parseFloat(form.temperature) : null,
            max_tokens: form.max_tokens ? parseInt(form.max_tokens) : null,
            audience: form.audience,
            scope: form.scope,
            scope_group_id: needsGroup(form.scope)
                ? form.scope_group_id
                    ? parseInt(form.scope_group_id)
                    : null
                : null,
            min_grade:
                form.scope === "grade"
                    ? form.min_grade
                        ? parseInt(form.min_grade)
                        : null
                    : null,
            max_grade:
                form.scope === "grade"
                    ? form.max_grade
                        ? parseInt(form.max_grade)
                        : null
                    : null,
            tags: form.tags
                .split(",")
                .map((t) => t.trim())
                .filter(Boolean),
            available_from: form.available_from || null,
            available_until: form.available_until || null,
            // Greift nur in der Schüler-Behandlung; bei Lehrkraft-Zielgruppe ohne Wirkung.
            disabled_augmentations: form.disabled_augmentations,
        };
        if (isAdmin) {
            p.sort_order = parseInt(form.sort_order) || 0;
            p.tool_groups = form.tool_groups;
        }
        return p;
    }

    // ━━━━━━━━━━━━━━━━━━━━━━ Lade- / Speicher-Logik ━━━━━━━━━━━━━━━━━━

    async function load() {
        try {
            // 1. Verfügbare Modelle laden
            const modelsResult = await getModels();
            models = modelsResult.models ?? [];

            // 2. Fächer für subject_id-Dropdown laden
            const subjectsResult = await getSubjects();
            subjects = subjectsResult.items ?? [];

            // 3. Gruppen laden
            let myGroups = (await getMyGroups()).items;
            if (isAdmin && (!myGroups || myGroups.length === 0)) {
                // Admin ohne eigene Gruppen: alle Gruppen laden
                const allGroupsResult = await getAllGroups();
                myGroups = allGroupsResult.items ?? [];
            }
            groups = myGroups ?? [];

            // 3b. Lernverhalten-Augmentierungen (für Schüler-Zielgruppen)
            try {
                augmentations = (await getAugmentations()).augmentations ?? [];
            } catch {
                augmentations = []; // Editor bleibt nutzbar, Abschnitt entfällt
            }

            // 4. Assistenten-Daten laden (wenn nicht neu, oder Vorlage duplizieren)
            if (!isNew) {
                const a = await getMyAssistant(assistantId);
                form = mapAssistantToForm(a);
                // Dokumente laden für bestehenden Assistenten
                await loadDocuments();
                // Kontext-Anker laden
                await loadContextAnchors();
            } else {
                const fromId = $page.url.searchParams.get("from");
                if (fromId) {
                    const template = await getMyAssistant(fromId);
                    form = {
                        ...mapAssistantToForm(template),
                        name: `Kopie von ${template.name}`,
                        status: "draft",
                        sort_order: 0,
                        reject_reason: null,
                    };
                } else {
                    form = emptyForm();
                }
            }
            savedForm = { ...form };
        } catch (e) {
            error = e.message ?? "Fehler beim Laden der Daten";
            form = emptyForm();
            savedForm = emptyForm();
        } finally {
            loading = false;
        }
    }

    async function save() {
        if (!dirty) {
            error = "Keine Änderungen zum Speichern.";
            return;
        }

        // Pflichtfelder prüfen
        if (!form.name.trim() || !form.system_prompt.trim() || !form.model) {
            error =
                "Bitte füllen Sie alle Pflichtfelder aus (Name, System-Prompt, Modell).";
            return;
        }

        saving = true;
        error = null;
        try {
            const payload = buildPayload();
            let result;
            if (isNew) {
                result = await createAssistant(payload);
                // Umleiten zur Bearbeitungsseite mit der neuen ID
                goto(`${backUrl}/${result.id}`);
                return;
            } else {
                result = await updateAssistant(assistantId, payload);
                form.status = result.status || form.status;
            }
            savedForm = { ...form };
            success = "Änderungen wurden gespeichert.";
        } catch (e) {
            error = e.message ?? "Fehler beim Speichern";
        } finally {
            saving = false;
        }
    }

    async function submitAssistant() {
        if (dirty) {
            error = "Bitte zuerst speichern, bevor Sie einreichen.";
            return;
        }

        submitting = true;
        error = null;
        try {
            const result = await submitMyAssistant(assistantId);
            form.status = result.status || "pending_review";
            savedForm = { ...form };
            success = "Assistent wurde zur Prüfung eingereicht.";
        } catch (e) {
            error = e.message ?? "Fehler beim Einreichen";
        } finally {
            submitting = false;
        }
    }

    async function approveInEditor() {
        if (!assistantId || isNew) return;
        approving = true;
        error = null;
        try {
            await approveAssistant(assistantId);
            form.status = "active";
            savedForm = { ...savedForm, status: "active" };
            success = "Assistent wurde freigegeben.";
            await refreshPendingCount();
        } catch (e) {
            error = e.message ?? "Fehler beim Freigeben";
        } finally {
            approving = false;
        }
    }

    async function rejectInEditor() {
        if (!assistantId || isNew) return;
        rejecting = true;
        error = null;
        try {
            await rejectAssistant(assistantId, rejectReason || null);
            form.status = "draft";
            form.reject_reason = rejectReason || null;
            savedForm = { ...savedForm, status: "draft", reject_reason: rejectReason || null };
            success = "Assistent wurde abgelehnt.";
            rejectDialogOpen = false;
            rejectReason = "";
            await refreshPendingCount();
        } catch (e) {
            error = e.message ?? "Fehler beim Ablehnen";
        } finally {
            rejecting = false;
        }
    }

    function openRejectDialog() {
        rejectDialogOpen = true;
        rejectReason = "";
    }

    function closeRejectDialog() {
        rejectDialogOpen = false;
        rejectReason = "";
    }

    async function toggleActivate() {
        if (!assistantId || isNew) return;
        saving = true;
        try {
            if (form.status === "active") {
                await deactivateAssistant(assistantId);
                form.status = "disabled";
                success = "Assistent wurde deaktiviert.";
            } else {
                await activateAssistant(assistantId);
                form.status = "active";
                success = "Assistent wurde aktiviert.";
            }
            savedForm = { ...savedForm, status: form.status };
        } catch (e) {
            error = e.message ?? "Fehler beim Ändern des Status";
        } finally {
            saving = false;
        }
    }

    async function doExport() {
        const a = await getMyAssistant(assistantId);
        const slug = a.name.toLowerCase().replace(/\s+/g, "-");
        await exportAssistant(assistantId, `${slug}.yaml`);
    }

    // ━━━━━━━━━━━━━━━━━━━━━━ Testchat ━━━━━━━━━━━━━━━━━━━━━

    function adjustTestTextareaHeight() {
        if (!testTextarea) return;
        testTextarea.rows = 1;
        const rows = Math.min(Math.ceil(testTextarea.scrollHeight / 24), 6);
        testTextarea.rows = rows;
        testAreaRows = rows;
    }

    function resetTestChat() {
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

    async function sendTestMessage() {
        if (!testInput.trim() || testIsStreaming) return;

        if (dirty) {
            await save();
            if (dirty) {
                error = "Bitte speichern Sie zuerst den Assistenten.";
                return;
            }
        }

        const userMessage = testInput.trim();
        testInput = "";
        adjustTestTextareaHeight();

        testMessages = [
            ...testMessages,
            { role: "user", content: userMessage },
        ];
        testMessages = [...testMessages, { role: "assistant", content: "" }];
        testIsStreaming = true;
        testError = null;

        try {
            const history = testMessages
                .slice(0, -1)
                .map((m) => ({ role: m.role, content: m.content }));
            for await (const item of streamChat(
                history,
                testConversationId,
                null,
                Number(assistantId),
                true,
            )) {
                if (item.type === "start") {
                    testConversationId = item.conversationId;
                } else if (item.type === "title" || item.type === "cost") {
                    // ignorieren
                } else if (typeof item === "string") {
                    const last = testMessages.length - 1;
                    testMessages[last] = {
                        ...testMessages[last],
                        content: testMessages[last].content + item,
                    };
                    testMessages = testMessages;
                }
            }
        } catch (e) {
            testError = e.message ?? "Fehler beim Testen";
            if (
                testMessages.length > 0 &&
                testMessages[testMessages.length - 1].content === ""
            ) {
                testMessages = testMessages.slice(0, -1);
            }
        } finally {
            testIsStreaming = false;
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━ Lifecycle ━━━━━━━━━━━━━━━━━━━━━

    onMount(load);

    // Cleanup für Search-Timeout
    onDestroy(() => {
        clearTimeout(searchTimeout);
    });

    $effect(() => {
        if (success) {
            const t = setTimeout(() => (success = null), 3000);
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
                onclick={() => goto(backUrl)}
                class="flex items-center gap-2 text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx"
            >
                <X class="w-4 h-4" />
                Zurück
            </button>
            <span class="text-light-tx-2 dark:text-dark-tx-2">/</span>
            <Bot class="w-5 h-5 text-light-bl dark:text-dark-bl" />
            <h1 class="text-xl font-bold text-light-tx dark:text-dark-tx">
                {isNew
                    ? "Neuer Assistent"
                    : form.name || "Assistent bearbeiten"}
            </h1>
        </div>
        <div class="flex items-center gap-2">
            {#if !isNew && assistantId}
                <button
                    onclick={resetTestChat}
                    disabled={testIsStreaming}
                    class="px-3 py-1.5 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors disabled:opacity-50
                 flex items-center gap-1.5 text-sm"
                >
                    <RotateCcw class="w-4 h-4" />
                    Neuer Test
                </button>
            {/if}

            {#if isAdmin}
                <!-- Admin: Speichern + Aktivieren/Deaktivieren + Exportieren -->
                {#if !isNew}
                    {#if form.status === "pending_review"}
                        <!-- Admin bei pending_review: Freigeben/Ablehnen -->
                        <button
                            onclick={approveInEditor}
                            disabled={saving || approving}
                            class="px-3 py-1.5 text-sm rounded-lg bg-light-gr/10 dark:bg-dark-gr/10 text-light-gr dark:text-dark-gr
                   hover:bg-light-gr/20 dark:hover:bg-dark-gr/20 transition-colors
                   flex items-center gap-1.5 disabled:opacity-50"
                        >
                            {#if approving}
                                <Loader2 class="w-4 h-4 animate-spin" />
                                Freigeben...
                            {:else}
                                <Check class="w-4 h-4" />
                                Freigeben
                            {/if}
                        </button>
                        <button
                            onclick={openRejectDialog}
                            disabled={saving}
                            class="px-3 py-1.5 text-sm rounded-lg bg-light-re/10 dark:bg-dark-re/10 text-light-re dark:text-dark-re
                   hover:bg-light-re/20 dark:hover:bg-dark-re/20 transition-colors
                   flex items-center gap-1.5 disabled:opacity-50"
                        >
                            <X class="w-4 h-4" />
                            Ablehnen
                        </button>
                    {:else}
                        <!-- Admin bei anderen Status: Aktivieren/Deaktivieren -->
                        <button
                            onclick={toggleActivate}
                            disabled={saving}
                            class="px-3 py-1.5 text-sm rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                       text-light-tx dark:text-dark-tx
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                       flex items-center gap-1.5 disabled:opacity-50"
                        >
                            {#if form.status === "active"}
                                <EyeOff class="w-4 h-4" />
                                Deaktivieren
                            {:else}
                                <Eye class="w-4 h-4" />
                                Aktivieren
                            {/if}
                        </button>
                    {/if}
                {/if}
            {/if}

            <!-- Export-Button für alle Rollen — nur bei aktiven Assistenten -->
            {#if !isNew && form.status === "active"}
                <button
                    onclick={doExport}
                    disabled={saving}
                    class="px-3 py-1.5 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors disabled:opacity-50
                   flex items-center gap-1.5 text-sm"
                >
                    <Download class="w-4 h-4" />
                    Exportieren
                </button>
            {/if}

            <button
                onclick={save}
                disabled={saving ||
                    !dirty ||
                    !form.name.trim() ||
                    !form.system_prompt.trim() ||
                    !form.model}
                class="px-4 py-2 bg-primary dark:bg-primary-dark text-white rounded-lg
               hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2"
            >
                {#if saving}
                    <Loader2 class="w-4 h-4 animate-spin" />
                    Speichern...
                {:else}
                    <Check class="w-4 h-4" />
                    Speichern
                {/if}
            </button>

            {#if !isAdmin && isDraft && !isNew}
                <button
                    onclick={submitAssistant}
                    disabled={submitting || dirty}
                    class="px-4 py-2 bg-light-ye dark:bg-dark-ye text-light-tx dark:text-dark-tx rounded-lg
                 hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2"
                >
                    {#if submitting}
                        <Loader2 class="w-4 h-4 animate-spin" />
                        Einreichen...
                    {:else}
                        <Send class="w-4 h-4" />
                        Einreichen
                    {/if}
                </button>
            {/if}
        </div>
    </div>

    <!-- Hauptbereich: Zweispaltiges Layout -->
    <div class="flex-1 flex overflow-y-auto">
        <!-- Linke Spalte: Editor (ca. 45%) -->
        <div
            class="flex-1 min-w-0 lg:w-[45%] border-r border-light-ui-3 dark:border-dark-ui-3 p-4 overflow-y-auto"
        >
            {#if error}
                <div class="mb-4">
                    <ErrorBanner
                        message={error}
                        onClose={() => (error = null)}
                    />
                </div>
            {/if}
            {#if success}
                <div class="mb-4">
                    <SuccessBanner
                        message={success}
                        onClose={() => (success = null)}
                    />
                </div>
            {/if}

            {#if loading}
                <div class="flex justify-center py-8">
                    <Loader2
                        class="w-6 h-6 animate-spin text-light-tx-2 dark:text-dark-tx-2"
                    />
                </div>
            {:else}
                <div class="space-y-4">
                    <!-- Name & Beschreibung -->
                    <div class="space-y-2">
                        <label
                            for="ae-name"
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                        >
                            Name *
                        </label>
                        <input
                            id="ae-name"
                            bind:value={form.name}
                            disabled={!canEdit}
                            type="text"
                            placeholder="Name des Assistenten"
                            class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                    </div>

                    <div class="space-y-2">
                        <label
                            for="ae-description"
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                        >
                            Beschreibung
                        </label>
                        <textarea
                            id="ae-description"
                            bind:value={form.description}
                            disabled={!canEdit}
                            rows="2"
                            placeholder="Kurze Beschreibung des Assistenten"
                            class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     px-3 py-2 resize-none disabled:opacity-50 disabled:cursor-not-allowed"
                        ></textarea>
                    </div>

                    <!-- Fach-Dropdown -->
                    <div class="space-y-2">
                        <label
                            for="ae-subject"
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                        >
                            Fach
                        </label>
                        <select
                            id="ae-subject"
                            bind:value={form.subject_id}
                            disabled={!canEdit}
                            class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <option value="">— Kein Fach —</option>
                            {#each subjects as subject}
                                <option value={subject.id}
                                    >{subject.name}</option
                                >
                            {/each}
                        </select>
                    </div>

                    <!-- System-Prompt -->
                    <div class="space-y-2">
                        <label
                            for="ae-system-prompt"
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                        >
                            System-Prompt *
                        </label>
                        <textarea
                            id="ae-system-prompt"
                            bind:value={form.system_prompt}
                            disabled={!canEdit}
                            rows="8"
                            placeholder="System-Prompt für den Assistenten..."
                            class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     px-3 py-2 resize-none font-mono text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                        ></textarea>
                    </div>

                    <!-- Modell & Parameter -->
                    <div class="space-y-2">
                        <label
                            for="ae-model"
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                        >
                            Modell *
                        </label>
                        {#if models.length > 0}
                            <select
                                id="ae-model"
                                bind:value={form.model}
                                disabled={!canEdit}
                                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <option value="">— Modell auswählen —</option>
                                {#each models as model}
                                    <option value={model.id}
                                        >{model.label || model.id}{model.supports_function_calling === true ? ' ⚙' : ''}</option
                                    >
                                {/each}
                            </select>
                        {:else}
                            <input
                                id="ae-model"
                                bind:value={form.model}
                                disabled={!canEdit}
                                type="text"
                                placeholder="openai/gpt-4o-mini"
                                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                        {/if}
                    </div>

                    <div class="grid grid-cols-2 gap-4">
                        <div class="space-y-2">
                            <label
                                for="ae-temperature"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                            >
                                Temperatur
                            </label>
                            <input
                                id="ae-temperature"
                                bind:value={form.temperature}
                                disabled={!canEdit}
                                type="number"
                                min="0"
                                max="2"
                                step="0.1"
                                placeholder="0.7"
                                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                        </div>
                        <div class="space-y-2">
                            <label
                                for="ae-max-tokens"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                            >
                                Max. Tokens
                            </label>
                            <input
                                id="ae-max-tokens"
                                bind:value={form.max_tokens}
                                disabled={!canEdit}
                                type="number"
                                min="1"
                                placeholder="1000"
                                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                        </div>
                    </div>

                    <!-- Zielgruppe & Sichtbarkeit -->
                    <div class="grid grid-cols-2 gap-4">
                        <div class="space-y-2">
                            <label
                                for="ae-audience"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                            >
                                Zielgruppe
                            </label>
                            <select
                                id="ae-audience"
                                bind:value={form.audience}
                                disabled={!canEdit}
                                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {#each AUDIENCE_OPTIONS as opt}
                                    <option value={opt.value}
                                        >{opt.label}</option
                                    >
                                {/each}
                            </select>
                        </div>
                        <div class="space-y-2">
                            <label
                                for="ae-scope"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                            >
                                Sichtbarkeit
                            </label>
                            <select
                                id="ae-scope"
                                bind:value={form.scope}
                                disabled={!canEdit}
                                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {#each SCOPE_OPTIONS as opt}
                                    <option value={opt.value}
                                        >{opt.label}</option
                                    >
                                {/each}
                            </select>
                        </div>
                    </div>

                    <!-- Hinweis: all-Assistenten verhalten sich rollenabhängig (D1) -->
                    {#if form.audience === "all"}
                        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 -mt-2">
                            Bei der Zielgruppe „Alle" verhält sich der Assistent für
                            <strong>Schüler:innen</strong> pädagogisch geformt (Denkanstöße statt
                            Komplettlösungen) und für <strong>Lehrkräfte</strong> direkt und
                            vollständig.
                        </p>
                    {/if}

                    <!-- Lernverhalten-Leitplanken (nur Schüler-Zielgruppen) -->
                    {#if showAugmentations}
                        <div
                            class="space-y-2 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 p-3"
                        >
                            <span
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                            >
                                Lernverhalten-Leitplanken
                            </span>
                            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                Gelten nur für Schüler:innen. Abgewählte Leitplanken werden für
                                diesen Assistenten nicht angewendet.
                            </p>
                            {#each augmentations as aug (aug.key)}
                                <label
                                    class="flex items-center gap-2 text-sm text-light-tx dark:text-dark-tx cursor-pointer"
                                >
                                    <input
                                        type="checkbox"
                                        checked={isAugmentationActive(aug.key)}
                                        disabled={!canEdit}
                                        onchange={(e) =>
                                            toggleAugmentation(
                                                aug.key,
                                                e.currentTarget.checked,
                                            )}
                                        class="rounded border-light-ui-3 dark:border-dark-ui-3"
                                    />
                                    {aug.label}
                                </label>
                            {/each}
                        </div>
                    {/if}

                    <!-- scope_group_id (konditionell) -->
                    {#if needsGroup(form.scope)}
                        <div class="space-y-2">
                            <label
                                for="ae-scope-group"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                            >
                                Gruppe
                            </label>
                            {#if getFilteredGroups(form.scope).length > 0}
                                <select
                                    id="ae-scope-group"
                                    bind:value={form.scope_group_id}
                                    disabled={!canEdit}
                                    class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                         bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                         px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    <option value=""
                                        >— Gruppe auswählen —</option
                                    >
                                    {#each getFilteredGroups(form.scope) as group}
                                        <option value={group.id}
                                            >{group.name}</option
                                        >
                                    {/each}
                                </select>
                            {:else}
                                <p
                                    class="text-sm text-light-tx-3 dark:text-dark-tx-3 italic"
                                >
                                    Keine passenden Gruppen gefunden.
                                </p>
                            {/if}
                        </div>
                    {/if}

                    <!-- Jahrgang (konditionell für grade-Scope) -->
                    {#if form.scope === "grade"}
                        <div class="grid grid-cols-2 gap-4">
                            <div class="space-y-2">
                                <label
                                    for="ae-min-grade"
                                    class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                                >
                                    Jahrgang von
                                </label>
                                <input
                                    id="ae-min-grade"
                                    bind:value={form.min_grade}
                                    disabled={!canEdit}
                                    type="number"
                                    min="1"
                                    max="13"
                                    placeholder="5"
                                    class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                         bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                         px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                />
                            </div>
                            <div class="space-y-2">
                                <label
                                    for="ae-max-grade"
                                    class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                                >
                                    Jahrgang bis
                                </label>
                                <input
                                    id="ae-max-grade"
                                    bind:value={form.max_grade}
                                    disabled={!canEdit}
                                    type="number"
                                    min="1"
                                    max="13"
                                    placeholder="10"
                                    class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                         bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                         px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                />
                            </div>
                        </div>
                    {/if}

                    <!-- Tags -->
                    <div class="space-y-2">
                        <label
                            for="ae-tags"
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                        >
                            Tags (kommagetrennt)
                        </label>
                        <input
                            id="ae-tags"
                            bind:value={form.tags}
                            disabled={!canEdit}
                            type="text"
                            placeholder="mathe, physik, hilfe"
                            class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                     bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                     px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                    </div>

                    <!-- Kontext-Dokumente -->
                    <div class="space-y-3">
                        <div class="flex items-center justify-between">
                          <span class="block text-sm font-medium text-light-tx dark:text-dark-tx">
                            Kontext-Dokumente
                          </span>
                          <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                            {totalTokens.toLocaleString("de")} / {MAX_TOTAL_TOKENS.toLocaleString("de")} Tokens
                          </span>
                        </div>

                        <!-- Token-Fortschrittsbalken -->
                        <div class="h-1.5 w-full rounded-full bg-light-ui-2 dark:bg-dark-ui-2 overflow-hidden">
                          <div
                            class="h-full rounded-full transition-all"
                            class:bg-light-gr={totalTokens < WARN_TOKENS}
                            class:dark:bg-dark-gr={totalTokens < WARN_TOKENS}
                            class:bg-light-ye={totalTokens >= WARN_TOKENS && totalTokens < MAX_TOTAL_TOKENS}
                            class:dark:bg-dark-ye={totalTokens >= WARN_TOKENS && totalTokens < MAX_TOTAL_TOKENS}
                            class:bg-light-re={totalTokens >= MAX_TOTAL_TOKENS}
                            class:dark:bg-dark-re={totalTokens >= MAX_TOTAL_TOKENS}
                            style="width: {Math.min((totalTokens / MAX_TOTAL_TOKENS) * 100, 100)}%"
                          ></div>
                        </div>

                        <!-- Warnhinweis ab 10 000 Tokens -->
                        {#if totalTokens >= WARN_TOKENS}
                          <p class="text-xs text-light-ye dark:text-dark-ye">
                            Diese Dokumente verbrauchen bei jedem Chat-Turn ca. {totalTokens.toLocaleString("de")} Tokens Kontext.
                            Bei langen Gesprächen kann das Kontextfenster erschöpft werden.
                          </p>
                        {/if}

                        <!-- Hochgeladene Dokumente -->
                        {#if documents.length > 0}
                          <ul class="space-y-1.5">
                            {#each documents as doc (doc.id)}
                              <li class="flex items-center justify-between gap-3 px-3 py-2 rounded-lg
                          bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3">
                                <div class="flex-1 min-w-0">
                                  <span class="text-sm text-light-tx dark:text-dark-tx truncate block">{doc.filename}</span>
                                  <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    {(doc.size_bytes / 1024).toFixed(1)} KB · ~{doc.token_estimate.toLocaleString("de")} Tokens
                                  </span>
                                </div>
                                <button
                                  type="button"
                                  onclick={() => handleDocDelete(doc.id)}
                                  class="p-1.5 rounded-md hover:bg-light-re/10 dark:hover:bg-dark-re/10
                         text-light-tx-2 dark:text-dark-tx-2 hover:text-light-re dark:hover:text-dark-re
                         transition-colors shrink-0"
                                  title="Dokument entfernen"
                                >
                                  <Trash2 size={14} />
                                </button>
                              </li>
                            {/each}
                          </ul>
                        {/if}

                        <!-- Upload-Button (ausgeblendet wenn Limit erreicht) -->
                        {#if documents.length < MAX_DOCS}
                          <label class="flex items-center gap-2 px-3 py-2 rounded-lg border border-dashed
                         border-light-ui-3 dark:border-dark-ui-3 cursor-pointer
                         hover:border-primary dark:hover:border-primary-dark
                         text-sm text-light-tx-2 dark:text-dark-tx-2 transition-colors
                         {docUploading ? 'opacity-50 pointer-events-none' : ''}">
                            <Upload size={14} />
                            {#if docUploading}
                              Wird hochgeladen…
                            {:else}
                              PDF, TXT oder Markdown hochladen (max. 2 MB)
                            {/if}
                            <input
                              type="file"
                              accept=".pdf,.txt,.md"
                              class="sr-only"
                              onchange={handleDocUpload}
                              disabled={docUploading}
                            />
                          </label>
                        {:else}
                          <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                            Maximal {MAX_DOCS} Dokumente erreicht.
                          </p>
                        {/if}

                        <!-- Fehlermeldung -->
                        {#if docError}
                          <p class="text-sm text-light-re dark:text-dark-re">{docError}</p>
                        {/if}
                    </div>

                    <!-- Wissenskontext (KS-Phase-3 Schritt 5) -->
                    <div class="space-y-3">
                        <h3 class="block text-sm font-medium text-light-tx dark:text-dark-tx">
                            Wissenskontext
                        </h3>

                        <div class="anchor-search relative">
                            <input
                                type="text"
                                placeholder="Wissensgebiet suchen…"
                                bind:value={anchorQuery}
                                oninput={searchAnchorNodes}
                                disabled={!canEdit}
                                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                         bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                         px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                            {#if anchorSearchLoading}
                                <div class="absolute right-3 top-1/2 -translate-y-1/2">
                                    <Loader2 class="w-4 h-4 animate-spin text-light-tx-2 dark:text-dark-tx-2" />
                                </div>
                            {/if}
                            {#if anchorSearchResults.length > 0 && anchorQuery.length >= 2}
                                <ul class="absolute top-full left-0 right-0 mt-1 z-10 max-h-48 overflow-y-auto
                            border border-light-ui-3 dark:border-dark-ui-3 rounded-lg
                            bg-light-bg-2 dark:bg-dark-bg-2 shadow-lg">
                                    {#each anchorSearchResults as node}
                                        <li class="px-3 py-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 cursor-pointer">
                                            <button
                                                type="button"
                                                onclick={() => addAnchor(node)}
                                                class="w-full text-left flex items-center gap-2 text-light-tx dark:text-dark-tx"
                                            >
                                                <span>{node.title}</span>
                                                {#if node.content_type}
                                                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2
                                                        bg-light-ui-2 dark:bg-dark-ui-2 px-1.5 py-0.5 rounded-full">
                                                        {node.content_type}
                                                    </span>
                                                {/if}
                                            </button>
                                        </li>
                                    {/each}
                                </ul>
                            {/if}
                        </div>

                        <div class="anchor-tags flex flex-wrap gap-2">
                            {#each retrievalAnchors as anchor}
                                <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg
                            bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3
                            text-sm text-light-tx dark:text-dark-tx">
                                    {anchor.node_title}
                                    <button
                                        type="button"
                                        onclick={() => removeAnchor(anchor)}
                                        disabled={!canEdit}
                                        class="p-0.5 rounded-md hover:bg-light-re/10 dark:hover:bg-dark-re/10
                               text-light-tx-2 dark:text-dark-tx-2 hover:text-light-re dark:hover:text-dark-re
                               transition-colors disabled:opacity-50"
                                        title="Anker entfernen"
                                    >
                                        <X size={12} />
                                    </button>
                                </span>
                            {/each}
                        </div>

                        {#if anchorError}
                            <p class="text-sm text-light-re dark:text-dark-re">{anchorError}</p>
                        {/if}

                        {#if retrievalAnchors.length > 0}
                            <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                Der Assistent sucht in allen Knoten, die diesen Wissensgebieten zugeordnet sind.
                            </p>
                        {/if}
                    </div>

                    <!-- Verfügbarkeit -->
                    <div class="grid grid-cols-2 gap-4">
                        <div class="space-y-2">
                            <label
                                for="ae-available-from"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                            >
                                Verfügbar von
                            </label>
                            <input
                                id="ae-available-from"
                                bind:value={form.available_from}
                                disabled={!canEdit}
                                type="date"
                                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                        </div>
                        <div class="space-y-2">
                            <label
                                for="ae-available-until"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                            >
                                Verfügbar bis
                            </label>
                            <input
                                id="ae-available-until"
                                bind:value={form.available_until}
                                disabled={!canEdit}
                                type="date"
                                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                        </div>
                    </div>

                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 flex items-center gap-1.5">
                        {#if form.available_from || form.available_until}
                            <span class="inline-block w-1.5 h-1.5 rounded-full bg-light-gr dark:bg-dark-gr shrink-0"></span>
                        {:else}
                            <span class="inline-block w-1.5 h-1.5 rounded-full bg-light-ui-3 dark:bg-dark-ui-3 shrink-0"></span>
                        {/if}
                        {availabilitySummary}
                    </p>

                    <!-- Admin-only: Sortier-Reihenfolge + Werkzeuge -->
                    {#if isAdmin}
                        <div class="space-y-2">
                            <label
                                for="ae-sort-order"
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                            >
                                Sortier-Reihenfolge
                            </label>
                            <input
                                id="ae-sort-order"
                                bind:value={form.sort_order}
                                type="number"
                                placeholder="0"
                                class="w-full rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2"
                            />
                        </div>

                        <div class="space-y-2">
                            <span class="block text-sm font-medium text-light-tx dark:text-dark-tx">
                                Werkzeuge
                            </span>
                            <label class="flex items-center gap-2 text-sm text-light-tx dark:text-dark-tx cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={form.tool_groups.includes('planning')}
                                    onchange={(e) => {
                                        if (e.currentTarget.checked) {
                                            form.tool_groups = [...form.tool_groups.filter(g => g !== 'planning'), 'planning']
                                        } else {
                                            form.tool_groups = form.tool_groups.filter(g => g !== 'planning')
                                        }
                                    }}
                                    class="rounded border-light-ui-3 dark:border-dark-ui-3"
                                />
                                Unterrichtsplanung
                                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                    (Jahresplan, Slot-Zuweisung, Themen)
                                </span>
                            </label>
                        </div>
                    {/if}

                    <!-- Status-Anzeige (nur bei bestehendem Assistenten) -->
                    {#if !isNew}
                        <div
                            class="space-y-2 pt-2 border-t border-light-ui-3 dark:border-dark-ui-3"
                        >
                            <span
                                class="block text-sm font-medium text-light-tx dark:text-dark-tx"
                            >
                                Status
                            </span>
                            <div class="flex items-center gap-3">
                                <span
                                    class="px-2 py-1 rounded-full text-xs {STATUS_CLASS[
                                        form.status
                                    ] || STATUS_CLASS.draft}"
                                >
                                    {STATUS_LABEL[form.status] || form.status}
                                </span>
                            </div>
                            {#if !isAdmin && form.reject_reason}
                                <div
                                    class="flex items-start gap-2 text-sm text-light-re dark:text-dark-re"
                                >
                                    <AlertCircle
                                        class="w-4 h-4 shrink-0 mt-0.5"
                                    />
                                    <span>{form.reject_reason}</span>
                                </div>
                            {/if}
                        </div>
                    {/if}
                </div>
            {/if}
        </div>

        <!-- Rechte Spalte: Testchat (ca. 55%) -->
        <div class="flex-1 min-w-0 lg:w-[55%] p-4 overflow-y-auto">
            <div class="h-full flex flex-col">
                <!-- Testchat Header -->
                <div class="flex items-center justify-between mb-4">
                    <div class="flex items-center gap-2">
                        <Play class="w-5 h-5 text-light-gr dark:text-dark-gr" />
                        <h2
                            class="text-lg font-semibold text-light-tx dark:text-dark-tx"
                        >
                            Testchat
                        </h2>
                    </div>
                    <span class="text-xs text-light-tx-3 dark:text-dark-tx-3">
                        Modell: {form.model || "—"}
                    </span>
                </div>

                {#if isNew}
                    <div
                        class="flex-1 flex items-center justify-center text-light-tx-2 dark:text-dark-tx-2"
                    >
                        <p>
                            Speichern Sie den Assistenten zuerst, um den
                            Testchat zu nutzen.
                        </p>
                    </div>
                {:else if !form.model}
                    <div
                        class="flex-1 flex items-center justify-center text-light-tx-2 dark:text-dark-tx-2"
                    >
                        <p>
                            Wählen Sie ein Modell aus, um den Testchat zu
                            nutzen.
                        </p>
                    </div>
                {:else}
                    <!-- Nachrichtenbereich -->
                    <div class="flex-1 overflow-y-auto space-y-4 mb-4 min-h-0">
                        {#if testMessages.length === 0}
                            <div
                                class="flex items-center justify-center h-full text-light-tx-3 dark:text-dark-tx-3"
                            >
                                <p>
                                    Stellen Sie dem Assistenten eine Testfrage.
                                </p>
                            </div>
                        {:else}
                            {#each testMessages as message, i}
                                <MessageBubble
                                    {message}
                                    isStreaming={testIsStreaming &&
                                        i === testMessages.length - 1 &&
                                        message.role === "assistant"}
                                />
                            {/each}
                        {/if}
                        {#if testError}
                            <div class="flex justify-center">
                                <span
                                    class="text-light-re dark:text-dark-re text-sm"
                                    >{testError}</span
                                >
                            </div>
                        {/if}
                    </div>

                    <!-- Eingabebereich -->
                    <div
                        class="border-t border-light-ui-3 dark:border-dark-ui-3 pt-4"
                    >
                        <div class="flex gap-2">
                            <textarea
                                bind:this={testTextarea}
                                bind:value={testInput}
                                rows={testAreaRows}
                                onkeydown={handleTestKeydown}
                                oninput={adjustTestTextareaHeight}
                                disabled={testIsStreaming}
                                placeholder={testIsStreaming
                                    ? "..."
                                    : "Testfrage eingeben…"}
                                class="flex-1 resize-none rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx
                       px-3 py-2 disabled:opacity-50"
                            ></textarea>
                            <button
                                onclick={sendTestMessage}
                                disabled={testIsStreaming || !testInput.trim()}
                                class="p-2 bg-primary dark:bg-primary-dark text-white rounded-lg
                       hover:opacity-90 transition-opacity disabled:opacity-50
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

<!-- Ablehnen-Dialog (Modal) - nur Admin, nur bei pending_review -->
{#if isAdmin && !isNew && form.status === "pending_review" && rejectDialogOpen}
    <div
        class="fixed inset-0 bg-black/50 z-40"
        onclick={closeRejectDialog}
        onkeydown={(e) => e.key === 'Escape' && closeRejectDialog()}
        role="presentation"
    ></div>
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
                <p class="text-sm text-light-tx-3 dark:text-dark-tx-3 mt-1">
                    Begründung (optional) — wird der Lehrkraft im Editor angezeigt.
                </p>
            </div>
        </div>

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
                onclick={closeRejectDialog}
                disabled={rejecting}
                class="px-4 py-2 bg-light-ui dark:bg-dark-ui text-light-tx dark:text-dark-tx rounded-lg
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors disabled:opacity-50"
            >
                Abbrechen
            </button>
            <button
                onclick={rejectInEditor}
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
