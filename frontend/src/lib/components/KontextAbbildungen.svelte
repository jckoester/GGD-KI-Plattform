<script>
    // Die Abbildungen eines Bausteins in der Kontextliste (0.14, Schritt 4) — geholt erst,
    // wenn die Liste aufgeklappt ist (die Komponente steht nur dann).
    import { ladeAbbildungen, zeigeAbbildungen } from "$lib/kontext_anzeige.js";

    let { nodeId } = $props();

    let abbildungen = $state([]);
    let wurzel = $state(null);

    $effect(() => {
        let aktuell = true;
        ladeAbbildungen(nodeId).then((liste) => {
            if (aktuell) abbildungen = liste;
        });
        return () => (aktuell = false);
    });

    $effect(() => {
        zeigeAbbildungen(wurzel, abbildungen);
    });
</script>

<span bind:this={wurzel} class="block"></span>
