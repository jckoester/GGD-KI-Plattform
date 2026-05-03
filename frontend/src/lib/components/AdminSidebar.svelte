<script>
    import { branding } from "$lib/branding.js";
    import { slide } from "svelte/transition";
    import { goto } from "$app/navigation";
    import {
        ChevronDown,
        ChevronRight,
        ChevronLeft,
        Settings,
        CloudCog,
        FileText,
        Section,
        ShieldBan,
        FileQuestionMark,
        TriangleAlert,
        ChartNoAxesCombined,
        ChartColumn,
        ReceiptEuro,
        ShieldCheck,
        BarChart2,
        PiggyBank,
        Bot,
    } from "lucide-svelte";
    import SidebarBottom from "./SidebarBottom.svelte";
    import { user, hasAnyRole } from "$lib/stores/user.js";

    const canSeeSettings   = hasAnyRole(['admin']);
    const canSeeStatistics = hasAnyRole(['statistics', 'admin']);
    const canSeeBudget     = hasAnyRole(['budget', 'admin']);
    import { page } from "$app/stores";

    const initials = (name) => name.slice(0, 2).toUpperCase();

    let {
        bgHeaderClass = "bg-light-bg dark:bg-dark-bg-2",
        textClass = "text-light-tx dark:text-dark-tx",
        borderClass = "border-light-ui-2 dark:border-dark-ui-2",
    } = $props();

    // Aktuelle Sektion aus URL-Parameter

    let openSection = $derived($page.data.sidebarSection ?? "");

    $effect(() => {
        openSection = $page.data.sidebarSection ?? "";
    });

    function toggleOpenSection(section) {
        if (openSection === section) {
            openSection = "";
        } else {
            openSection = section;
        }
    }

    function setOpenSection(section) {
        openSection = section;
    }
</script>

<aside
    class="w-72 h-full bg-light-bg dark:bg-dark-bg-2 border-r border-light-ui-3 dark:border-dark-ui-3 flex flex-col"
    transition:slide={{ duration: 250, axis: "x" }}
