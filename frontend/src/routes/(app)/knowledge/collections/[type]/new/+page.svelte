<script>
    import { page } from "$app/stores";
    import CollectionEditor from "$lib/components/CollectionEditor.svelte";

    const typ = $derived($page.params.type);
    const vorgabeFachId = $derived($page.url.searchParams.get("subject_id"));
    const back = $derived($page.url.searchParams.get("back"));
</script>

{#key typ}
    <CollectionEditor {typ} {vorgabeFachId} {back} />
{/key}
