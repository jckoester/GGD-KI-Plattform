<script>
    /**
     * Ein Eintrag der Seitenleiste (0.48, Päckchen N).
     *
     * Ein echter Link auf ganzer Zeilenbreite. Bis 0.47 waren die Einträge `<button>` mit
     * `goto()`: Strg-Klick, Mittelklick und „In neuem Tab öffnen“ gingen nicht, und beim
     * Überfahren zeigte der Browser kein Ziel. Die Hervorhebung entscheidet der Aufrufer
     * (`aktiv`), weil die Regel je Eintrag verschieden ist (genau dieser Pfad oder alles
     * darunter).
     */
    let {
        href,
        aktiv = false,
        haupt = false,
        title = undefined,
        onclick = undefined,
        children,
    } = $props();
</script>

<a
    {href}
    {title}
    {onclick}
    aria-current={aktiv ? 'page' : undefined}
    class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-light-tx dark:text-dark-tx
           transition-colors {haupt ? 'font-medium' : ''}
           {aktiv
               ? 'bg-light-ui-2 dark:bg-dark-ui-2 font-medium'
               : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
>
    {@render children()}
</a>
