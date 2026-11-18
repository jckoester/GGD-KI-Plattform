<script>
    /**
     * Übersicht der Bibliothek (0.48, Päckchen N, G3/G4).
     *
     * Oben die Suche: Das Formular schickt an `/knowledge/search`, die Ergebnisseite mit
     * Filtern und Zustand in der Adresse. Darunter je Unterbereich eine Kachel. Dorthin führen
     * die Rückwege der Unterbereiche, damit die Hierarchie stimmt. Die Liste aller Bausteine,
     * die bis 0.47 hier lag, steht unter `/knowledge/all`.
     */
    import { goto } from "$app/navigation";
    import BibliothekSuchformular from "$lib/components/BibliothekSuchformular.svelte";
    import NodeTypeIcon from "$lib/components/NodeTypeIcon.svelte";
    import PageBody from "$lib/components/PageBody.svelte";
    import StufenHinweis from "$lib/components/StufenHinweis.svelte";
    import { bibliothekBereiche } from "$lib/bibliothek_bereiche.js";
    import { sidebarSammlungen } from "$lib/collections.js";
    import { pageTitle } from "$lib/stores/pageTitle.js";
    import { zeigtEintrag } from "$lib/stores/uiLevel.js";
    import { user } from "$lib/stores/user.js";

    pageTitle.set("Bibliothek");

    let frage = $state("");
    let typ = $state("");
    let fachId = $state("");
    let stufe = $state("");

    const istLehrkraft = $derived(
        ($user?.roles?.includes("teacher") ?? false) || ($user?.roles?.includes("admin") ?? false),
    );
    const bereiche = $derived(bibliothekBereiche({ istLehrkraft, zeigt: $zeigtEintrag }));

    function suchen() {
        const params = new URLSearchParams();
        for (const [name, wert] of [["q", frage.trim()], ["typ", typ], ["fach", fachId], ["stufe", stufe]]) {
            if (wert) params.set(name, String(wert));
        }
        goto(`/knowledge/search?${params}`);
    }

    const KACHEL =
        "flex flex-col gap-1 p-4 rounded-lg border border-light-ui-3 dark:border-dark-ui-3 " +
        "bg-light-bg dark:bg-dark-bg hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors";
</script>

<svelte:head><title>Bibliothek</title></svelte:head>

<PageBody>
    <StufenHinweis eintrag="knowledge" />
    <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">Bibliothek</h1>
    <p class="mt-1 mb-5 text-sm text-light-tx-2 dark:text-dark-tx-2">
        Bausteine, die du einem Chat als Wissen mitgeben kannst. Die Suche findet sie nach
        Namen und nach Thema.
    </p>

    <BibliothekSuchformular bind:frage bind:typ bind:fachId bind:stufe onsuchen={suchen} />

    {#if bereiche.length > 0}
        <h2 class="mt-8 mb-3 text-sm font-semibold text-light-tx dark:text-dark-tx">Bereiche</h2>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {#each bereiche as b (b.href)}
                <a href={b.href} class={KACHEL}>
                    <span class="flex items-center gap-2 font-medium text-light-tx dark:text-dark-tx">
                        <b.icon class="w-4 h-4" />
                        {b.titel}
                    </span>
                    <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">{b.text}</span>
                </a>
            {/each}
        </div>

        <h2 class="mt-8 mb-3 text-sm font-semibold text-light-tx dark:text-dark-tx">Sammlungen</h2>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {#each sidebarSammlungen() as s (s.typ)}
                <a href={`/knowledge/collections/${s.typ}`} class={KACHEL}>
                    <span class="flex items-center gap-2 font-medium text-light-tx dark:text-dark-tx">
                        <NodeTypeIcon contentType={s.typ} size={16} />
                        {s.label}
                    </span>
                </a>
            {/each}
        </div>
    {/if}
</PageBody>
