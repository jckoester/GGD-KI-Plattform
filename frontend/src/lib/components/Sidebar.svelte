<script>
    import { branding } from "$lib/branding.js";
    import { slide } from "svelte/transition";
    import SidebarBottom from "./SidebarBottom.svelte";

    const initials = (name) => name.slice(0, 2).toUpperCase();
</script>

<aside
    class="w-64 h-full bg-white border-r border-gray-200 flex flex-col"
    transition:slide={{ duration: 250, axis: "x" }}
>
    <!-- Sidebar-Header mit Branding -->
    <div
        class="h-14 border-b border-gray-200 flex items-center px-4 flex-shrink-0"
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
        <span class="ml-2 font-semibold text-gray-800">{branding.name}</span>
    </div>

    <!-- Sidebar-Inhalt (Platzhalter für Schritt 3c) -->
    <div class="flex-1 overflow-y-auto p-4">
        <p class="text-sm text-gray-400">Navigation folgt in Schritt 3c</p>
    </div>

    <!-- Unterer Bereich -->
    <SidebarBottom />
</aside>
