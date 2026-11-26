<script>
    import { sidebarSammlungen } from '$lib/collections.js';
    import NodeTypeIcon from '$lib/components/NodeTypeIcon.svelte';
    import { branding } from "$lib/branding.js";
    import { slide } from "svelte/transition";
    import {
        Home,
        Plus,
        ChevronDown,
        Info,
        ChevronRight,
        History,
        ShieldCheck,
        Bot,
        Settings,
        BookOpen,
        Pencil,
        Database,
        Library,
        FolderHeart,
        Search,
        Hammer,
        CalendarRange,
        Archive,
    Check,
        ChartGantt,
    } from "@lucide/svelte";
    import SidebarBottom from "./SidebarBottom.svelte";
    import {
        recentConversations,
        refreshConversations,
    } from "$lib/stores/conversations.js";
    import { user } from "$lib/stores/user.js";
    import { zeigtEintrag, naechsteStufen, setzeStufe } from '$lib/stores/uiLevel.js';
    import { page } from "$app/stores";
    import { subjectMap } from "$lib/stores/subjects.js";
    import { myGroups } from "$lib/stores/myGroups.js";
    import { gruppenMarke, chatTooltip } from "$lib/gruppenmarke.js";
    import { visibleSidebarSubjectSections } from "$lib/stores/sidebarSections.js"
    import { refreshConversationCounts } from "$lib/stores/conversationCounts.js"
    import { refreshPotentialTeachingGroups } from "$lib/stores/potentialTeachingGroups.js"
    import { pendingCount, refreshPendingCount } from "$lib/stores/pendingAssistants.js"
    import { aufmerksamkeit, refreshAufmerksamkeit } from "$lib/stores/meineBausteine.js"
    import SidebarSubjectItem from "./SidebarSubjectItem.svelte"
    import SidebarLink from "./SidebarLink.svelte"
    import SidebarBereich from "./SidebarBereich.svelte"
    import ConversationMenu from "$lib/components/ConversationMenu.svelte";
    import { getPlanungsgruppen } from "$lib/api.js";
    import { menueGruppen, mitBeschriftung, plannerPfad } from "$lib/planung_archiv.js";
    import SubjectIcon from "./SubjectIcon.svelte";

    const initials = (name) => name.slice(0, 2).toUpperCase();

    let {
        bgHeaderClass = "bg-light-bg dark:bg-dark-bg-2",
        textClass = "text-light-tx dark:text-dark-tx",
        borderClass = "border-light-ui-2 dark:border-dark-ui-2",
    } = $props();

    // Zentrales Öffnungs-Signal: 'recent' | 'assistants' | 'subject-<id>' | null
    let openSection = $state(null)

    function toggle(key) {
        openSection = openSection === key ? null : key
    }

    // Der Name eines Bereichs öffnet ihn (und führt auf seine Seite); nur der Pfeil schließt.
    function oeffne(key) {
        openSection = key
    }

    // Assistenten-Sektion beim Navigieren auf /assistants/* auto-öffnen
    $effect(() => {
        if ($page.url.pathname.startsWith('/assistants')) {
            openSection = 'assistants'
        }
    })

    // Fach-Sektion beim Navigieren auf /subjects/<slug>[/*] auto-öffnen
    $effect(() => {
        const slug = $page.url.pathname.match(/^\/subjects\/([^/]+)/)?.[1]
        if (slug) {
            const found = $visibleSidebarSubjectSections.find(s => s.slug === slug)
            if (found) openSection = `subject-${found.subjectId}`
        }
    })

    // Admins sind Lehrkräfte mit zusätzlichen Rechten, kein eigener Nutzertyp (CLAUDE.md).
    // Darstellungsstufen: `$zeigtEintrag(key)` ist `true`, solange kein Zuschnitt geladen
    // ist oder die Rolle keine Stufen hat — dann zeigt die Sidebar alles. Der Filter ist
    // ein Anzeige-Filter, KEINE Berechtigung: Was hier fehlt, bleibt über Direktlink
    // erreichbar (Rollenmodell, ADR-003). Die Rollenweichen unten greifen unabhängig
    // davon — erst entscheidet die Rolle, was es gibt, dann die Stufe, was davon zu
    // sehen ist.
    // Der Hinweis auf verborgene Funktionen ist eingeklappt. Aufgeklappt wirkte er wie
    // eine Aufgabe, die zu erledigen ist, und drängte auf die höchste Stufe — das
    // Gegenteil des Zwecks. Er soll sagen „es gibt mehr", nicht „schalte mehr frei".
    let mehrOffen = $state(false);

    const istLehrkraft = $derived(
        $user?.roles.includes('teacher') || $user?.roles.includes('admin'),
    );

    // Menüpunkt „Planung“ (0.42): je aktuelle Gruppe ein Link in ihren Planer, dazu das
    // Archiv. Geladen nur für Lehrkräfte mit der Stufe des Planers; neu bei jedem Wechsel
    // in einen Planer oder ins Archiv — dort ändert sich, was aktuell ist.
    let planungsgruppen = $state([]);
    const imPlaner = $derived(
        /^\/subjects\/[^/]+\/groups\/\d+\/planner/.test($page.url.pathname)
        || $page.url.pathname.startsWith('/planning'),
    );
    $effect(() => {
        if (!istLehrkraft || !$zeigtEintrag('planner')) return;
        imPlaner;
        getPlanungsgruppen()
            .then((g) => (planungsgruppen = mitBeschriftung(menueGruppen(g))))
            .catch(() => (planungsgruppen = []));
    });
    $effect(() => {
        if (imPlaner) openSection = 'planning';
    });

    // Bibliothek beim Navigieren auf /knowledge[/*] auto-öffnen
    $effect(() => {
        if ($page.url.pathname.startsWith('/knowledge')) {
            openSection = 'knowledge'
        }
    })

    function formatDate(dateString) {
        if (!dateString) return "";
        const date = new Date(dateString);
        const now = new Date();

        // Prüfe ob heute
        const today = new Date(
            now.getFullYear(),
            now.getMonth(),
            now.getDate(),
        );
        const dateDate = new Date(
            date.getFullYear(),
            date.getMonth(),
            date.getDate(),
        );

        if (dateDate.getTime() === today.getTime()) {
            // Heute: nur Uhrzeit
            return date.toLocaleTimeString("de-DE", {
                hour: "2-digit",
                minute: "2-digit",
            });
        }

        // Prüfe ob gestern
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        if (dateDate.getTime() === yesterday.getTime()) {
            return "Gestern";
        }

        // Prüfe ob dieses Jahr
        if (date.getFullYear() === now.getFullYear()) {
            return date.toLocaleDateString("de-DE", {
                day: "2-digit",
                month: "2-digit",
            });
        }

        // Älter: voller Datum
        return date.toLocaleDateString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        });
    }

    // Aktive Konversations-ID aus URL extrahieren
    const currentConversationId = $derived($page.url.searchParams.get("id"));

    // Limit aus User-Präferenzen
    const limit = $derived(
        $user?.preferences?.sidebar_recent_chats_limit ?? 10,
    );

    // Aktualisieren beim Ändern des Limits
    $effect(() => {
        refreshConversations(limit);
        refreshConversationCounts();
        refreshPotentialTeachingGroups();
        if (istLehrkraft) refreshAufmerksamkeit();
    });

    // Fächer-Container offen wenn ein Fach oder der Container selbst aktiv ist
    const subjectsOpen = $derived(
        openSection === 'subjects' || (openSection?.startsWith('subject-') ?? false)
    )

    function toggleSubjects() {
        openSection = subjectsOpen ? null : 'subjects'
    }

    function handleDeleted() {
        refreshConversations(limit);
        refreshConversationCounts();
        refreshPotentialTeachingGroups();
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

    <!-- Sidebar-Inhalt. Seit 0.48 (Päckchen N) sind alle Einträge echte Links
         (`SidebarLink`, `SidebarBereich`): ganze Zeile klickbar, Strg-Klick und neuer Tab
         gehen, der Pfeil eines Bereichs klappt nur auf oder zu. -->
    <div class="flex-1 overflow-y-auto p-2">
        {#if $zeigtEintrag('welcome')}
    <!-- Startseite: der Tag auf einen Blick. Steht ganz oben, weil sie die Frage
         beantwortet, mit der man sich morgens anmeldet. -->
            <SidebarLink href="/welcome" haupt aktiv={$page.url.pathname === '/welcome'}>
                <Home class="w-4 h-4" />
                Startseite
            </SidebarLink>
        {/if}

        {#if $zeigtEintrag('chat')}
            <SidebarLink href="/chat" haupt>
                <Plus class="w-4 h-4" />
                Neuer Chat
            </SidebarLink>
        {/if}

        {#if $zeigtEintrag('assistants')}
    <!-- Assistenten: aufklappbar nur für Lehrkräfte (Meine, Verwalten, Freigaben). -->
            <div class="mt-2">
                <SidebarBereich
                    href="/assistants"
                    label="Assistenten"
                    aufklappbar={istLehrkraft}
                    offen={openSection === 'assistants'}
                    ontoggle={() => toggle('assistants')}
                    onnavigate={() => oeffne('assistants')}
                    aktiv={$page.url.pathname.startsWith('/assistants')}
                >
                    <Bot class="w-4 h-4" />
                    Assistenten
                </SidebarBereich>
                {#if openSection === 'assistants' && istLehrkraft}
                    <div class="mt-1 space-y-1 pl-5">
                        {#if $zeigtEintrag('assistants_my')}
                            <SidebarLink href="/assistants/my"
                                aktiv={$page.url.pathname.startsWith('/assistants/my')}>
                                <Pencil class="w-4 h-4" />
                                Meine Assistenten
                            </SidebarLink>
                        {/if}
                        {#if $user?.roles.includes('admin')}
                            <SidebarLink href="/assistants/manage" onclick={refreshPendingCount}
                                aktiv={$page.url.pathname === '/assistants/manage'}>
                                <Settings class="w-4 h-4" />
                                Verwalten
                            </SidebarLink>
                            <!-- Offene Freigaben stehen seit 0.27 unter Einstellungen → Assistenten-Freigabe. -->
                            {#if $pendingCount > 0}
                                <SidebarLink href="/settings/assistants">
                                    <Check class="w-4 h-4" />
                                    Freigaben
                                    <span class="ml-auto text-xs font-semibold px-1.5 py-0.5 rounded-full
                                         bg-light-ye/30 dark:bg-dark-ye/30 text-light-ye dark:text-dark-ye">
                                        {$pendingCount}
                                    </span>
                                </SidebarLink>
                            {/if}
                        {/if}
                    </div>
                {/if}
            </div>

        {/if}
        {#if $zeigtEintrag('workshop')}
    <!-- Werkstatt (alle Rollen; bis 0.40 „Bibliothek“) -->
            <div class="mt-2">
                <SidebarLink href="/workshop" haupt aktiv={$page.url.pathname.startsWith('/workshop')}>
                    <Hammer class="w-4 h-4" />
                    Werkstatt
                </SidebarLink>
            </div>

        {/if}
        {#if $zeigtEintrag('knowledge')}
    <!-- Bibliothek. Der Menüpunkt steht allen offen: Seine Landeseite ist seit 0.48 die
                 Übersicht `/knowledge` (Suche und Kacheln), und die Suche durchsucht denselben Bestand, den Schüler:innen über den
                 Suchknopf im Chat ohnehin erreichen.

                 Seit AP7 ist die Sektion **für alle Rollen** aufklappbar. Schüler:innen
                 sehen darin seit 0.41 nur die Suche — ihre eigene Arbeit liegt in der
                 Werkstatt („Meine Bausteine“ entfällt für sie, Päckchen AN Schritt 9). Die
                 übrigen Unterpunkte (Meine und Alle Bausteine, Sammlungen, Curricula,
                 Bildungspläne, Leitperspektiven) bleiben Lehrkraft-Sache. -->
              <div class="mt-2">
                <SidebarBereich
                    href="/knowledge"
                    label="Bibliothek"
                    offen={openSection === 'knowledge'}
                    ontoggle={() => toggle('knowledge')}
                    onnavigate={() => oeffne('knowledge')}
                    aktiv={$page.url.pathname.startsWith('/knowledge')}
                >
                    <Library class="w-4 h-4" />
                    Bibliothek
                </SidebarBereich>
                {#if openSection === 'knowledge'}
                    <div class="mt-1 space-y-1 pl-5" transition:slide={{ duration: 150 }}>
                        <!-- Für alle Rollen: die Suche. „Meine Bausteine“ nur für Lehrkräfte (0.41). -->
                        <SidebarLink href="/knowledge/search"
                            aktiv={$page.url.pathname === '/knowledge/search'}>
                            <Search class="w-4 h-4" />
                            Suche
                        </SidebarLink>
                        {#if istLehrkraft}
                        <SidebarLink href="/knowledge/mine"
                            aktiv={$page.url.pathname === '/knowledge/mine'}>
                            <FolderHeart class="w-4 h-4" />
                            Meine Bausteine
                            {#if $aufmerksamkeit.gesamt > 0}
                                <span class="ml-auto text-xs font-semibold px-1.5 py-0.5 rounded-full
                                     bg-light-ye/30 dark:bg-dark-ye/30 text-light-ye dark:text-dark-ye"
                                     title="{$aufmerksamkeit.gesamt} Bausteine brauchen Aufmerksamkeit">
                                    {$aufmerksamkeit.gesamt}
                                </span>
                            {/if}
                        </SidebarLink>
                        {/if}

                        <!-- Ab hier Lehrkraft-Sache. Bewusst im selben Aufklapp-Container:
                             Zwei `transition:slide` nebeneinander liefen als zwei
                             Animationen ab und ruckelten sichtbar. -->
                        {#if istLehrkraft}
                        <SidebarLink href="/knowledge/all" aktiv={$page.url.pathname === '/knowledge/all'}>
                            <Database class="w-4 h-4" />
                            Alle Bausteine
                        </SidebarLink>
                        <!-- Sammlungen: gepflegte Bestände je Bausteinart. Die Liste
                             kommt aus der Taxonomie (`collection:`-Block) — eine neue
                             Sammlung erscheint hier ohne Code-Änderung. -->
                        <div class="pl-3 pt-1 pb-0.5 text-xs uppercase tracking-wide
                                    text-light-tx-3 dark:text-dark-tx-3">
                            Sammlungen
                        </div>
                        {#each sidebarSammlungen() as s (s.typ)}
                            <SidebarLink href={`/knowledge/collections/${s.typ}`}
                                aktiv={$page.url.pathname === `/knowledge/collections/${s.typ}`}>
                                <NodeTypeIcon contentType={s.typ} size={16} />
                                {s.label}
                            </SidebarLink>
                        {/each}

                        {#if $zeigtEintrag('curricula')}
                        <!-- Jahresverlaufspläne (0.59, BD), vor den Curricula (Hierarchie Jan: Verlaufsplan – Curriculum – Bildungsplan): dieselbe Darstellungsstufe wie die Curricula —
                             bewusst derselbe Schlüssel, ein eigener fehlte in der Schuldatei `ui_levels.yaml`
                             und bliebe auf Prod unsichtbar, bis jemand ihn von Hand nachträgt. -->
                        <SidebarLink href="/knowledge/year-plans"
                            aktiv={$page.url.pathname.startsWith('/knowledge/year-plans')}>
                            <ChartGantt class="w-4 h-4" />
                            Jahresverlaufspläne
                        </SidebarLink>
                        <SidebarLink href="/knowledge/curricula"
                            aktiv={$page.url.pathname === '/knowledge/curricula'}>
                            <BookOpen class="w-4 h-4" />
                            Curricula
                        </SidebarLink>
                        {/if}
                        {#if $zeigtEintrag('education_plans')}
                        <SidebarLink href="/knowledge/education-plans"
                            aktiv={$page.url.pathname === '/knowledge/education-plans'}>
                            <BookOpen class="w-4 h-4" />
                            Bildungspläne
                        </SidebarLink>
                        <SidebarLink href="/knowledge/cross-cutting-themes"
                            aktiv={$page.url.pathname === '/knowledge/cross-cutting-themes'}>
                            <ShieldCheck class="w-4 h-4" />
                            Leitperspektiven
                        </SidebarLink>
                        {/if}
                        {/if}
                    </div>
                {/if}
              </div>

        {/if}
        {#if istLehrkraft && $zeigtEintrag('planner')}
    <!-- Planung (0.42, Päckchen AO): je aktuelle Gruppe der Planer, darunter das Archiv.
         Keine Liste aller Planungsknoten (Jan, F2). Seit 0.42.2 öffnet der Kopf die
         Übersicht `/planning` (Kacheln je Gruppe, Archiv abgesetzt). -->
              <div class="mt-2">
                <SidebarBereich
                    href="/planning"
                    label="Planung"
                    offen={openSection === 'planning'}
                    ontoggle={() => toggle('planning')}
                    onnavigate={() => oeffne('planning')}
                    aktiv={imPlaner}
                >
                    <CalendarRange class="w-4 h-4" />
                    Planung
                </SidebarBereich>
                {#if openSection === 'planning'}
                    <div class="mt-1 space-y-1 pl-5" transition:slide={{ duration: 150 }}>
                        {#each planungsgruppen as g (g.id)}
                            {@const pfad = plannerPfad(g)}
                            {@const fach = $subjectMap[g.fach.id]}
                            <!-- Wie „Meine Fächer“: Fachsymbol in Fachfarbe. Beschriftung statt der
                                 Kennung aus dem Schulkonto; die steht im Tooltip. -->
                            <SidebarLink href={pfad}
                                title={g.beschriftung === g.name ? g.fach.name : `${g.fach.name} · ${g.name}`}
                                aktiv={$page.url.pathname.startsWith(pfad)}>
                                <SubjectIcon name={fach?.icon ?? null} size={15} color={fach?.color ?? null} />
                                <span class="flex-1 min-w-0 truncate">{g.beschriftung}</span>
                            </SidebarLink>
                        {:else}
                            <p class="px-3 py-1 text-xs text-light-tx-2 dark:text-dark-tx-2">
                                Keine Unterrichtsgruppe in diesem Schuljahr.
                            </p>
                        {/each}
                        <SidebarLink href="/planning/archive"
                            aktiv={$page.url.pathname.startsWith('/planning/archive')}>
                            <Archive class="w-4 h-4" />
                            Archiv
                        </SidebarLink>
                    </div>
                {/if}
              </div>

        {/if}
        {#if $zeigtEintrag('subjects')}
    {#if $visibleSidebarSubjectSections.length > 0}
              <div class="mt-2">
                <SidebarBereich
                    href="/subjects"
                    label="Meine Fächer"
                    offen={subjectsOpen}
                    ontoggle={toggleSubjects}
                    onnavigate={() => { if (!subjectsOpen) openSection = 'subjects' }}
                    aktiv={$page.url.pathname.startsWith('/subjects')}
                >
                    <BookOpen size={16} />
                    Meine Fächer
                </SidebarBereich>

                {#if subjectsOpen}
                    <div class="mt-1 space-y-1 pl-5" transition:slide={{ duration: 150 }}>
                        {#each $visibleSidebarSubjectSections as section (section.type === 'student' ? `s-${section.groupId}` : `t-${section.subjectId}`)}
                            <SidebarSubjectItem
                                {section}
                                expanded={openSection === `subject-${section.subjectId}`}
                                ontoggle={() => toggle(`subject-${section.subjectId}`)}
                            />
                        {/each}
                    </div>
                {/if}
              </div>
            {/if}
        {/if}

        {#if $zeigtEintrag('history')}
    <!-- Letzte Chats: Kopf führt in den Verlauf, aufgeklappt die letzten Chats. -->
            <div class="mt-2">
                <SidebarBereich
                    href="/history"
                    label="Letzte Chats"
                    offen={openSection === 'recent'}
                    ontoggle={() => toggle('recent')}
                    onnavigate={() => oeffne('recent')}
                    aktiv={$page.url.pathname === '/history'}
                >
                    <History class="w-4 h-4" />
                    Letzte Chats
                </SidebarBereich>

                {#if openSection === 'recent'}
                    <div class="mt-1 space-y-1 pl-5">
                        {#if $recentConversations.length === 0}
                            <p
                                class="text-sm text-light-tx-3 dark:text-dark-tx-3 px-3 py-1"
                            >
                                Noch keine Chats
                            </p>
                        {:else}
                            {#each $recentConversations as conv (conv.id)}
                                {@const convColor = conv.subject_id != null
                                    ? ($subjectMap[conv.subject_id]?.color ?? null)
                                    : null}
                                <!-- Link und Menü nebeneinander statt verschachtelt: Ein Knopf
                                     im Link wäre ungültiges HTML, und ein Klick ins Menü
                                     öffnete sonst zugleich den Chat. -->
                                <div
                                    class="relative overflow-hidden flex items-center gap-1 pr-1 rounded-lg text-sm
                                           text-light-tx dark:text-dark-tx transition-colors
                                           {conv.id === currentConversationId
                                        ? 'bg-light-ui-2 dark:bg-dark-ui-2'
                                        : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                                >
                                    <!-- Farbstreifen links (nur wenn Fach mit Farbe) -->
                                    {#if convColor}
                                        <span
                                            class="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-lg"
                                            style="background-color: {convColor}"
                                        ></span>
                                    {/if}
                                    <a
                                        href={`/chat?id=${conv.id}`}
                                        aria-current={conv.id === currentConversationId ? 'page' : undefined}
                                        class="flex-1 min-w-0 flex justify-between items-center gap-1 pl-3 py-2"
                                    >
                                        <span class="flex items-center gap-1 min-w-0">
                                            {#if conv.assistant_name}
                                                <Bot
                                                    class="w-3 h-3 shrink-0 text-light-bl dark:text-dark-bl"
                                                    title={conv.assistant_name}
                                                />
                                            {/if}
                                            <!-- Die Unterrichtsgruppe steht hier nur im
                                                 Tooltip: Titel, Datum und Menü teilen
                                                 sich bereits eine schmale Zeile. In der
                                                 History, wo Platz ist, steht sie sichtbar. -->
                                            <span
                                                class="truncate"
                                                title={chatTooltip(
                                                    conv.title,
                                                    gruppenMarke(conv.group_id, $myGroups, { istLehrkraft }),
                                                )}
                                            >
                                                {conv.title ?? "Unbenannter Chat"}
                                            </span>
                                        </span>
                                        <span
                                            class="text-xs text-light-tx-3 dark:text-dark-tx-3 whitespace-nowrap"
                                        >
                                            {formatDate(conv.last_message_at)}
                                        </span>
                                    </a>
                                    <ConversationMenu
                                        conversationId={conv.id}
                                        title={conv.title}
                                        subject_id={conv.subject_id}
                                        group_id={conv.group_id}
                                        onDeleted={handleDeleted}
                                        iconSize={12}
                                    />
                                </div>
                            {/each}
                        {/if}
                    </div>
                {/if}
            </div>
        {/if}

        <!-- Hinweis auf verborgene Funktionen (Leitprinzip 5 der Konzeptnotiz).
             Ohne ihn entsteht der Eindruck, das Werkzeug könne wenig — das Gegenteil
             dessen, was die Stufen bezwecken. Deshalb dezent, aber vorhanden. -->
        {#if $naechsteStufen.length > 0}
            {@const naechste = $naechsteStufen[0]}
            <div class="mt-4">
                <button
                    onclick={() => (mehrOffen = !mehrOffen)}
                    aria-expanded={mehrOffen}
                    class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm
                           text-light-tx-2 dark:text-dark-tx-2
                           border border-dashed border-light-ui-3 dark:border-dark-ui-3
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                >
                    <Info class="w-4 h-4 shrink-0" />
                    <span class="flex-1 text-left">Es gibt mehr</span>
                    {#if mehrOffen}
                        <ChevronDown class="w-4 h-4 shrink-0" />
                    {:else}
                        <ChevronRight class="w-4 h-4 shrink-0" />
                    {/if}
                </button>

                {#if mehrOffen}
                    <div class="mt-1 px-3 py-2" transition:slide={{ duration: 150 }}>
                        <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                            Noch nicht eingeblendet:
                        </p>
                        <ul
                            class="mt-1 ml-1 space-y-0.5 text-xs text-light-tx-2 dark:text-dark-tx-2"
                        >
                            {#each $naechsteStufen as s (s.stufe)}
                                <li>· {s.name}</li>
                            {/each}
                        </ul>

                        <!-- Eigene Überschrift, sonst liest sich der Absatz wie eine
                             Wiederholung der Liste darüber. -->
                        <p
                            class="mt-2.5 text-xs font-medium text-light-tx dark:text-dark-tx"
                        >
                            Nächste Stufe
                        </p>
                        <p class="mt-0.5 text-xs text-light-tx-2 dark:text-dark-tx-2">
                            <b>{naechste.name}</b> — {naechste.beschreibung}
                        </p>
                        {#if naechste.aufwand}
                            <p
                                class="mt-1 text-xs italic text-light-tx-2 dark:text-dark-tx-2"
                            >
                                {naechste.aufwand}
                            </p>
                        {/if}
                        <button
                            onclick={() => setzeStufe(naechste.stufe)}
                            class="mt-2 text-xs underline text-light-tx dark:text-dark-tx
                                   hover:no-underline transition-all"
                        >
                            Einblenden
                        </button>
                        <p class="mt-1.5 text-xs text-light-tx-2 dark:text-dark-tx-2">
                            Jederzeit im Profil zurückzunehmen; es geht nichts verloren.
                        </p>
                    </div>
                {/if}
            </div>
        {/if}
    </div>

    <!-- Unterer Bereich -->
    <SidebarBottom />
</aside>
