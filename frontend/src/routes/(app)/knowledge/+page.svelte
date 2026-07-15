<script>
    import KnowledgeNodeList from "$lib/components/KnowledgeNodeList.svelte";
    import { BP_CURRICULUM_CONTENT_TYPES } from "$lib/taxonomy.js";
</script>

<div class="h-full overflow-y-auto p-6">
    <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
            Wissensgraph
        </h1>
    </div>
    <!-- BP-Curriculum-Knoten (ik/pk/leitidee/…) gehören in BildungsplanTree/Curricula,
         nicht in die freie Liste — serverseitig ausgeblendet (C2). -->
    <KnowledgeNodeList
        showSubjectFilter={true}
        showNewButton={true}
        excludeContentTypes={BP_CURRICULUM_CONTENT_TYPES}
    />
</div>
