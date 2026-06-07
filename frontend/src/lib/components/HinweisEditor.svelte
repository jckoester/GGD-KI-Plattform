<script>
    /**
     * HinweisEditor — Textarea mit @/# Inline-Autocomplete für Hinweise-Tokens.
     *
     * @ → Leitperspektive-Suche (global)
     * #FACH query → Cross-Fach-IK-Suche im Zielfach
     *
     * Props:
     *   value    — gebundener Textwert (zwei-Wege: bind:value)
     *   onchange — Callback bei Änderung
     */
    import { parseHinweise } from "$lib/hinweise.js";
    import HinweisChip from "./HinweisChip.svelte";

    let { value = $bindable(""), onchange = () => {} } = $props();

    // ── Dropdown-State ────────────────────────────────────────────────────────
    let dropdownOpen = $state(false);
    let dropdownItems = $state([]); // Array von {id, label, sublabel, kind:'lp'|'ik', node_id, serialized}
    let dropdownIndex = $state(0);
    let loading = $state(false);

    // Für # Cross-Fach: welches Fach wurde erkannt?
    let resolvedFachCode = $state(null); // z.B. 'ETH'
    let resolvedSubjectId = $state(null);

    let textarea;

    // Debounce-Handle
    let debounceTimer = null;

    // ── Trigger-Erkennung ─────────────────────────────────────────────────────
    function getActiveTrigger(text, cursorPos) {
        const before = text.slice(0, cursorPos);

        // @-Trigger: Leitperspektive
        const lpMatch = before.match(/@([^\s@#]*)$/);
        if (lpMatch)
            return {
                kind: "lp",
                query: lpMatch[1],
                matchStart: before.length - lpMatch[0].length,
            };

        // #-Trigger: erst Fach-Code, dann IK-Suche
        const crossMatch = before.match(/#([A-ZÄÖÜ]{2,6})(?:\s+(\S*))?$/);
        if (crossMatch) {
            return {
                kind: "ik",
                fachCode: crossMatch[1],
                query: crossMatch[2] ?? "",
                matchStart: before.length - crossMatch[0].length,
            };
        }
        return null;
    }

    // ── Suche auslösen ────────────────────────────────────────────────────────
    async function search(trigger) {
        if (trigger.kind === "lp") {
            loading = true;
            try {
                const params = new URLSearchParams({
                    content_type: "leitperspektive",
                    limit: "10",
                });
                if (trigger.query) params.set("q", trigger.query);
                const res = await fetch(`/api/context/nodes?${params}`, {
                    credentials: "include",
                });
                const nodes = res.ok ? await res.json() : [];
                dropdownItems = nodes.map((n) => ({
                    node_id: n.id,
                    label: n.title,
                    sublabel: null,
                    kind: "lp",
                    serialized: `@[${n.title}](lp:${n.id})`,
                }));
                dropdownOpen = dropdownItems.length > 0;
            } finally {
                loading = false;
            }
            return;
        }

        // kind === 'ik'
        // Schritt 1: Fach-Code auflösen (gecacht in resolvedFachCode/Id)
        if (trigger.fachCode !== resolvedFachCode) {
            resolvedFachCode = null;
            resolvedSubjectId = null;
            try {
                const res = await fetch(
                    `/api/context/subjects/by-code/${encodeURIComponent(trigger.fachCode)}`,
                    { credentials: "include" },
                );
                if (res.ok) {
                    const data = await res.json();
                    resolvedFachCode = trigger.fachCode;
                    resolvedSubjectId = data.subject_id;
                } else {
                    // Unbekannter Fach-Code → kein Dropdown
                    dropdownItems = [];
                    dropdownOpen = false;
                    return;
                }
            } catch {
                dropdownItems = [];
                dropdownOpen = false;
                return;
            }
        }

        // Schritt 2: IK im Zielfach suchen
        loading = true;
        try {
            const params = new URLSearchParams({
                content_type: "ik_kompetenz",
                subject_id: resolvedSubjectId,
                limit: "10",
            });
            if (trigger.query) params.set("q", trigger.query);
            const res = await fetch(`/api/context/nodes?${params}`, {
                credentials: "include",
            });
            const nodes = res.ok ? await res.json() : [];
            dropdownItems = nodes.map((n) => {
                const nr = extractNrFromTitle(n.title) || n.title;
                return {
                    node_id: n.id,
                    label: `${trigger.fachCode} ${nr}`,
                    sublabel: n.title,
                    kind: "ik",
                    serialized: `#[${trigger.fachCode} ${nr}](ik:${n.id})`,
                };
            });
            dropdownOpen = dropdownItems.length > 0;
        } finally {
            loading = false;
        }
    }

    function extractNrFromTitle(title) {
        const m = title.match(/(\d+\.\d+(?:\.\d+)*)/);
        return m ? m[1] : null;
    }

    // ── Input-Handler ─────────────────────────────────────────────────────────
    function handleInput(e) {
        value = e.target.value;
        onchange(value);

        const cursorPos = e.target.selectionStart ?? value.length;
        const trigger = getActiveTrigger(value, cursorPos);

        if (!trigger) {
            dropdownOpen = false;
            dropdownItems = [];
            return;
        }

        dropdownIndex = 0;
        clearTimeout(debounceTimer);
        // Für LP sofort suchen wenn Query leer; sonst 250ms debounce
        const delay = trigger.kind === "lp" && !trigger.query ? 0 : 250;
        debounceTimer = setTimeout(() => search(trigger), delay);
    }

    // ── Keyboard-Handler ─────────────────────────────────────────────────────
    function handleKeydown(e) {
        if (!dropdownOpen) return;
        if (e.key === "ArrowDown") {
            e.preventDefault();
            dropdownIndex = Math.min(
                dropdownIndex + 1,
                dropdownItems.length - 1,
            );
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            dropdownIndex = Math.max(dropdownIndex - 1, 0);
        } else if (e.key === "Enter" || e.key === "Tab") {
            if (dropdownItems.length > 0) {
                e.preventDefault();
                confirmSelection(dropdownItems[dropdownIndex]);
            }
        } else if (e.key === "Escape") {
            dropdownOpen = false;
        }
    }

    // ── Auswahl bestätigen ────────────────────────────────────────────────────
    function confirmSelection(item) {
        const cursorPos = textarea?.selectionStart ?? value.length;
        const trigger = getActiveTrigger(value, cursorPos);
        if (!trigger) return;

        const before = value.slice(0, trigger.matchStart);
        const after = value.slice(cursorPos);
        value = before + item.serialized + " " + after;
        onchange(value);

        dropdownOpen = false;
        dropdownItems = [];

        // Cursor hinter das eingefügte Token setzen
        const newPos = (before + item.serialized + " ").length;
        requestAnimationFrame(() => {
            if (textarea) {
                textarea.setSelectionRange(newPos, newPos);
                textarea.focus();
            }
        });
    }

    // ── Preview-Parts ─────────────────────────────────────────────────────────
    const previewParts = $derived(parseHinweise(value));
</script>

<div class="space-y-2">
    <!-- Eingabefeld -->
    <div class="relative">
        <textarea
            bind:this={textarea}
            bind:value
            oninput={handleInput}
            onkeydown={handleKeydown}
            onblur={() => {
                setTimeout(() => {
                    dropdownOpen = false;
                }, 200);
            }}
            rows="5"
            placeholder="Hinweise: @LP für Leitperspektive, #ETH 3.1 für Fachbezug, freier Text für alles andere etc."
            class="w-full text-sm rounded border border-light-ui-3 dark:border-dark-ui-3
                   bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx p-2 resize-none
                   focus:outline-none focus:border-primary dark:focus:border-primary-dark"
        />

        <!-- Autocomplete-Dropdown -->
        {#if dropdownOpen && dropdownItems.length > 0}
            <div
                class="absolute bottom-full left-0 right-0 mb-1 z-50
                        bg-white dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3
                        rounded-md shadow-lg max-h-56 overflow-y-auto"
            >
                {#each dropdownItems as item, i}
                    <button
                        onmousedown={(e) => {
                            e.preventDefault();
                            confirmSelection(item);
                        }}
                        class="w-full px-3 py-2 text-left text-sm flex items-start gap-2 transition-colors
                               {i === dropdownIndex
                            ? 'bg-light-ui-2 dark:bg-dark-ui-2'
                            : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                    >
                        <span
                            class="shrink-0 mt-0.5 text-xs px-1.5 py-0.5 rounded-full font-medium
                                     {item.kind === 'lp'
                                ? 'bg-light-pur/20 dark:bg-dark-pur/20 text-light-pur dark:text-dark-pur'
                                : 'bg-light-ui-3/50 dark:bg-dark-ui-3/50 text-light-tx dark:text-dark-tx'}"
                        >
                            {item.kind === "lp" ? "LP" : "IK"}
                        </span>
                        <div class="min-w-0 flex-1">
                            <div
                                class="font-medium text-light-tx dark:text-dark-tx truncate"
                            >
                                {item.label}
                            </div>
                            {#if item.sublabel}
                                <div
                                    class="text-xs text-light-tx-2 dark:text-dark-tx-2 truncate"
                                >
                                    {item.sublabel}
                                </div>
                            {/if}
                        </div>
                    </button>
                {/each}
            </div>
        {/if}
    </div>

    <!-- Live-Vorschau (nur wenn Tokens vorhanden) -->
    {#if previewParts.some((p) => p.kind !== "text")}
        <div
            class="flex flex-wrap gap-1 items-center text-xs text-light-tx-2 dark:text-dark-tx-2"
        >
            <span class="shrink-0">Vorschau:</span>
            {#each previewParts as part}
                {#if part.kind === "lp"}
                    <HinweisChip typ="leitperspektive" lp_code={part.label} />
                {:else if part.kind === "ik"}
                    <HinweisChip typ="fach_bezug" fach={part.label} />
                {:else if part.label.trim()}
                    <span class="text-light-tx dark:text-dark-tx"
                        >{part.label}</span
                    >
                {/if}
            {/each}
        </div>
    {/if}
</div>
