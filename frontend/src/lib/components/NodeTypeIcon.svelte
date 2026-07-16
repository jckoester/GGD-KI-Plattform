<script>
    import { CATEGORY_COLORS } from "$lib/taxonomy.js";
    import {
        Target,
        ClipboardList,
        Layers,
        Cpu,
        Lightbulb,
        FileText,
        BookOpen,
        Package,
        Circle,
        Users,
        Presentation,
        Zap,
    } from "lucide-svelte";

    let { category, contentType = undefined, size = 16 } = $props();

    // Icon-Mapping für content_types
    const CONTENT_TYPE_ICON_MAP = {
        lernziel: Target,
        aufgabe: ClipboardList,
        themengebiet: Layers,
        bauteil: Cpu,
        abstrakt: Lightbulb,
        methode: Presentation,
        sozialform: Users,
        operator: Zap,
        lfdb_baustein: Layers,
        lfdb_themenblock: BookOpen,
        lfdb_kompetenz: Target,
    };

    // Fallback-Mapping für categories
    const CATEGORY_FALLBACK = {
        document: FileText,
        knowledge: BookOpen,
        artifact: Package,
        concept: Lightbulb,
    };

    // Statische Klassen-Map — alle Strings müssen literal im Quelltext stehen damit Tailwind sie nicht purgt
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
        contentType && CONTENT_TYPE_ICON_MAP[contentType]
            ? CONTENT_TYPE_ICON_MAP[contentType]
            : CATEGORY_FALLBACK[category]
              ? CATEGORY_FALLBACK[category]
              : Circle,
    );
</script>

<svelte:component this={IconComponent} {size} class="{colorClass} shrink-0" />
