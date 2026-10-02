<script>
    // Ist gegen Soll — Verbrauch und Zusage der Schule, Woche für Woche (0.12, AP2).
    //
    // Farben: Ist = Blau (durchgezogen), Soll = Orange (gestuft, gestrichelt). Mit
    // `validate_palette.js` geprüft, hell gegen base-100 und dunkel gegen black —
    // ΔE 21,8 bzw. 20,4 bei Farbfehlsichtigkeit. Blau + Grau (der erste Versuch) fiel
    // durch: ΔE 13,9 schon bei normalem Sehen. Rot und Grün bleiben dem Status
    // vorbehalten; Warnung ist hier Gelb, Orange eine Akzentfarbe.
    //
    // Die Strichelung ist die zweite Kodierung neben der Farbe — wer die Farben nicht
    // trennen kann, trennt die Linien trotzdem.
    import { onMount, onDestroy } from "svelte";
    import { reihen, euro, tabellenZeilen } from "$lib/budgetverlauf.js";
    import { token, beobachteModus } from "$lib/diagrammfarben.js";

    let { verlauf = [] } = $props();

    let leinwand = $state(null);
    let diagramm = null;
    let abmelden = null;

    let daten = $derived(reihen(verlauf));
    let zeilen = $derived(tabellenZeilen(verlauf));
    let letzterIst = $derived([...verlauf].reverse().find((p) => p.ist_eur !== null));
    let zusage = $derived(verlauf.length ? verlauf[verlauf.length - 1].soll_eur : null);

    function farben() {
        return {
            ist: token("verbrauch"),
            soll: token("zusage"),
            text2: token("text"),
            gitter: token("gitter"),
            flaeche: token("flaeche"),
        };
    }

    // Senkrechte Haarlinie am aktiven Punkt: Man zielt auf ein Datum, nicht auf eine
    // 2-px-Linie.
    const fadenkreuz = {
        id: "fadenkreuz",
        afterDatasetsDraw(chart) {
            const aktiv = chart.tooltip?.getActiveElements?.() ?? [];
            if (!aktiv.length) return;
            const x = aktiv[0].element.x;
            const { top, bottom } = chart.chartArea;
            const ctx = chart.ctx;
            ctx.save();
            ctx.strokeStyle = chart.options.plugins.fadenkreuz.farbe;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(x, top);
            ctx.lineTo(x, bottom);
            ctx.stroke();
            ctx.restore();
        },
    };

    // Name der Reihe am Linienende — Textfarbe, nicht Reihenfarbe; die Linie daneben
    // trägt die Zuordnung.
    const endbeschriftung = {
        id: "endbeschriftung",
        afterDatasetsDraw(chart) {
            const ctx = chart.ctx;
            ctx.save();
            ctx.font = "12px system-ui, sans-serif";
            ctx.fillStyle = chart.options.plugins.endbeschriftung.farbe;
            ctx.textBaseline = "middle";
            chart.data.datasets.forEach((ds, i) => {
                const meta = chart.getDatasetMeta(i);
                let letzter = -1;
                ds.data.forEach((v, j) => { if (v !== null && v !== undefined) letzter = j; });
                if (letzter < 0) return;
                const punkt = meta.data[letzter];
                ctx.fillText(ds.label, punkt.x + 6, punkt.y);
            });
            ctx.restore();
        },
    };

    function konfiguration(f) {
        return {
            type: "line",
            data: {
                labels: daten.labels,
                datasets: [
                    {
                        label: "Ist",
                        data: daten.ist,
                        borderColor: f.ist,
                        backgroundColor: f.ist,
                        borderWidth: 2,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHoverBorderWidth: 2,
                        pointHoverBorderColor: f.flaeche,
                        borderCapStyle: "round",
                        borderJoinStyle: "round",
                        spanGaps: false,
                    },
                    {
                        label: "Soll",
                        data: daten.soll,
                        borderColor: f.soll,
                        backgroundColor: f.soll,
                        borderWidth: 2,
                        borderDash: [6, 4],
                        stepped: "after",
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHoverBorderWidth: 2,
                        pointHoverBorderColor: f.flaeche,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                // Rechts Platz für die Endbeschriftung.
                layout: { padding: { right: 36 } },
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: {
                        labels: { color: f.text2, usePointStyle: true, pointStyle: "line" },
                    },
                    tooltip: {
                        callbacks: {
                            // Wert vorn, Name dahinter.
                            label: (c) => `${euro(c.parsed.y)}  ${c.dataset.label}`,
                        },
                    },
                    fadenkreuz: { farbe: f.text2 },
                    endbeschriftung: { farbe: f.text2 },
                },
                scales: {
                    x: {
                        grid: { color: f.gitter, lineWidth: 1 },
                        ticks: { color: f.text2, maxRotation: 0, autoSkipPadding: 16 },
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: f.gitter, lineWidth: 1 },
                        ticks: { color: f.text2, callback: (v) => euro(v) },
                    },
                },
            },
            plugins: [fadenkreuz, endbeschriftung],
        };
    }

    let Diagramm = null;

    function zeichnen() {
        if (!Diagramm || !leinwand) return;
        diagramm?.destroy();
        diagramm = new Diagramm(leinwand, konfiguration(farben()));
    }

    onMount(async () => {
        const { Chart, registerables } = await import("chart.js");
        Chart.register(...registerables);
        Diagramm = Chart;
        zeichnen();
        // Dunkelmodus ist eigens gewählt, keine Umkehrung: beim Umschalten neu zeichnen.
        abmelden = beobachteModus(zeichnen);
    });

    $effect(() => {
        // Neue Daten → neu zeichnen.
        void daten;
        zeichnen();
    });

    onDestroy(() => {
        abmelden?.();
        diagramm?.destroy();
    });
