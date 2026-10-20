<script>
    import { CalendarDays, MessageSquareWarning, PanelLeftClose, PanelLeftOpen } from "lucide-svelte";
    import { oeffneFeedback } from "$lib/stores/feedbackDialog.js";
    import { page } from "$app/stores";
    import { pageTitle, activeConversationId, activeConversationSubjectId, activeConversationGroupId, activeConversationStunde } from "$lib/stores/pageTitle.js";
    import { stundenDatum, stundenPfad, stundenText } from "$lib/chat_stunde.js";
    import ConversationMenu from "$lib/components/ConversationMenu.svelte";
    import SubjectIcon from "$lib/components/SubjectIcon.svelte";
    import { subjectMap } from "$lib/stores/subjects.js";

    // Props
    let {
        sidebarOpen,
        onToggle,
        bgClass = "bg-light-bg-2 dark:bg-dark-bg-2",
        textClass = "text-light-tx dark:text-dark-tx",
        borderClass = "border-light-ui-2 dark:border-dark-ui-2",
    } = $props();

    // Hintergrundfarbe
    //let bgClass = $page.data.headerColor ?? "bg-light-bg-2 dark:bg-dark-bg-2";

    // Abgeleiteter Titel
    let title = $derived($pageTitle || ($page.data.title ?? ""));

    // Link zur Bezugsstunde des Chats (0.19) — nur, solange eine Konversation offen ist.
    let stundenLink = $derived($activeConversationId ? stundenPfad($activeConversationStunde) : null);

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

        <!-- Seitentitel (mit optionalem Fach-Icon) -->
        <div class="flex items-center gap-2">
            {#if $activeConversationSubjectId && $subjectMap[$activeConversationSubjectId]}
                <SubjectIcon
                    name={$subjectMap[$activeConversationSubjectId].icon}
                    color={$subjectMap[$activeConversationSubjectId].color}
                    size={18}
                    class="shrink-0"
                />
            {/if}
            <h1 class="text-lg font-semibold {textClass}">{title}</h1>
            {#if stundenLink}
                <a
                    href={stundenLink}
                    title="Zum Stundenentwurf"
                    class="inline-flex items-center gap-1 min-w-0 rounded-full border
                           border-light-ui-3 dark:border-dark-ui-3 px-2 py-0.5 text-xs
                           text-light-bl dark:text-dark-bl hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
                    aria-label="Zum Stundenentwurf: {stundenText($activeConversationStunde)}"
                >
                    <CalendarDays size={14} class="shrink-0" />
                    <!-- Nur der Titel wird gekürzt — der Tag bleibt lesbar. -->
                    <span class="truncate max-w-[12rem]">{$activeConversationStunde.titel}</span>
                    {#if stundenDatum($activeConversationStunde.datum)}
                        <span class="shrink-0">· {stundenDatum($activeConversationStunde.datum)}</span>
                    {/if}
                    <span class="shrink-0" aria-hidden="true">↗</span>
                </a>
            {/if}
        </div>
    </div>

    <!-- Rechte Seite: Abmelden-Button oder Konversationsmenü -->
    {#if $activeConversationId}
        <div class="flex items-center">
            <!-- Der kurze Weg: Wer im Chat auf einen Fehler stößt, soll ihn dort melden
                 können, wo er auftritt — mit dem Chat als Beleg, vorausgewählt. -->
            <button
                onclick={() => oeffneFeedback({ chatAnhaengen: true })}
                aria-label="Feedback zu diesem Chat"
                title="Feedback zu diesem Chat"
                class="p-2 rounded-lg hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 {textClass} transition-colors"
            >
                <MessageSquareWarning size={20} />
            </button>
        <ConversationMenu
            conversationId={$activeConversationId}
            title={$pageTitle}
            subject_id={$activeConversationSubjectId}
            group_id={$activeConversationGroupId}
            syncPageTitle={true}
            buttonClasses=" hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
        />
        </div>
    {/if}
</header>
