<script>
    /**
     * name: Lucide-Icon-Name (`@lucide/svelte`) in kebab-case, z.B. 'calculator', 'book-open'.
     *       null/undefined → sofort Fallback.
     * size: Pixel-Größe (wird als `size`-Prop an die Lucide-Komponente übergeben).
     * class: Zusätzliche CSS-Klassen.
     */
    import { symbolLader } from '$lib/fach_symbol.js'

    let { name = null, size = 16, class: className = '', color = null } = $props()

    let Component = $state(null)

    $effect(() => {
        const iconName = name
        let abgebrochen = false
        ;(symbolLader(iconName) ?? symbolLader('square-x'))?.().then((mod) => {
            if (!abgebrochen) Component = mod.default ?? null
        })
        return () => {
            abgebrochen = true
        }
    })
</script>

{#if Component}
    <Component {size} {color} class={className} />
{/if}
