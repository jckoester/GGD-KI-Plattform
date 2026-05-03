<script>
    import { page } from '$app/stores';
    import { helpNav } from '$lib/help-nav.js';
    import { ChevronRight, Menu } from 'lucide-svelte';
    import { goto } from '$app/navigation';

    let { children } = $props();

    let tocOpen = $state(false);

    function toggleToc() {
        tocOpen = !tocOpen;
    }
</script>

<div class="flex flex-col md:flex-row h-full">
    <!-- TOC Sidebar - Desktop -->
    <aside class="hidden md:flex md:flex-col w-52 flex-shrink-0 border-r border-light-ui-3 dark:border-dark-ui-3 bg-light-bg-2 dark:bg-dark-bg-2 overflow-y-auto">
        <nav class="p-4">
            <h2 class="text-sm font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-3">
                Inhaltsverzeichnis
            </h2>
            <ul class="space-y-1">
                {#each helpNav as item}
                    <li>
                        <a
                            href={item.path}
                            class="flex items-center gap-2 px-3 py-2 rounded text-sm transition-colors
                                {$page.url.pathname === item.path
                                    ? 'bg-primary text-white dark:bg-primary-dark'
                                    : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'
                                }"
                        >
                            {#if $page.url.pathname === item.path}
                                <ChevronRight class="w-4 h-4" />
                            {/if}
                            <span>{item.label}</span>
                        </a>
                    </li>
                {/each}
            </ul>
        </nav>
    </aside>

    <!-- Mobile TOC - Aufklappbar -->
    <div class="md:hidden">
        <button
            onclick={toggleToc}
            class="w-full flex items-center justify-between p-4 border-b border-light-ui-3 dark:border-dark-ui-3 text-left"
        >
            <span class="font-medium text-light-tx dark:text-dark-tx">
                Inhaltsverzeichnis
            </span>
            <Menu class="w-5 h-5 text-light-tx-2 dark:text-dark-tx-2" />
        </button>
        {#if tocOpen}
            <nav class="p-4 border-b border-light-ui-3 dark:border-dark-ui-3">
                <ul class="space-y-1">
                    {#each helpNav as item}
                        <li>
                            <a
                                href={item.path}
                                onclick={(e) => {
                                    e.preventDefault();
                                    goto(item.path);
                                    tocOpen = false;
                                }}
                                class="flex items-center gap-2 px-3 py-2 rounded text-sm transition-colors
                                    {$page.url.pathname === item.path
                                        ? 'bg-primary text-white dark:bg-primary-dark'
                                        : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'
                                    }"
                            >
                                {#if $page.url.pathname === item.path}
                                    <ChevronRight class="w-4 h-4" />
                                {/if}
                                <span>{item.label}</span>
                            </a>
                        </li>
                    {/each}
                </ul>
            </nav>
        {/if}
    </div>

    <!-- Main Content -->
    <main class="flex-1 overflow-y-auto">
        {@render children()}
    </main>
</div>
