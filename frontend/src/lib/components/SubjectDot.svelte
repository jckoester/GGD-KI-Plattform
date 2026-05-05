<script>
    /**
     * color: CSS-Farbwert (z.B. '#4f46e5' oder 'hsl(230 60% 50%)').
     * null/undefined → Primärfarben-Fallback (blau).
     * size: 'sm' (8×8px) | 'md' (12×12px)
     */
    let { color = null, size = 'sm' } = $props()

    const sizeClass = size === 'md' ? 'w-3 h-3' : 'w-2 h-2'
</script>

<span
    class="rounded-full shrink-0 {sizeClass}
           {color ? '' : 'bg-light-bl dark:bg-dark-bl'}"
    style={color ? `background-color: ${color}` : ''}
></span>
