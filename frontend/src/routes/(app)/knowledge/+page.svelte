<script>
    import KnowledgeNodeList from "$lib/components/KnowledgeNodeList.svelte";
    import { BP_CURRICULUM_CONTENT_TYPES } from "$lib/taxonomy.js";
    import PageBody from '$lib/components/PageBody.svelte'
    import { FolderHeart } from "lucide-svelte";
</script>

<PageBody breit>
    <div class="flex items-center justify-between gap-4 mb-6 flex-wrap">
        <div>
            <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
                Alle Bausteine
            </h1>
            <p class="mt-1 text-sm text-light-tx-2 dark:text-dark-tx-2">
                Der gemeinsame Bestand der Schule — Fachschaftsmaterial, Sammlungen
                und was Kolleg:innen geteilt haben.
            </p>
        </div>
        <!-- Absprung statt Filter (A4, entschieden 05.09.2026): Ein Filter „Meine"
             hier hätte dieselbe Liste zweimal erklärt. „Meine Bausteine" ist eine
             eigene Seite mit eigenen Aufgaben — Lebenszyklus, Rechenschaft,
             Aufräumen —, nicht eine gefilterte Ansicht dieser hier. -->
        <a
            href="/knowledge/mine"
            class="shrink-0 flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg
                   border border-light-ui-3 dark:border-dark-ui-3
                   text-light-tx dark:text-dark-tx
                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
        >
            <FolderHeart class="w-4 h-4" />
            Meine Bausteine
        </a>
    </div>
    <!-- BP-Curriculum-Knoten (ik/pk/leitidee/…) gehören in BildungsplanTree/Curricula,
         nicht in die freie Liste — serverseitig ausgeblendet (C2). -->
    <KnowledgeNodeList
        showSubjectFilter={true}
        showNewButton={true}
        excludeContentTypes={BP_CURRICULUM_CONTENT_TYPES}
    />
</PageBody>
