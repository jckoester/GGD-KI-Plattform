<script>
  import { goto } from '$app/navigation'
  import { getNeighborhood } from '$lib/api.js'
  import { CATEGORY_LABELS } from '$lib/taxonomy.js'
  import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force'

  let {
    nodeId,           // UUID des Startknotens
    initialDepth = 2, // 1 oder 2
  } = $props()

  let depth = $state(initialDepth)
  let loading = $state(false)
  let error = $state(null)
  let hoveredId = $state(null)   // für Tooltip
  let simNodes = $state([])     // { id, x, y, ... } — wird von Simulation befüllt
  let simEdges = $state([])     // { source, target, relation }

  let svgEl = $state(null)

  // Kategorie-Filter (Toggle-Buttons)
  const ALL_CATEGORIES = ['document', 'knowledge', 'artifact', 'concept']
  let selectedCategories = $state(new Set(ALL_CATEGORIES))

  // Größen
  const NODE_RADIUS = 10   // normaler Knoten
  const START_RADIUS = 15   // Startknoten
  const TOOLTIP_DX = 14   // horizontaler Abstand des Labels vom Knoten

  // Farbschemata
  const NODE_COLORS = {
    document:  { bg: '#e0f2fe', border: '#0284c7' },
    knowledge: { bg: '#dcfce7', border: '#16a34a' },
    artifact:  { bg: '#fef9c3', border: '#ca8a04' },
    concept:   { bg: '#ede9fe', border: '#7c3aed' },
    _default:  { bg: '#f1f5f9', border: '#94a3b8' },
  }

  const RELATION_COLORS = {
    requires:     '#ef4444',
    part_of:      '#f97316',
    develops:     '#22c55e',
    supersedes:   '#a855f7',
    used_with:    '#3b82f6',
    references:   '#6b7280',
    related_to:   '#6b7280',
    follows:      '#14b8a6',
    reflects_on:  '#f59e0b',
    derived_from: '#8b5cf6',
  }

  function runSimulation(rawNodes, rawEdges, width, height) {
    // Knoten als mutable Objekte (d3-force schreibt x/y direkt rein)
    const nodes = rawNodes.map(n => ({ ...n, x: width / 2, y: height / 2 }))

    // Kanten brauchen Referenzen auf Knoten-Objekte (nicht nur IDs)
    const nodeById = Object.fromEntries(nodes.map(n => [n.id, n]))
    const links = rawEdges.map(e => ({
      source: nodeById[e.from_node_id],
      target: nodeById[e.to_node_id],
      relation: e.relation,
      id: e.id,
    }))

    const sim = forceSimulation(nodes)
      .force('link',    forceLink(links).id(n => n.id).distance(80).strength(0.5))
      .force('charge',  forceManyBody().strength(-200))
      .force('center',  forceCenter(width / 2, height / 2))
      .force('collide', forceCollide(NODE_RADIUS * 2))

    // Simulation 300 Ticks vorlaufen lassen (synchron, kein Animation-Loop nötig)
    sim.tick(300)
    sim.stop()

    return { nodes, links }
  }

  async function load() {
    if (!nodeId) return
    loading = true
    error = null
    try {
      const data = await getNeighborhood(nodeId, {
        depth,
        category: [...selectedCategories],
      })
      
      // Warte kurz, um sicherzustellen, dass svgEl im DOM ist
      await new Promise(resolve => setTimeout(resolve, 50))
      
      const { width, height } = svgEl.getBoundingClientRect()
      const { nodes, links } = runSimulation(data.nodes, data.edges, width, height)
      simNodes = nodes
      simEdges = links
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  $effect(() => {
    nodeId; depth; selectedCategories
    load()
  })
</script>

<div class="flex flex-col h-full">
  <!-- Kontrollleiste -->
  <div class="flex flex-wrap items-center gap-3 px-4 py-3 flex-shrink-0
              border-b border-light-ui-2 dark:border-dark-ui-2
              bg-light-bg-2 dark:bg-dark-bg-2 text-sm">

    <!-- Tiefe -->
    <div class="flex items-center gap-1">
      <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 font-medium">Tiefe:</span>
      {#each [1, 2] as d}
        <button
          onclick={() => { depth = d }}
          class="px-2.5 py-1 rounded text-xs border transition-colors
                 {depth === d
                   ? 'bg-primary/10 border-primary text-primary font-medium'
                   : 'border-light-ui-3 text-light-tx-2 dark:text-dark-tx-2'}"
        >{d}</button>
      {/each}
    </div>

    <!-- Kategorie-Toggle -->
    <div class="flex items-center gap-1 flex-wrap">
      <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 font-medium">Typen:</span>
      {#each ALL_CATEGORIES as cat}
        {@const colors = NODE_COLORS[cat]}
        <button
          onclick={() => {
            const next = new Set(selectedCategories)
            next.has(cat) ? next.delete(cat) : next.add(cat)
            selectedCategories = next
          }}
          class="flex items-center gap-1 px-2 py-0.5 rounded text-xs border transition-colors
                 {selectedCategories.has(cat)
                   ? 'border-current opacity-100'
                   : 'border-light-ui-3 opacity-40 dark:border-dark-ui-3'}"
          style="color: {colors.border}"
        >
          <span class="w-2 h-2 rounded-full inline-block"
                style="background: {colors.border}"></span>
          {CATEGORY_LABELS[cat]}
        </button>
      {/each}
    </div>

    <!-- Knoten-Zähler -->
    <span class="ml-auto text-xs text-light-tx-2 dark:text-dark-tx-2">
      {simNodes.length} Knoten · {simEdges.length} Kanten
    </span>
  </div>

  <!-- SVG-Canvas -->
  <div class="flex-1 relative overflow-hidden">
    {#if loading}
      <div class="absolute inset-0 flex items-center justify-center z-10
                  bg-light-bg/80 dark:bg-dark-bg/80">
        <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">Wird geladen…</span>
      </div>
    {/if}
    {#if error}
      <div class="absolute inset-0 flex items-center justify-center">
        <p class="text-sm text-light-re dark:text-dark-re">{error}</p>
      </div>
    {:else}
      <svg
        bind:this={svgEl}
        class="w-full h-full"
        onclick={(e) => { if (e.target === svgEl) hoveredId = null }}
      >
        <!-- Kanten (zuerst, damit Knoten darüber liegen) -->
        <g class="edges">
          {#each simEdges as edge (edge.id)}
            {@const color = RELATION_COLORS[edge.relation] ?? '#d1d5db'}
            <line
              x1={edge.source.x} y1={edge.source.y}
              x2={edge.target.x} y2={edge.target.y}
              stroke={color}
              stroke-width="1.5"
              opacity="0.7"
            />
          {/each}
        </g>

        <!-- Knoten -->
        <g class="nodes">
          {#each simNodes as node (node.id)}
            {@const colors = NODE_COLORS[node.category] ?? NODE_COLORS._default}
            {@const isStart = node.id === nodeId}
            {@const r = isStart ? START_RADIUS : NODE_RADIUS}
            <g
              class="cursor-pointer"
              transform="translate({node.x},{node.y})"
              onmouseenter={() => { hoveredId = node.id }}
              onmouseleave={() => { hoveredId = null }}
              onclick={() => goto(`/knowledge/${node.id}`)}
            >
              <circle
                r={r}
                fill={colors.bg}
                stroke={colors.border}
                stroke-width={isStart ? 3 : 1.5}
              />
              <!-- Tooltip: Text nur beim Hovern -->
              {#if hoveredId === node.id}
                <text
                  x={r + TOOLTIP_DX}
                  y="4"
                  font-size="12"
                  fill="currentColor"
                  class="text-light-tx dark:text-dark-tx pointer-events-none"
                  style="text-shadow: 0 1px 2px rgba(255,255,255,0.8);"
                >{node.title}</text>
              {/if}
            </g>
          {/each}
        </g>
      </svg>

      <!-- Legende (Relationstypen) -->
      {#if simEdges.length > 0}
        {@const usedRelations = [...new Set(simEdges.map(e => e.relation))]}
        <div class="absolute bottom-3 left-3 flex flex-wrap gap-x-3 gap-y-1
                    text-xs text-light-tx-2 dark:text-dark-tx-2">
          {#each usedRelations as rel}
            {@const color = RELATION_COLORS[rel] ?? '#d1d5db'}
            <span class="flex items-center gap-1">
              <span class="inline-block w-4 h-0.5 rounded"
                    style="background: {color}"></span>
              {rel}
            </span>
          {/each}
        </div>
      {/if}
    {/if}
  </div>
</div>
