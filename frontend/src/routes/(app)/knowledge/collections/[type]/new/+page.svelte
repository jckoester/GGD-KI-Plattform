<script>
    import { rueckwegAus } from "$lib/rueckweg.js";
    import { page } from "$app/stores";
    import CollectionEditor from "$lib/components/CollectionEditor.svelte";
    import { feldSchema } from "$lib/collections.js";

    const typ = $derived($page.params.type);
    const vorgabeFachId = $derived($page.url.searchParams.get("subject_id"));
    const back = $derived(rueckwegAus($page.url.searchParams));
    // Vorgabe für den Titel — aus dem Curriculum-Editor, wenn ein Begriff fehlt (0.44, AQ).
    const vorgabeTitel = $derived($page.url.searchParams.get("titel"));
    // Textfelder des Typs, vorbelegt aus der Adresse — etwa `?leitlinie=SDG` (0.50, AT).
    const vorgabeFelder = $derived(Object.fromEntries(
        Object.entries(feldSchema(typ))
            .filter(([name, f]) => f.typ === "text" && $page.url.searchParams.get(name))
            .map(([name]) => [name, $page.url.searchParams.get(name)]),
    ));
</script>

{#key typ}
    <CollectionEditor {typ} {vorgabeFachId} {vorgabeTitel} {vorgabeFelder} {back} />
{/key}
