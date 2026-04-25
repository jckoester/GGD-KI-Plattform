<script>
    import { branding } from "$lib/branding.js";
    import { slide } from "svelte/transition";
    import { goto } from "$app/navigation";
    import {
        Plus,
        ChevronDown,
        ChevronRight,
        History,
        ShieldCheck,
        BarChart2,
        PiggyBank,
    } from "lucide-svelte";
    import SidebarBottom from "./SidebarBottom.svelte";
    import { user } from "$lib/stores/user.js";
    import { page } from "$app/stores";

    const initials = (name) => name.slice(0, 2).toUpperCase();

    let {
        bgHeaderClass = "bg-light-bg dark:bg-dark-bg-2",
        textClass = "text-light-tx dark:text-dark-tx",
        borderClass = "border-light-ui-2 dark:border-dark-ui-2",
    } = $props();
    // Limit aus User-Präferenzen
    const limit = $derived(
        $user?.preferences?.sidebar_recent_chats_limit ?? 10,
    );

    // Aktualisieren beim Ändern des Limits
    $effect(() => {
        refreshConversations(limit);
    });
</script>

<aside
    class="w-72 h-full bg-light-bg dark:bg-dark-bg-2 border-r border-light-ui-3 dark:border-dark-ui-3 flex flex-col"
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

    <!-- Sidebar-Inhalt -->
    <div class="flex-1 overflow-y-auto p-2"></div>

    <!-- Verwaltungslinks -->
    {#if $user?.roles.some( (r) => ["admin", "statistics", "budget"].includes(r), )}
        <div
            class="flex-shrink-0 border-t border-light-ui-3 dark:border-dark-ui-3 pt-3"
        >
            <p
                class="px-3 py-1 text-xs font-medium text-light-tx-3 dark:text-dark-tx-3 uppercase tracking-wide"
            >
                Verwaltung
            </p>
            {#if $user.roles.includes("admin")}
                <a
                    href="/admin"
                    class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm
                          text-light-tx dark:text-dark-tx
                          hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                          {$page.url.pathname === '/admin'
                        ? 'bg-light-ui-2 dark:bg-dark-ui-2'
                        : ''}"
                >
                    <ShieldCheck class="w-4 h-4" />
                    Administration
                </a>
            {/if}
            {#if $user.roles.some((r) => ["statistics", "admin"].includes(r))}
                <a
                    href="/statistik"
                    class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm
                          text-light-tx dark:text-dark-tx
                          hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                          {$page.url.pathname === '/statistik'
                        ? 'bg-light-ui-2 dark:bg-dark-ui-2'
                        : ''}"
                >
                    <BarChart2 class="w-4 h-4" />
                    Statistik
                </a>
            {/if}
            {#if $user.roles.some((r) => ["budget", "admin"].includes(r))}
                <a
                    href="/budget"
                    class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm
                          text-light-tx dark:text-dark-tx
                          hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                          {$page.url.pathname === '/budget'
                        ? 'bg-light-ui-2 dark:bg-dark-ui-2'
                        : ''}"
                >
                    <PiggyBank class="w-4 h-4" />
                    Budget
                </a>
            {/if}
        </div>
    {/if}

    <!-- Unterer Bereich -->
    <SidebarBottom />
</aside>
