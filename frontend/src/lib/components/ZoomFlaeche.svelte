<script>
    // Ein großes Diagramm vergrößern und verschieben (0.41, Schritt 8; Todo „Große Diagramme
    // vergrößern“, 06.11.2026). Pele bringt das für jedes fertige SVG mit (`enableZoom`) —
    // auch für Schaltpläne, Funktionsgraphen und Strukturformeln vom Server. Gedacht als
    // gemeinsames Bauteil; der Chat nutzt denselben Helfer (`$lib/zoom.js`).
    //
    // `svg` muss bereits bereinigt sein (`sanitizeSvg`).
    import { onDestroy } from 'svelte'
    import { zoomAnhaengen } from '$lib/zoom.js'

    // `immer`: Knöpfe auch dann, wenn das Diagramm schon passt — in der Produktansicht ist
    // Vergrößern der Zweck. Ohne zeigt Pele sie nur bei Bedarf (nachgeprüft in jsdom, 13.11.2026).
    let { svg, hoehe = '70vh', titel = 'Diagramm', immer = true } = $props()

    let flaeche = $state(null)
    let zoom = null

    $effect(() => {
        if (!flaeche || !svg) return
        let abgebrochen = false
        zoomAnhaengen(flaeche, { immer }).then((z) => {
            if (abgebrochen) { z.destroy(); return }
            zoom?.destroy()
            zoom = z
        })
        return () => { abgebrochen = true }
    })

    onDestroy(() => zoom?.destroy())
</script>

<div
    bind:this={flaeche}
    role="img"
    aria-label={titel}
    class="relative w-full overflow-hidden rounded-lg border border-light-ui-3 dark:border-dark-ui-3 bg-white"
    style="height: {hoehe}"
>
    <!-- eslint-disable-next-line svelte/no-at-html-tags -- `svg` ist bereinigt (sanitizeSvg) -->
    {@html svg}
</div>
