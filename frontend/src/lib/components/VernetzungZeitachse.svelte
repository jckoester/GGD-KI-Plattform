<script>
    /**
     * Die Zeitachse der Vernetzung (BE, Teil A, Schritt 5): Stufen untereinander, das Fach in der
     * Mitte, Spuren daneben, Leitlinien und Leitperspektiven am Rand. Kapitel sind Knöpfe, Linien
     * liegen als SVG darüber. Die Anordnung rechnet `$lib/zeitachse.js`; hier wird nur gezeichnet.
     *
     * Props:
     * - daten: Antwort von `GET /context/vernetzung`
     * - lay: `spalten(...)`, a: `achse(...)`, je: `bloecke(...)`
     * - bezuege: die aktiven Bezüge (Schalter schon angewandt)
     * - kapitelFach: Map Kapitel → Fach
     * - spurIds: Set der Fächer mit Spur
     * - gewaehlt: Kennung des gewählten Kapitels oder null
     * - hover: Kapitel unter dem Mauszeiger oder mit Tastaturfokus — hebt schon vor dem Klick hervor
     * - alle: „alle Linien zeigen“
     * - onwaehle(id | null), ontipp(event, kapitel | null)
     */
    import { ArrowDownUp, ArrowLeftRight, TriangleAlert } from '@lucide/svelte'
    import { fachToenung, ART_SATZ } from '$lib/absprachen.js'
    import {
        STUFENKOPF, ACHSE, anker, artAusSicht, fassungKurz, frueher, klammer, kurve, kurvenEnden,
        lageQuelleText, marken, mitText, mittelY, randmarken, rinnenTiefen, sichtbar, stil, verbunden, wocheY,
        kalenderwoche,
    } from '$lib/zeitachse.js'

    let {
        daten, lay, a, je, bezuege, kapitelFach, spurIds, gewaehlt = null, hover = null, alle = false,
        onwaehle = () => {}, ontipp = () => {},
    } = $props()

    const fachId = $derived(daten.fach.id)
    const fachFarbe = $derived(daten.fach.color)
    const faecherJe = $derived(Object.fromEntries([[daten.fach.id, daten.fach], ...daten.faecher.map((f) => [f.id, f])]))
    const kapitelJe = $derived(new Map(daten.kapitel.map((k) => [k.id, k])))
    const stufenJe = $derived(Object.fromEntries(daten.stufen.map((s) => [s.stufe, s])))
    // Hervorgehoben wird das Kapitel unter dem Zeiger, sonst das gewählte (Jan 28.11.2026)
    const aktiv = $derived(hover ?? gewaehlt)
    const nah = $derived(aktiv ? verbunden(bezuege, aktiv, { bereiche: true }) : null)

    const zeichnen = $derived(sichtbar(bezuege, { gewaehlt: aktiv, alle, bereiche: true, kapitelFach, fachId, spurIds }))
    const linien = $derived.by(() => {
        const eigen = []
        const kurven = []
        for (const b of zeichnen) {
            const xa = anker(je, b.a)
            const xb = anker(je, b.b)
            if (!xa || !xb) continue
            if (kapitelFach.get(b.a) === kapitelFach.get(b.b)) {
                const [f, s] = frueher(je, b.a, b.b) <= 0 ? [xa, xb] : [xb, xa]
                eigen.push({ b, schluessel: `${b.a}|${b.b}`, y1: mittelY(f), y2: mittelY(s) })
            } else {
                const [m, o] = kapitelFach.get(b.a) === fachId ? [xa, xb] : [xb, xa]
                kurven.push({ b, m, o, ...kurvenEnden(m, o) })
            }
        }
        const tiefen = rinnenTiefen(eigen)
        return {
            eigen: eigen.map((k) => ({ ...k, d: klammer(lay.spalten.mitte.x, k.y1, k.y2, tiefen.get(k.schluessel)) })),
            kurven: kurven.map((k) => ({ ...k, d: kurve(k.x1, k.y1, k.x2, k.y2) })),
        }
    })
    const rand = $derived(randmarken(daten.leitlinien, je, lay.spalten))

    function pille(k) {
        if (!aktiv || k.b.typ !== 'absprache') return null
        const mitteId = kapitelFach.get(k.b.a) === fachId ? k.b.a : k.b.b
        const anderId = mitteId === k.b.a ? k.b.b : k.b.a
        const art = artAusSicht(k.b, mitteId)
        const ergebnis = k.b.pruefung?.ergebnis
        const zeichen = ergebnis === 'eingehalten' ? ' ✓' : ergebnis === 'verletzt' ? ' ✗' : ''
        return { text: `${faecherJe[kapitelFach.get(anderId)]?.name ?? ''} ${ART_SATZ[art] ?? art}${zeichen}`,
            verletzt: ergebnis === 'verletzt', x: (k.x1 + k.x2) / 2, y: (k.y1 + k.y2) / 2 }
    }

    function linienKlasse(s) {
        if (s.verletzt) return 'text-light-re dark:text-dark-re'
        return s.strich ? 'text-light-tx-2 dark:text-dark-tx-2' : 'text-light-tx dark:text-dark-tx'
    }

    function blockKlasse(id, mitte, m) {
        if (nah) return nah.has(id) ? '' : 'opacity-35'
        return !mitte && !m.fremd ? 'opacity-45' : ''
    }

    const pfeilId = `pfeil-${Math.random().toString(36).slice(2, 8)}`
