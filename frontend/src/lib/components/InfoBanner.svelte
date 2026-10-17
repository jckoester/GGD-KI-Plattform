<script>
    import { Info, X } from "lucide-svelte";
    /**
     * Info-Hinweis (blau). Optional seit 0.17 (Hinweise auf Neuerungen): ein Titel, ein
     * Link und ein Schließen-Knopf — ohne sie sieht der Hinweis aus wie bisher.
     */
    let { message, title = null, href = null, linkLabel = "Mehr erfahren", onclose = null } = $props();
</script>

<div
    class="flex items-start gap-3 p-4 rounded border
        bg-light-bl-bg dark:bg-dark-bl-bg
        border-light-bl dark:border-dark-bl
        text-light-tx dark:text-dark-tx mb-4"
    class:items-center={!title && !href && !onclose}
>
    <Info class="w-5 h-5 shrink-0 text-light-bl dark:text-dark-bl" />
    <div class="text-sm flex-1">
        {#if title}<p class="font-semibold mb-1">{title}</p>{/if}
        <span>{message}</span>
        {#if href}
            <a {href} class="ml-1 text-light-bl dark:text-dark-bl hover:underline">{linkLabel}</a>
        {/if}
    </div>
    {#if onclose}
        <button
            onclick={onclose}
            class="shrink-0 p-1 rounded opacity-70 hover:opacity-100"
            aria-label="Hinweis schließen"
            title="Schließen"
        >
            <X class="w-4 h-4" />
        </button>
    {/if}
</div>
