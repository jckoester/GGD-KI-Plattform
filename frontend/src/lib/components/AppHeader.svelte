<script>
    import { PanelLeftClose, PanelLeftOpen, LogOut } from "lucide-svelte";
    import { page } from "$app/stores";
    import { pageTitle, activeConversationId } from "$lib/stores/pageTitle.js";
    import { logout } from "$lib/api.js";
    import { goto } from "$app/navigation";
    import ConversationMenu from "$lib/components/ConversationMenu.svelte";

    // Props
    let {
        sidebarOpen,
        onToggle,
        bgClass = "bg-light-bg-2 dark:bg-dark-bg-2",
        textClass = "text-light-tx dark:text-dark-tx",
        borderClass = "border-light-ui-2 dark:border-dark-ui-2",
        hoverClass = "hover:bg-light-ui-3 dark:hover:bg-dark-ui-3",
    } = $props();

    // Hintergrundfarbe
    //let bgClass = $page.data.headerColor ?? "bg-light-bg-2 dark:bg-dark-bg-2";

    // Abgeleiteter Titel
    let title = $derived($pageTitle || ($page.data.title ?? ""));

    async function handleLogout() {
        await logout();
        goto("/");
    }
</script>

<header
    class="h-14 {bgClass} border-b {borderClass} flex-shrink-0
           flex items-center justify-between px-1 pr-3"
>
    <div class="flex items-center gap-4">
        <!-- Toggle-Button -->
        <button
            onclick={onToggle}
            aria-label="Menü {sidebarOpen ? 'schließen' : 'öffnen'}"
            class="p-2 rounded-lg hover:bg-light-ui-2 dark:hover:bg-dark-ui {textClass} transition-colors md:p-1"
        >
            {#if sidebarOpen}
                <PanelLeftClose size={24} />
            {:else}
                <PanelLeftOpen size={24} />
            {/if}
        </button>

        <!-- Seitentitel -->
        <h1 class="text-lg font-semibold {textClass}">
            {title}
        </h1>
    </div>

    <!-- Rechte Seite: Abmelden-Button oder Konversationsmenü -->
    {#if $activeConversationId}
        <ConversationMenu
            conversationId={$activeConversationId}
            title={$pageTitle}
            syncPageTitle={true}
            buttonClasses=" hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
        />
    {:else}
        <button
            onclick={handleLogout}
            class="text-sm {textClass} hover:text-light-tx dark:hover:text-dark-tx
                   px-3 py-1.5 rounded-lg hover:bg-light-ui dark:hover:bg-dark-ui transition-colors"
        >
            <LogOut size={16} class="inline-block mr-1" />Abmelden
        </button>
    {/if}
</header>
