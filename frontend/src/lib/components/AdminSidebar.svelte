<script>
    import { branding } from "$lib/branding.js";
    import { slide } from "svelte/transition";
    import {
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
        ScanSearch,
        ThumbsUp,
        ShieldCheck,
        PiggyBank,
        Bot,
        Check,
        CalendarDays,
        Inbox,
        BookOpen,
        ScrollText,
    } from "lucide-svelte";
    import SidebarBottom from "./SidebarBottom.svelte";
    import SidebarLink from "./SidebarLink.svelte";
    import SidebarBereich from "./SidebarBereich.svelte";
    import { hasAnyRole } from "$lib/stores/user.js";
    import { pendingCount, refreshPendingCount } from "$lib/stores/pendingAssistants.js";
    import { onMount } from "svelte";
    import {
        calendarConfigured,
        refreshCalendarStatus,
    } from "$lib/stores/calendarStatus.js";
    import {
        offeneFeedbackCount,
        refreshFeedbackAlerts,
    } from "$lib/stores/feedbackAlerts.js";

    // Der Ferienkalender erscheint nur, wenn eine Stundenplanquelle eingerichtet ist —
    // eine Schule ohne WebUntis soll den Menüpunkt gar nicht sehen (Plan §0).
    onMount(refreshCalendarStatus);
    // Einmal beim Laden; danach zieht die Sichtungsseite den Zähler nach jedem
    // Statuswechsel selbst nach. Eine Abfrageschleife wäre für Rückmeldungen,
    // die einzeln über den Tag eintreffen, verschwendete Last.
    onMount(refreshFeedbackAlerts);
    onMount(refreshPendingCount);

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

    const einstellungenOffen = $derived(
        ["settings", "settings-texts", "settings-guardrail"].includes(openSection),
    );

    /** Genau diese Seite oder eine darunter. */
    function istPfad(pfad) {
        return $page.url.pathname === pfad || $page.url.pathname.startsWith(`${pfad}/`);
    }

    const TEXTE = [
        { tab: "impressum", label: "Impressum", icon: Section },
        { tab: "datenschutz", label: "Datenschutz", icon: ShieldBan },
        { tab: "hilfe", label: "Hilfe", icon: FileQuestionMark },
        { tab: "regeln", label: "Regeln", icon: TriangleAlert },
    ];

    function toggleOpenSection(section) {
        if (openSection === section) {
            openSection = "";
        } else {
            openSection = section;
        }
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
                       text-on-fill text-xs font-bold select-none"
            >
                {initials(branding.name)}
            </div>
        {/if}
        <span class="ml-2 font-semibold {textClass}">{branding.name}</span>
    </div>

    <!-- Sidebar-Inhalt. Seit 0.48 echte Links wie in der App-Seitenleiste
         (`SidebarLink`, `SidebarBereich`, Päckchen N). -->
    <div class="flex-1 overflow-y-auto p-2">
        <div class="mt-2">
            <SidebarLink href="/welcome" haupt>
                <ChevronLeft class="w-4 h-4" />
                Zurück zur App
            </SidebarLink>
        </div>

        <!-- Assistenten: seit 0.27 unter Einstellungen (Plan F8 a) — Verwalten und Freigabe
             stehen nebeneinander, die Freigabe mit der Zahl offener Einreichungen. -->

        <!-- Einstellungen -->
        {#if $canSeeSettings}
        <div class="mt-2 border-t border-light-ui-3 dark:border-dark-ui-3 pt-3">
            <SidebarBereich
                href="/settings"
                label="Einstellungen"
                offen={einstellungenOffen}
                ontoggle={() => (openSection = einstellungenOffen ? "" : "settings")}
                onnavigate={() => { if (!einstellungenOffen) openSection = "settings"; }}
                aktiv={$page.url.pathname === "/settings"}
            >
                <Settings class="w-4 h-4 text-light-re dark:text-dark-re" />
                Einstellungen
            </SidebarBereich>
        </div>
        {#if einstellungenOffen}
            <div class="mt-1 space-y-1 pl-5">
                <SidebarLink href="/settings/models" aktiv={istPfad("/settings/models")}>
                    <CloudCog class="w-4 h-4" />
                    Modell-Freischaltung
                </SidebarLink>
                <SidebarLink href="/assistants/manage" aktiv={istPfad("/assistants/manage")}>
                    <Bot class="w-4 h-4" />
                    Assistenten verwalten
                </SidebarLink>
                <SidebarLink href="/settings/assistants" aktiv={istPfad("/settings/assistants")}>
                    <Check class="w-4 h-4" />
                    Assistenten-Freigabe
                    {#if $pendingCount > 0}
                        <span class="ml-auto text-xs font-semibold px-1.5 py-0.5 rounded-full
                                     bg-light-ye/30 dark:bg-dark-ye/30 text-light-ye dark:text-dark-ye">
                            {$pendingCount}
                        </span>
                    {/if}
                </SidebarLink>
                <SidebarLink href="/settings/guardrail" aktiv={istPfad("/settings/guardrail")}>
                    <ShieldCheck class="w-4 h-4" />
                    Guardrails
                </SidebarLink>
                <SidebarLink href="/settings/audit" aktiv={istPfad("/settings/audit")}>
                    <ScrollText class="w-4 h-4" />
                    Audit-Log
                </SidebarLink>
                <SidebarLink href="/settings/fachbegriffe" aktiv={istPfad("/settings/fachbegriffe")}>
                    <BookOpen class="w-4 h-4" />
                    Fachbegriffe
                </SidebarLink>
                {#if $calendarConfigured}
                <SidebarLink href="/settings/holidays" aktiv={istPfad("/settings/holidays")}>
                    <CalendarDays class="w-4 h-4" />
                    Ferienkalender
                </SidebarLink>
                {/if}
                <SidebarBereich
                    href="/settings/texts?tab=impressum"
                    label="Texte"
                    offen={openSection === "settings-texts"}
                    ontoggle={() => (openSection = openSection === "settings-texts" ? "settings" : "settings-texts")}
                    onnavigate={() => (openSection = "settings-texts")}
                >
                    <FileText class="w-4 h-4" />
                    <span class="font-normal">Texte</span>
                </SidebarBereich>
                {#if openSection === "settings-texts"}
                    <div class="mt-1 space-y-1 pl-4">
                        {#each TEXTE as t (t.tab)}
                            <SidebarLink href={`/settings/texts?tab=${t.tab}`}
                                aktiv={istPfad("/settings/texts") && $page.url.searchParams.get("tab") === t.tab}>
                                <t.icon class="w-4 h-4" />
                                {t.label}
                            </SidebarLink>
                        {/each}
                    </div>
                {/if}
            </div>
        {/if}
        {/if}

        <!-- Krisen-Meldungen (operativer Bereich, nicht unter Einstellungen) -->
        {#if $canSeeSettings}
        <div class="mt-2 border-t border-light-ui-3 dark:border-dark-ui-3 pt-3">
            <SidebarLink href="/flags" haupt aktiv={istPfad("/flags")}>
                <TriangleAlert class="w-4 h-4 text-light-re dark:text-dark-re" />
                Krisen-Meldungen
            </SidebarLink>
        </div>
        {/if}

        <!-- Rückmeldungen (operativer Bereich wie die Krisen-Meldungen) -->
        {#if $canSeeSettings}
        <div class="mt-2 border-t border-light-ui-3 dark:border-dark-ui-3 pt-3">
            <SidebarLink href="/feedback/manage" haupt aktiv={istPfad("/feedback/manage")}>
                <Inbox class="w-4 h-4 text-light-bl dark:text-dark-bl" />
                Rückmeldungen
                {#if $offeneFeedbackCount > 0}
                    <span class="ml-auto text-xs font-semibold px-1.5 py-0.5 rounded-full
                                 bg-light-bl/20 dark:bg-dark-bl/20 text-light-bl dark:text-dark-bl">
                        {$offeneFeedbackCount}
                    </span>
                {/if}
            </SidebarLink>
        </div>
        {/if}

        <!-- Statistiken -->
        {#if $canSeeStatistics}
        <div class="mt-2 border-t border-light-ui-3 dark:border-dark-ui-3 pt-3">
            <SidebarBereich
                href="/statistics"
                label="Statistiken"
                offen={openSection === "statistics"}
                ontoggle={() => toggleOpenSection("statistics")}
                onnavigate={() => (openSection = "statistics")}
                aktiv={$page.url.pathname === "/statistics"}
            >
                <ChartNoAxesCombined class="w-4 h-4 text-light-gr dark:text-dark-gr" />
                Statistiken
            </SidebarBereich>
        </div>
        {#if openSection === "statistics"}
            <div class="mt-1 space-y-1 pl-5">
                <SidebarLink href="/statistics/prompts" aktiv={istPfad("/statistics/prompts")}>
                    <ChartColumn class="w-4 h-4" />
                    Prompts
                </SidebarLink>
                <SidebarLink href="/statistics/costs" aktiv={istPfad("/statistics/costs")}>
                    <ReceiptEuro class="w-4 h-4" />
                    Kosten
                </SidebarLink>
                <SidebarLink href="/statistics/vorab" aktiv={istPfad("/statistics/vorab")}>
                    <ScanSearch class="w-4 h-4" />
                    Vorab-Suche
                </SidebarLink>
                <SidebarLink href="/statistics/ratings" aktiv={istPfad("/statistics/ratings")}>
                    <ThumbsUp class="w-4 h-4" />
                    Antwortbewertung
                </SidebarLink>
            </div>
        {/if}
        {/if}
        <!--Budget-->
        {#if $canSeeBudget}
        <div class="mt-2 border-t border-light-ui-3 dark:border-dark-ui-3 pt-3">
            <SidebarLink href="/budget" haupt aktiv={istPfad("/budget")}>
                <PiggyBank class="w-4 h-4 text-light-ma dark:text-dark-ma" />
                Budget
            </SidebarLink>
        </div>
        {/if}
    </div>

    <!-- Unterer Bereich -->
    <SidebarBottom />
</aside>