</script>

<div class="relative" style="width: {lay.breite}px; height: {a.hoehe}px">
    <!-- Stufen: Kopf, Wochen, Ferien, heute -->
    {#each a.stufen as s (s.stufe)}
        {@const info = stufenJe[s.stufe]}
        <div id="stufe-{s.stufe}" class="absolute left-0 flex flex-wrap items-center content-center gap-x-3 gap-y-0.5 px-3 py-1.5 rounded
                    border-l-4 bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx"
             style="top: {s.oben}px; height: {STUFENKOPF - 8}px; width: {lay.breite}px; border-left-color: {fachFarbe ?? 'currentColor'}">
            <span class="text-base font-bold">Klasse {s.stufe}</span>
            <span class="text-xs text-light-tx dark:text-dark-tx">
                {[info.schuljahr, info.fassung && `Bildungsplan ${fassungKurz(info.fassung)}`, lageQuelleText(info)].filter(Boolean).join(' · ')}
            </span>
        </div>
        <!-- Anmerkungen: je eine Zeile, als Aufzählung im Rahmen unter dem Kopf (Jan 28.11.2026) -->
        {#if s.hinweise.length}
            <ul class="absolute left-0 list-disc pl-7 pr-3 py-0.5 rounded border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg text-xs leading-4 text-light-tx dark:text-dark-tx"
                style="top: {s.oben + STUFENKOPF - 6}px; width: {lay.breite}px"
                aria-label="Anmerkungen zu Klasse {s.stufe}">
                {#each s.hinweise as h (h)}<li>{h}</li>{/each}
            </ul>
        {/if}
        {#each Array.from({ length: Math.ceil(s.wochen / 4) }, (_, i) => 1 + i * 4) as w (w)}
            <div class="absolute text-[10px] text-light-tx-2 dark:text-dark-tx-2 text-right"
                 style="top: {wocheY(a, s.stufe, w) - 6}px; left: 0; width: {ACHSE - 6}px">
                {kalenderwoche(info, w) != null ? `KW ${kalenderwoche(info, w)}` : `Wo. ${w}`}
            </div>
        {/each}
        {#each info.ferien as f (f.nach_woche)}
            <div class="absolute border-t border-dashed border-light-ui-3 dark:border-dark-ui-3"
                 style="top: {wocheY(a, s.stufe, f.nach_woche + 1) - 1}px; left: {ACHSE}px; width: {lay.breite - ACHSE}px">
                <span class="absolute -top-2 text-[10px] italic text-light-tx-2 dark:text-dark-tx-2 bg-light-bg dark:bg-dark-bg px-0.5"
                      style="left: 2px">{f.name}</span>
            </div>
        {/each}
        {#if info.heute_woche}
            <div class="absolute border-t-2 border-light-bl dark:border-dark-bl pointer-events-none z-30"
                 style="top: {wocheY(a, s.stufe, info.heute_woche) + a.px / 2}px; left: {ACHSE}px; width: {lay.breite - ACHSE}px">
                <span class="absolute right-1 -top-4 text-[11px] font-semibold text-light-bl dark:text-dark-bl">heute</span>
            </div>
        {/if}
    {/each}

    <!-- Kapitel -->
    {#each [...je] as [id, liste] (id)}
        {@const k = kapitelJe.get(id)}
        {@const mitte = k.fach_id === fachId}
        {@const m = marken(bezuege, id, kapitelFach, { bereiche: true })}
        {@const fach = faecherJe[k.fach_id]}
        {#each liste as blk, i (i)}
            <button
                type="button"
                id={i === 0 ? `kap-${id}` : undefined}
                class="kapitel absolute z-20 overflow-hidden rounded border text-left px-1.5 py-0.5 text-light-tx dark:text-dark-tx
                       focus:outline-none focus:ring-2 focus:ring-primary transition-opacity
                       {blk.quelle === 'geschaetzt' ? 'border-dashed' : ''}
                       {gewaehlt === id ? 'ring-2 ring-light-tx dark:ring-dark-tx' : ''} {blockKlasse(id, mitte, m)}"
                style="left: {blk.x}px; top: {blk.y}px; width: {blk.b}px; height: {Math.max(blk.h, 8)}px; border-left-width: 4px; {fachToenung(fach?.color)}"
                aria-label="{fach?.name}: {k.titel}{i ? ' (Fortsetzung)' : ''}"
                aria-pressed={gewaehlt === id}
                onclick={() => onwaehle(gewaehlt === id ? null : id)}
                onmouseenter={(e) => ontipp(e, k)}
                onmousemove={(e) => ontipp(e, k)}
                onmouseleave={() => ontipp(null, null)}
                onfocus={(e) => ontipp(e, k)}
                onblur={() => ontipp(null, null)}
            >
                {#if blk.quelle === 'geschaetzt'}<span class="schraffur" aria-hidden="true"></span>{/if}
                {#if (mitte || !lay.schmal) && mitText(blk, a.px)}
                    <span class="relative block font-semibold leading-tight {mitte ? 'text-sm' : 'text-xs'} line-clamp-2">
                        {k.titel}{#if i}<span class="font-normal"> (Forts.)</span>{/if}
                    </span>
                {/if}
                {#if (m.fremd || m.eigen || m.verletzt) && blk.h > 30 && (mitte || !lay.schmal)}
                    <span class="absolute right-1 bottom-0.5 flex gap-1">
                        {#if m.fremd}
                            <span class="marke" title="Bezüge zu anderen Fächern"><ArrowLeftRight class="w-3.5 h-3.5" />{m.fremd}</span>
                        {/if}
                        {#if mitte && m.eigen}
                            <span class="marke" title="Bezüge im eigenen Fach"><ArrowDownUp class="w-3.5 h-3.5" />{m.eigen}</span>
                        {/if}
                        {#if m.verletzt}
                            <span class="marke text-light-re dark:text-dark-re" title="Absprache laut Jahresverlaufsplänen nicht eingehalten">
                                <TriangleAlert class="w-3.5 h-3.5" />
                            </span>
                        {/if}
                    </span>
                {/if}
            </button>
        {/each}
    {/each}

    <!-- Leitlinien und Leitperspektiven -->
    {#each rand as r (`${r.kapitel}-${r.art}-${r.kuerzel}`)}
        <button type="button"
                class="absolute z-20 -translate-y-1/2 flex items-center gap-1 text-[11px] whitespace-nowrap text-light-tx dark:text-dark-tx
                       hover:underline focus:outline-none focus:ring-2 focus:ring-primary rounded
                       {nah && !nah.has(r.kapitel) ? 'opacity-30' : ''}"
                style="left: {r.x}px; top: {r.y}px"
                title="{r.titel}{r.aspekte.length ? ` — ${r.aspekte.join(', ')}` : ''}"
                onclick={() => onwaehle(r.kapitel)}>
            <span class="inline-block w-2.5 h-2.5 border-2 bg-light-bg dark:bg-dark-bg {r.art === 'll' ? 'rotate-45 rounded-[2px]' : 'rounded-full'}"
                  style="border-color: {fachFarbe}"></span>
            {r.kuerzel}
        </button>
    {/each}

    <!-- Linien -->
    <svg class="absolute inset-0 pointer-events-none overflow-visible z-10" width={lay.breite} height={a.hoehe} aria-hidden="true">
        <defs>
            <marker id={pfeilId} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,0 L8,4 L0,8 z" fill={fachFarbe ?? 'currentColor'} />
            </marker>
        </defs>
        {#each linien.eigen as k (k.schluessel)}
            <path d={k.d} fill="none" stroke={fachFarbe ?? 'currentColor'} stroke-width={stil(k.b).breite}
                  opacity={aktiv ? 1 : 0.6} marker-end="url(#{pfeilId})" />
        {/each}
        {#each linien.kurven as k (`${k.b.typ}-${k.b.a}-${k.b.b}`)}
            {@const s = stil(k.b)}
            <path d={k.d} fill="none" class={linienKlasse(s)} stroke="currentColor" stroke-width={s.breite}
                  stroke-dasharray={s.strich ?? undefined} opacity={aktiv ? 1 : 0.55} />
        {/each}
    </svg>
    {#each linien.kurven as k (`p-${k.b.typ}-${k.b.a}-${k.b.b}`)}
        {@const p = pille(k)}
        {#if p}
            <span class="absolute z-30 -translate-x-1/2 -translate-y-1/2 pointer-events-none whitespace-nowrap rounded-full border px-1.5
                         text-[11px] bg-light-bg dark:bg-dark-bg
                         {p.verletzt ? 'border-light-re dark:border-dark-re text-light-re dark:text-dark-re font-semibold'
                                     : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx'}"
                  style="left: {p.x}px; top: {p.y}px">{p.text}</span>
        {/if}
    {/each}
</div>

<style>
    .schraffur {
        position: absolute;
        inset: 0;
        pointer-events: none;
        background: repeating-linear-gradient(135deg, transparent 0 6px, rgb(0 0 0 / 0.07) 6px 9px);
    }
    :global(.dark) .schraffur {
        background: repeating-linear-gradient(135deg, transparent 0 6px, rgb(255 255 255 / 0.09) 6px 9px);
    }
    .marke {
        display: inline-flex;
        align-items: center;
        gap: 2px;
        font-size: 11px;
        line-height: 1;
        padding: 1px 4px;
        border-radius: 4px;
        border: 1px solid var(--color-light-ui-3);
        background: var(--color-light-bg);
    }
    :global(.dark) .marke {
        border-color: var(--color-dark-ui-3);
        background: var(--color-dark-bg);
    }
</style>
