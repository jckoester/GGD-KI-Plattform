<!--
  Beschriftung eines Kontextknotens: Symbol · Einordnung · Titel · Fassung.

  Bewusst ohne eigenen Rahmen — die Komponente liefert nur die Bestandteile und
  fügt sich in eine Zeile, eine Pille oder eine Auswahlzeile ein. So zeigen die
  drei Stellen, an denen Kontextknoten auftauchen (Chat-Erwähnung, Vorschläge,
  angeheftete Knoten), dieselben Knoten auch gleich an.
-->
<script>
    import NodeTypeIcon from "./NodeTypeIcon.svelte";
    import { subjectMap } from "$lib/stores/subjects.js";
    import { einordnung, kontextknotenAnsicht } from "$lib/context_node_view.js";
    import { renderInlineMath } from "$lib/markdown.js";

    let {
        node,
        fassung = null,
        iconSize = 14,
        titleClass = "truncate",
    } = $props();

    const ansicht = $derived(kontextknotenAnsicht(node));
    const einordnen = $derived(einordnung(ansicht, $subjectMap));
</script>

{#if ansicht.contentType}
    <NodeTypeIcon
        category={ansicht.category}
        contentType={ansicht.contentType}
        size={iconSize}
    />
{/if}

{#if einordnen}
    <span
        class="text-xs text-light-tx-2 dark:text-dark-tx-2 shrink-0"
        title={einordnen.tooltip}
    >
        {einordnen.label}
    </span>
{/if}

<!-- Sichtbar mit gerenderten Formeln; das `title`-Attribut bleibt Rohtext — ein
     Tooltip kann kein Markup tragen. -->
<span class={titleClass} title={ansicht.title}>
    {@html renderInlineMath(ansicht.title)}
</span>

{#if fassung}
    <span
        class="text-xs shrink-0 rounded px-1.5 py-0.5
               border border-light-ui-3 dark:border-dark-ui-3
               text-light-tx-2 dark:text-dark-tx-2"
        title="Bildungsplan-Fassung — dieselbe Nummer kommt in mehreren Fassungen vor"
    >
        {fassung}
    </span>
{/if}
