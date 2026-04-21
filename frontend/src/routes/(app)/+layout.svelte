<script>
    import { onMount, onDestroy } from "svelte";
    import { goto } from "$app/navigation";
    import { getMe, getPreferences } from "$lib/api.js";
    import { user } from "$lib/stores/user.js";
    import { themePref } from "$lib/stores/theme.js";
    import Sidebar from "$lib/components/Sidebar.svelte";
    import AppHeader from "$lib/components/AppHeader.svelte";

    let { children } = $props();

    let sidebarOpen = $state(false);
    let isDesktop = $state(false);

    onMount(async () => {
        try {
            const [me, prefs] = await Promise.all([getMe(), getPreferences()])
            user.set({
                ...me,
                display_name: sessionStorage.getItem('display_name') ?? me.pseudonym,
            });
            themePref.syncFromServer(prefs.theme ?? 'system')
        } catch {
            goto("/");
        }
        handleResize();
        window.addEventListener("resize", handleResize);
    });

    onDestroy(() => {
        window.removeEventListener("resize", handleResize);
    });

    function handleResize() {
        isDesktop = window.innerWidth >= 768;
        if (isDesktop) sidebarOpen = true;
        else sidebarOpen = false;
    }

    function toggleSidebar() {
        sidebarOpen = !sidebarOpen;
    }

    function closeSidebar() {
        sidebarOpen = false;
    }
</script>

<div class="flex h-screen overflow-hidden">
    <!-- Backdrop (nur Mobile) -->
    {#if sidebarOpen && !isDesktop}
        <div
            class="fixed inset-0 bg-black/50 z-40"
            onclick={closeSidebar}
            aria-hidden="true"
        ></div>
    {/if}

    <!-- Sidebar: auf Desktop normaler Flex-Block, auf Mobile Fixed-Overlay -->
    {#if sidebarOpen}
        <div
            class={!isDesktop ? "fixed inset-y-0 left-0 z-50" : "flex-shrink-0"}
        >
            <Sidebar />
        </div>
    {/if}

    <!-- Rechter Bereich: Header + Inhalt -->
    <div class="flex flex-col flex-1 min-w-0 overflow-hidden">
        <AppHeader {sidebarOpen} onToggle={toggleSidebar} />
        <main class="flex-1 overflow-hidden bg-light-bg-2 dark:bg-dark-bg-2">
            {@render children()}
        </main>
    </div>
</div>
