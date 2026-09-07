<script>
    /**
     * Symbol eines Knotens: Form aus dem content_type, Farbe aus der Kategorie.
     *
     * Die Zuordnung wird aus `taxonomy.yaml` erzeugt (`node_icons.js`) — das Symbol
     * wird am Typ gepflegt, nicht hier. Vorher stand sie von Hand in dieser Datei
     * und deckte 11 von 41 Typen ab; der Rest fiel auf das Kategorie-Symbol
     * zurück, sodass in artefakt-lastigen Listen fast jede Zeile dasselbe Paket trug.
     */
    import { CATEGORY_COLORS } from "$lib/taxonomy.js";
    import { CATEGORY_ICONS, FALLBACK_ICON, NODE_ICONS } from "$lib/node_icons.js";

    let { category = undefined, contentType = undefined, size = 16 } = $props();

    // Statische Klassen-Map — alle Strings müssen literal im Quelltext stehen,
    // damit Tailwind sie nicht wegputzt.
    const COLOR_CLASSES = {
        bl: "text-light-bl dark:text-dark-bl",
        gr: "text-light-gr dark:text-dark-gr",
        or: "text-light-or dark:text-dark-or",
        pu: "text-light-pu dark:text-dark-pu",
        "tx-2": "text-light-tx-2 dark:text-dark-tx-2",
    };

    const colorToken = $derived(CATEGORY_COLORS[category] ?? "tx-2");
    const colorClass = $derived(
        COLOR_CLASSES[colorToken] ?? COLOR_CLASSES["tx-2"],
    );

    const IconComponent = $derived(
        NODE_ICONS[contentType] ?? CATEGORY_ICONS[category] ?? FALLBACK_ICON,
    );
</script>

<svelte:component this={IconComponent} {size} class="{colorClass} shrink-0" />
