<script>
    import { page } from "$app/stores";
    import { getContextNode } from "$lib/api.js";
    import CollectionEditor from "$lib/components/CollectionEditor.svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import LoadingBanner from "$lib/components/LoadingBanner.svelte";

    const typ = $derived($page.params.type);
    const back = $derived($page.url.searchParams.get("back"));
    let node = $state(null);
    let error = $state(null);

    $effect(() => {
        const id = $page.params.id;
        node = null;
        error = null;
        getContextNode(id)
            .then((n) => (node = n))
            .catch((e) => (error = e.message));
    });
</script>

{#if error}
    <div class="p-6"><ErrorBanner message={error} /></div>
{:else if !node}
    <div class="p-6"><LoadingBanner /></div>
{:else}
    {#key node.id}
        <CollectionEditor {typ} {node} {back} />
    {/key}
{/if}
