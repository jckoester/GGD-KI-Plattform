<script>
    import KnowledgeNodeList from "$lib/components/KnowledgeNodeList.svelte";
</script>

<div class="h-full overflow-y-auto p-6">
    <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
            Wissensgraph
        </h1>
    </div>
    <KnowledgeNodeList showSubjectFilter={true} showNewButton={true} />
</div>
