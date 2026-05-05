<script>
    /**
     * name: lucide-svelte Icon-Name in kebab-case, z.B. 'calculator', 'book-open'.
     *       null/undefined → sofort Fallback.
     * size: Pixel-Größe (wird als `size`-Prop an die Lucide-Komponente übergeben).
     * class: Zusätzliche CSS-Klassen.
     */
    let { name = null, size = 16, class: className = '' } = $props()

    let Component = $state(null)

    function toPascalCase(kebab) {
        return kebab
            .split('-')
            .map(s => s.charAt(0).toUpperCase() + s.slice(1))
            .join('')
    }

    $effect(() => {
        const iconName = name
        if (!iconName) {
            loadFallback()
            return
        }
        import('lucide-svelte').then(mod => {
            const pascal = toPascalCase(iconName)
            Component = mod[pascal] ?? null
            if (!Component) loadFallback()
        })
    })

    function loadFallback() {
        import('lucide-svelte').then(mod => {
            Component = mod['SquareX'] ?? null
        })
    }
</script>

{#if Component}
    <svelte:component this={Component} {size} class={className} />
{/if}
