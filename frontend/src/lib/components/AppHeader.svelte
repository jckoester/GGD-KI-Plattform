<script>
    import { PanelLeftClose, PanelLeftOpen, LogOut } from "lucide-svelte";
    import { page } from "$app/stores";
    import { logout } from "$lib/api.js";
    import { goto } from "$app/navigation";

    // Props
    let { sidebarOpen, onToggle } = $props();

    // Abgeleiteter Titel
    let title = $derived($page.data.title ?? "");

    async function handleLogout() {
        await logout();
        goto("/");
    }
</script>

<header
    class="h-14 bg-light-bg dark:bg-dark-bg-2 border-b border-light-ui-3 dark:border-dark-ui-3 flex-shrink-0
           flex items-center justify-between px-1"
>
    <div class="flex items-center gap-4">
        <!-- Toggle-Button -->
        <button
            onclick={onToggle}
            aria-label="Menü {sidebarOpen ? 'schließen' : 'öffnen'}"
            class="p-2 rounded-lg hover:bg-light-ui-2 dark:hover:bg-dark-ui dark:text-dark-tx-2 transition-colors md:p-1"
        >
            {#if sidebarOpen}
                <PanelLeftClose size={24} />
            {:else}
                <PanelLeftOpen size={24} />
            {/if}
        </button>

        <!-- Seitentitel -->
        <h1 class="text-lg font-semibold text-light-tx dark:text-dark-tx">
            {title}
        </h1>
    </div>

    <!-- Abmelden-Button -->
    <button
        onclick={handleLogout}
        class="text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx
               px-3 py-1.5 rounded-lg hover:bg-light-ui dark:hover:bg-dark-ui transition-colors"
    >
        <LogOut size={16} class="inline-block mr-1" />Abmelden
    </button>
</header>
