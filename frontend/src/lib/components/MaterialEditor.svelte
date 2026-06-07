<script>
    /**
     * MaterialEditor — Textarea mit @-Autocomplete für Knoten-Referenzen.
     *
     * @ → generische Knotensuche (alle Typen)
     * Token: @[<Titel>](node:<uuid>)
     * Freitext inkl. URLs erlaubt; URLs werden in der Vorschau verlinkt.
     *
     * TODO: Datentyp-Filter ergänzen, sobald relevante content_types festgelegt sind
     *       (→ Plaene/Todo.md „Material-Knotensuche auf Datentypen eingrenzen").
     *
     * Props:
     *   value    — gebundener Textwert (bind:value)
     *   onchange — Callback bei Änderung
     */
    import { parseMaterial } from "$lib/material.js";
    import { linkifyText } from "$lib/linkify.js";
    import { CONTENT_TYPE_LABELS } from "$lib/taxonomy.js";
    import HinweisChip from "./HinweisChip.svelte";

    let { value = $bindable(""), onchange = () => {} } = $props();

    let dropdownOpen = $state(false);
    let dropdownItems = $state([]);
    let dropdownIndex = $state(0);
    let loading = $state(false);

    let textarea;
    let debounceTimer = null;

    // ── Trigger-Erkennung ─────────────────────────────────────────────────────
    function getActiveTrigger(text, cursorPos) {
        const before = text.slice(0, cursorPos);
        const m = before.match(/@([^\s@]*)$/);
        if (m) return { query: m[1], matchStart: before.length - m[0].length };
        return null;
    }

    // ── Suche ─────────────────────────────────────────────────────────────────
    async function search(trigger) {
        loading = true;
        try {
            const params = new URLSearchParams({ limit: "10" });
            if (trigger.query) params.set("q", trigger.query);
            // TODO: content_type-Filter ergänzen (→ Plaene/Todo.md)
            const res = await fetch(`/api/context/nodes?${params}`, {
                credentials: "include",
            });
            const raw = res.ok ? await res.json() : [];
            const nodes = Array.isArray(raw) ? raw : (raw.items ?? []);
            dropdownItems = nodes.map((n) => ({
                node_id: n.id,
                label: n.title,
                sublabel: CONTENT_TYPE_LABELS[n.content_type] ?? n.content_type,
                serialized: `@[${n.title}](node:${n.id})`,
            }));
            dropdownOpen = dropdownItems.length > 0;
        } catch {
            dropdownItems = [];
            dropdownOpen = false;
        } finally {
            loading = false;
        }
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
        const delay = trigger.query ? 250 : 0;
        debounceTimer = setTimeout(() => search(trigger), delay);
    }

    // ── Keyboard-Handler ─────────────────────────────────────────────────────
    function handleKeydown(e) {
        if (!dropdownOpen) return;
        if (e.key === "ArrowDown") {
            e.preventDefault();
            dropdownIndex = Math.min(dropdownIndex + 1, dropdownItems.length - 1);
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
        const newPos = (before + item.serialized + " ").length;
        requestAnimationFrame(() => {
            if (textarea) {
                textarea.setSelectionRange(newPos, newPos);
                textarea.focus();
            }
        });
    }

    // ── Preview ───────────────────────────────────────────────────────────────
    const previewParts = $derived(parseMaterial(value));
    const hasTokens = $derived(previewParts.some((p) => p.kind !== "text"));
</script>

<div class="space-y-1">
    <div class="relative">
        <textarea
            bind:this={textarea}
            bind:value
            oninput={handleInput}
            onkeydown={handleKeydown}
            onblur={() => { setTimeout(() => { dropdownOpen = false }, 200) }}
            rows="3"
            placeholder="Material: @ für Knoten, URLs werden verlinkt, freier Text möglich"
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
                {#if loading}
                    <div class="p-3 text-sm text-light-tx-2 dark:text-dark-tx-2">Suche…</div>
                {:else}
                    {#each dropdownItems as item, i}
                        <button
                            onmousedown={(e) => { e.preventDefault(); confirmSelection(item) }}
                            class="w-full px-3 py-2 text-left text-sm flex items-start gap-2 transition-colors
                                   {i === dropdownIndex
                                ? 'bg-light-ui-2 dark:bg-dark-ui-2'
                                : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                        >
                            <span class="shrink-0 mt-0.5 text-xs px-1.5 py-0.5 rounded-full font-medium
                                         bg-light-ui-3/50 dark:bg-dark-ui-3/50 text-light-tx dark:text-dark-tx">
                                🔗
                            </span>
                            <div class="min-w-0 flex-1">
                                <div class="font-medium text-light-tx dark:text-dark-tx truncate">{item.label}</div>
                                {#if item.sublabel}
                                    <div class="text-xs text-light-tx-2 dark:text-dark-tx-2 truncate">{item.sublabel}</div>
                                {/if}
                            </div>
                        </button>
                    {/each}
                {/if}
            </div>
        {/if}
    </div>

    <!-- Live-Vorschau (nur wenn Tokens oder URLs vorhanden) -->
    {#if hasTokens}
        <div class="flex flex-wrap gap-1 items-center text-xs text-light-tx-2 dark:text-dark-tx-2">
            <span class="shrink-0">Vorschau:</span>
            {#each previewParts as part}
                {#if part.kind === "node"}
                    <HinweisChip typ="material" text={part.label} href="/knowledge/{part.node_id}" />
                {:else if part.label.trim()}
                    {#each linkifyText(part.label) as sub}
                        {#if sub.kind === "url"}
                            <a href={sub.href} target="_blank" rel="noopener noreferrer"
                               class="text-light-bl dark:text-dark-bl underline break-all">{sub.label}</a>
                        {:else if sub.label.trim()}
                            <span class="text-light-tx dark:text-dark-tx">{sub.label}</span>
                        {/if}
                    {/each}
                {/if}
            {/each}
        </div>
    {/if}
</div>
