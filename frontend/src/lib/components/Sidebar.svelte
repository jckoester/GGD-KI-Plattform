<script>
    import { branding } from "$lib/branding.js";
    import { slide } from "svelte/transition";
    import SidebarBottom from "./SidebarBottom.svelte";

    const initials = (name) => name.slice(0, 2).toUpperCase();

    let {
        bgHeaderClass = "bg-light-bg dark:bg-dark-bg-2",
        textClass = "text-light-tx dark:text-dark-tx",
        borderClass = "border-light-ui-2 dark:border-dark-ui-2",
    } = $props();
</script>

<aside
    class="w-64 h-full bg-light-bg dark:bg-dark-bg-2 border-r border-light-ui-3 dark:border-dark-ui-3 flex flex-col"
    transition:slide={{ duration: 250, axis: "x" }}
>
    <!-- Sidebar-Header mit Branding -->
    <div
        class="h-14 border-b {bgHeaderClass} {borderClass} flex items-center px-4 flex-shrink-0"
    >
        {#if branding.logo_url}
            <img src={branding.logo_url} alt="Logo" class="h-8 w-auto" />
        {:else}
            <div
                class="w-8 h-8 rounded-full bg-primary flex items-center justify-center
                       text-white text-xs font-bold select-none"
            >
                {initials(branding.name)}
            </div>
        {/if}
        <span class="ml-2 font-semibold {textClass}">{branding.name}</span>
    </div>

    <!-- Sidebar-Inhalt (Platzhalter für Schritt 3c) -->
    <div class="flex-1 overflow-y-auto p-4">
        <p class="text-sm text-light-tx-3 dark:text-dark-tx-3">
            Navigation folgt in Schritt 3c
        </p>
    </div>

    <!-- Unterer Bereich -->
    <SidebarBottom />
</aside>
