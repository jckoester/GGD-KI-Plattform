<script>
    import { page } from "$app/stores";
    import CollectionEditor from "$lib/components/CollectionEditor.svelte";

    const typ = $derived($page.params.type);
    const vorgabeFachId = $derived($page.url.searchParams.get("subject_id"));
    const back = $derived($page.url.searchParams.get("back"));
    // Vorgabe für den Titel — aus dem Curriculum-Editor, wenn ein Begriff fehlt (0.44, AQ).
    const vorgabeTitel = $derived($page.url.searchParams.get("titel"));
</script>

{#key typ}
    <CollectionEditor {typ} {vorgabeFachId} {vorgabeTitel} {back} />
{/key}