</script>

<!-- Dieselbe Karte wie die Hochrechnung darüber: Diagramme liegen auf der erhöhten
     Fläche (`bg-2`), nicht auf der Seite — vorher lag es im Dunkelmodus schwarz unter
     einer grauen Karte (Jan, 02.10.2026). -->
<div
    class="mt-4 rounded border border-light-ui-3 dark:border-dark-ui-3
           bg-light-bg-2 dark:bg-dark-bg-2 px-4 py-3"
>
    <h2 class="text-sm font-semibold text-light-tx dark:text-dark-tx mb-1">
        Verbrauch gegen Zusage
    </h2>
    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mb-2">
        Die Zusage (Soll) wächst nur in Unterrichtswochen — in den Ferien bleibt sie flach.
        Beide Linien summieren seit Schuljahresbeginn.
    </p>
    <div
        class="relative h-64"
        role="img"
        aria-label="Verbrauch gegen Zusage seit Schuljahresbeginn: bisher {euro(
            letzterIst?.ist_eur,
        )} verbraucht, Zusage fürs ganze Jahr {euro(zusage)}. Werte in der Tabelle darunter."
    >
        <canvas bind:this={leinwand} aria-hidden="true"></canvas>
    </div>
    <details class="mt-2 text-xs text-light-tx-2 dark:text-dark-tx-2">
        <summary class="cursor-pointer">Als Tabelle</summary>
        <table class="mt-2 w-full">
            <thead>
                <tr class="text-left">
                    <th class="pr-4 font-medium">Woche ab</th>
                    <th class="pr-4 font-medium text-right">Soll</th>
                    <th class="pr-4 font-medium text-right">Ist</th>
                    <th class="font-medium"></th>
                </tr>
            </thead>
            <tbody>
                {#each zeilen as z (z.woche)}
                    <tr>
                        <td class="pr-4">{z.woche}</td>
                        <td class="pr-4 text-right tabular-nums">{z.soll}</td>
                        <td class="pr-4 text-right tabular-nums">{z.ist}</td>
                        <td>{z.ferien ? "Ferien" : ""}</td>
                    </tr>
                {/each}
            </tbody>
        </table>
    </details>
</div>
