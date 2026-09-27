<script>
    import { onMount, onDestroy } from "svelte";
    import { afterNavigate, goto } from "$app/navigation";
    import { getMe, getPreferences, getBudget } from "$lib/api.js";
    import { user } from "$lib/stores/user.js";
    import { themePref } from "$lib/stores/theme.js";
    import { budget } from "$lib/stores/budget.js";
    import { refreshSubjects } from "$lib/stores/subjects.js";
    import { refreshMyGroups } from "$lib/stores/myGroups.js";
    import { refreshAssistants } from "$lib/stores/assistants.js";
    import { refreshConversationCounts } from "$lib/stores/conversationCounts.js";
    import { refreshGroupsConfig } from "$lib/stores/groupsConfig.js";
    import { refreshUiLevels } from '$lib/stores/uiLevel.js';
    import { refreshCrisisAlerts } from "$lib/stores/crisisAlerts.js";
    import Sidebar from "$lib/components/Sidebar.svelte";
    import FeedbackDialog from "$lib/components/FeedbackDialog.svelte";
    import { feedbackDialog, schliesseFeedback } from "$lib/stores/feedbackDialog.js";
    import AppHeader from "$lib/components/AppHeader.svelte";

    let { children } = $props();

    let sidebarOpen = $state(false);
    let isDesktop = $state(false);

    onMount(async () => {
        try {
            const [me, prefs, budgetData] = await Promise.all([
                getMe(),
                getPreferences(),
                getBudget(),
            ]);
            user.set({
                ...me,
                display_name:
                    me.display_name ?? sessionStorage.getItem("display_name") ?? me.pseudonym,
                preferences: prefs,
            });
            budget.set(budgetData);
            themePref.syncFromServer(prefs.theme ?? "system");
            refreshSubjects(); // fire-and-forget; Fehler werden intern ignoriert
            refreshMyGroups(); // fire-and-forget
            refreshAssistants(); // NEU — für Sichtbarkeitsregel
            refreshConversationCounts(); // NEU — für Chat-Anzahl in Sidebar
            refreshGroupsConfig(); // NEU — für allow_manual_teaching_groups Flag
            refreshUiLevels();     // Zuschnitt der Darstellungsstufen
            refreshCrisisAlerts(); // Hinweis auf offene Krisen-Fälle (admin/review)
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

    // Auf kleinen Bildschirmen liegt die Seitenleiste als Overlay **über** der Seite.
    // Ohne diese Zeile blieb sie nach dem Antippen eines Eintrags liegen: Die Seite
    // wechselte dahinter, sichtbar war weiter das Menü, und es brauchte einen zweiten
    // Tipp, um überhaupt etwas zu sehen (Befund aus dem Telefontest, 18.09.2026).
    //
    // Die Abfrage auf `isDesktop` ist nicht kosmetisch: Am Schreibtisch ist die
    // Seitenleiste ein fester Teil des Layouts, kein Overlay — dort klappte sie sonst
    // bei jedem Klick zu.
    afterNavigate(() => {
        if (!isDesktop) sidebarOpen = false;
    });

    function toggleSidebar() {
        sidebarOpen = !sidebarOpen;
    }

    function closeSidebar() {
        sidebarOpen = false;
    }
</script>

<!-- h-dvh, nicht h-screen: `100vh` ist auf mobilen Browsern die Höhe OHNE die
     Adressleiste. Zusammen mit `overflow-hidden` schob das den unteren Rand des
     Layouts - im Chat also das Eingabefeld - unter den sichtbaren Bereich, ohne
     Weg dorthin. `100dvh` ist die tatsächlich sichtbare Höhe. -->
<div class="flex h-dvh overflow-hidden">
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

<!-- Einmal je Layout, geschaltet über den Store: Geöffnet wird der Dialog aus dem
     Nutzermenü und aus dem Chat-Kopf — beides Elemente, die beim Klick
     verschwinden. Ein Dialog, der dort hinge, ginge mit ihnen. -->
{#if $feedbackDialog.offen}
    <FeedbackDialog
        vorauswahlChat={$feedbackDialog.chatAnhaengen}
        onclose={schliesseFeedback}
    />
{/if}