>
    <!-- Sidebar-Header mit Branding -->
    <div
        class="h-14 border-b {bgHeaderClass} {borderClass} flex items-center px-4 flex-shrink-0"
    >
        {#if branding.logo_url_light || branding.logo_url_dark}
            {#if branding.logo_url_light}
                <img src={branding.logo_url_light} alt="Logo" class="h-8 w-auto dark:hidden" />
            {/if}
            {#if branding.logo_url_dark}
                <img src={branding.logo_url_dark} alt="Logo" class="h-8 w-auto hidden dark:block" />
            {/if}
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
    <div class="flex-1 overflow-y-auto p-2">
        <!-- zurück zur App -->
        <div class="mt-2">
            <div
                class="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors rounded-lg"
            >
                <button
                    onclick={() => {
                        goto("/welcome");
                    }}
                >
                    <span class="flex items-center gap-2">
                        <ChevronLeft class="w-4 h-4" />
                        zurück zur App
                    </span>
                </button>
            </div>
        </div>

        <!-- Assistenten -->
        {#if $canSeeSettings}
        <div class="mt-2 border-t border-light-ui-3 dark:border-dark-ui-3 pt-3">
            <div
                class="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors rounded-lg"
            >
                <button
                    onclick={() => {
                        toggleOpenSection('assistants');
                        goto('/assistants');
                    }}
                >
                    <span class="flex items-center gap-2">
                        <Bot class="w-4 h-4 text-light-bl dark:text-dark-bl" />
                        Assistenten
                    </span>
                </button>
                <button
                    onclick={() => toggleOpenSection('assistants')}
                >
                    <span class="flex items-center gap-2">
                        {#if openSection === 'assistants'}
                            <ChevronDown class="w-4 h-4" />
                        {:else}
                            <ChevronRight class="w-4 h-4" />
                        {/if}
                    </span>
                </button>
            </div>
        </div>
        {#if openSection === 'assistants'}
            <div class="mt-1 space-y-1 pl-2">
                <button
                    onclick={() => goto('/assistants/manage')}
                    class="w-full text-left px-3 py-2 text-sm rounded-lg text-light-tx dark:text-dark-tx
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                >
                    <span class="flex items-center gap-2">
                        <Settings class="w-4 h-4" />
                        Verwalten
                    </span>
                </button>
            </div>
        {/if}
        {/if}

        <!-- Einstellungen -->
        {#if $canSeeSettings}
        <div class="mt-2 border-t border-light-ui-3 dark:border-dark-ui-3 pt-3">
            <div
                class="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors rounded-lg"
            >
                <button
                    onclick={() => {
                        toggleOpenSection("settings");
                        goto("/settings");
                    }}
                >
                    <span class="flex items-center gap-2">
                        <Settings
                            class="w-4 h-4 text-light-re dark:text-dark-re"
                        />
                        Einstellungen
                    </span>
                </button>
                <button
                    onclick={() => {
                        if (
                            openSection === "settings-texts" ||
                            openSection === "settings"
                        ) {
                            openSection = "";
                        } else {
                            openSection = "settings";
                        }
                    }}
                >
                    <span class="flex items-center gap-2">
                        {#if openSection === "settings" || openSection === "settings-texts"}
                            <ChevronDown class="w-4 h-4" />
                        {:else}
                            <ChevronRight class="w-4 h-4" />
                        {/if}
                    </span>
                </button>
            </div>
        </div>
        {#if openSection === "settings" || openSection === "settings-texts"}
            <div class="mt-1 space-y-1 pl-2">
                <button
                    onclick={() => goto(`/settings/models`)}
                    class="w-full text-left px-3 py-2 text-sm rounded-lg text-light-tx dark:text-dark-tx
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                >
                    <div class="flex justify-between items-center">
                        <span class="flex items-center gap-2">
                            <CloudCog class="w-4 h4" />
                            Modell-Freischaltung
                        </span>
                    </div>
                </button>
                <button
                    onclick={() => goto('/settings/assistants')}
                    class="w-full text-left px-3 py-2 text-sm rounded-lg text-light-tx dark:text-dark-tx
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                >
                    <span class="flex items-center gap-2">
                        <Bot class="w-4 h-4" />
                        Assistenten-Freigabe
                    </span>
                </button>
                <div
                    class="w-full flex items-center justify-between px-3 py-2 text-sm rounded-lg text-light-tx dark:text-dark-tx
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                >
                    <button
                        onclick={() => {
                            goto(`/settings/texts?tab=impressum`);
                            openSection = "settings-texts";
                        }}
                    >
                        <div class="flex justify-between items-center">
                            <span class="flex items-center gap-2">
                                <FileText class="w-4 h4" />
                                Texte
                            </span>
                        </div>
                    </button>
                    <button
                        onclick={() => {
                            if (openSection === "settings-texts")
                                openSection = "settings";
                            else openSection = "settings-texts";
                        }}
                    >
                        <span class="flex items-center gap-2">
                            {#if openSection === "settings-texts"}
                                <ChevronDown class="w-4 h-4" />
                            {:else}
                                <ChevronRight class="w-4 h-4" />
                            {/if}
                        </span>
                    </button>
                </div>
                {#if openSection === "settings-texts"}
                    <div class="mt-1 space-y-1 pl-4">
                        <button
                            onclick={() =>
                                goto(`/settings/texts?tab=impressum`)}
                            class="w-full text-left px-3 py-1 text-sm rounded-lg
                                   {openSection === 'settings-texts' &&
                            $page.url.searchParams.get('tab') === 'impressum'
                                ? 'bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx'
                                : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'} transition-colors"
                        >
                            <div class="flex justify-between items-center">
                                <span class="flex items-center gap-2">
                                    <Section class="w-4 h4" />
                                    Impressum
                                </span>
                            </div>
                        </button>
                        <button
                            onclick={() =>
                                goto(`/settings/texts?tab=datenschutz`)}
                            class="w-full text-left px-3 py-1 text-sm rounded-lg
                                   {openSection === 'settings-texts' &&
                            $page.url.searchParams.get('tab') === 'datenschutz'
                                ? 'bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx'
                                : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'} transition-colors"
                        >
                            <div class="flex justify-between items-center">
                                <span class="flex items-center gap-2">
                                    <ShieldBan class="w-4 h4" />
                                    Datenschutz
                                </span>
                            </div>
                        </button>
                        <button
                            onclick={() => goto(`/settings/texts?tab=hilfe`)}
                            class="w-full text-left px-3 py-1 text-sm rounded-lg
                                   {openSection === 'settings-texts' &&
                            $page.url.searchParams.get('tab') === 'hilfe'
                                ? 'bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx'
                                : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'} transition-colors"
                        >
                            <div class="flex justify-between items-center">
                                <span class="flex items-center gap-2">
                                    <FileQuestionMark class="w-4 h4" />
                                    Hilfe
                                </span>
                            </div>
                        </button>
                        <button
                            onclick={() => goto(`/settings/texts?tab=regeln`)}
                            class="w-full text-left px-3 py-1 text-sm rounded-lg
                                   {openSection === 'settings-texts' &&
                            $page.url.searchParams.get('tab') === 'regeln'
                                ? 'bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx'
                                : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'} transition-colors"
                        >
                            <div class="flex justify-between items-center">
                                <span class="flex items-center gap-2">
                                    <TriangleAlert class="w-4 h4" />
                                    Regeln
                                </span>
                            </div>
                        </button>
                    </div>
                {/if}
            </div>
        {/if}
        {/if}

        <!-- Statistiken -->
        {#if $canSeeStatistics}
        <div class="mt-2 border-t border-light-ui-3 dark:border-dark-ui-3 pt-3">
            <div
                class="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors rounded-lg"
            >
                <button
                    onclick={() => {
                        toggleOpenSection("statistics");
                        goto("/statistics");
                    }}
                >
                    <span class="flex items-center gap-2">
                        <ChartNoAxesCombined
                            class="w-4 h-4 text-light-gr dark:text-dark-gr"
                        />
                        Statistiken
                    </span>
                </button>
                <button
                    onclick={() => {
                        toggleOpenSection("statistics");
                    }}
                >
                    <span class="flex items-center gap-2">
                        {#if openSection === "statistics"}
                            <ChevronDown class="w-4 h-4" />
                        {:else}
                            <ChevronRight class="w-4 h-4" />
                        {/if}
                    </span>
                </button>
            </div>
        </div>
        {#if openSection === "statistics"}
            <div class="mt-1 space-y-1 pl-2">
                <button
                    onclick={() => goto(`/statistics/prompts`)}
                    class="w-full text-left px-3 py-2 text-sm rounded-lg text-light-tx dark:text-dark-tx
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                >
                    <div class="flex justify-between items-center">
                        <span class="flex items-center gap-2">
                            <ChartColumn class="w-4 h4" />
                            Prompts
                        </span>
                    </div>
                </button>
            </div>
            <div class="mt-1 space-y-1 pl-2">
                <button
                    onclick={() => goto(`/statistics/costs`)}
                    class="w-full text-left px-3 py-2 text-sm rounded-lg text-light-tx dark:text-dark-tx
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                >
                    <div class="flex justify-between items-center">
                        <span class="flex items-center gap-2">
                            <ReceiptEuro class="w-4 h4" />
                            Costs
                        </span>
                    </div>
                </button>
            </div>
        {/if}
        {/if}
        <!--Budget-->
        {#if $canSeeBudget}
        <div class="mt-2 border-t border-light-ui-3 dark:border-dark-ui-3 pt-3">
            <div
                class="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors rounded-lg"
            >
                <button
                    onclick={() => {
                        toggleOpenSection("budget");
                        goto("/budget");
                    }}
                >
                    <span class="flex items-center gap-2">
                        <PiggyBank
                            class="w-4 h-4 text-light-ma dark:text-dark-ma"
                        />
                        Budget
                    </span>
                </button>
                <!--<button
                    onclick={() => {
                        toggleOpenSection("budget");
                    }}
                >
                    <span class="flex items-center gap-2">
                        {#if openSection === "budget"}
                            <ChevronDown class="w-4 h-4" />
                        {:else}
                            <ChevronRight class="w-4 h-4" />
                        {/if}
                    </span>
                </button>-->
            </div>
        </div>
        {/if}
    </div>

    <!-- Unterer Bereich -->
    <SidebarBottom />
</aside>
