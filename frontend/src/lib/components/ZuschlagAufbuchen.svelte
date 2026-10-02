<script>
    // Zuschlag von Hand aufbuchen (0.12, Paket 2, AP1) — für alle, die Budget verwalten.
    //
    // Zwei Wege: eine **Gruppe** (für Schüler:innen der Regelfall) oder eine **einzelne
    // Lehrkraft** über ihre Kennung aus dem Profil. Gebucht wird erst nach der Vorschau,
    // und nur das, was die Vorschau gezeigt hat (siehe `lib/zuschlag.js`, `schluessel`).
    import { onMount } from "svelte";
    import { getZuschlagGruppen, postZuschlag } from "$lib/api.js";
    import {
        anfrage,
        schluessel,
        vorschauText,
        ergebnisText,
        mitgliederVorgabe,
    } from "$lib/zuschlag.js";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import SuccessBanner from "$lib/components/SuccessBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";

    let modus = $state("gruppe");
    let gruppen = $state([]);
    let gruppeId = $state("");
    let mitglieder = $state("schueler");
    let kennungEingabe = $state("");
    let betragEur = $state("");
    let grund = $state("");

    let vorschau = $state(null);
    let vorschauFuer = $state(null); // Schlüssel der geprüften Anfrage
    let ergebnis = $state(null);
    let fehler = $state(null);
    let laeuft = $state(false);

    let aktuell = $derived(
        anfrage({ modus, gruppeId, mitglieder, kennungEingabe, betragEur, grund }),
    );
    // Nur freigeben, solange die Eingaben noch genau die geprüften sind.
    let darfBuchen = $derived(
        vorschau !== null && vorschauFuer === schluessel(aktuell) && !laeuft,
    );

    onMount(async () => {
        try {
            gruppen = await getZuschlagGruppen();
        } catch (e) {
            fehler = e.message ?? "Gruppen konnten nicht geladen werden.";
        }
    });

    function gruppeGewaehlt() {
        const g = gruppen.find((x) => String(x.id) === String(gruppeId));
        if (g) mitglieder = mitgliederVorgabe(g.typ);
    }

    async function pruefen() {
        if (!aktuell) return;
        laeuft = true;
        fehler = null;
        ergebnis = null;
        try {
            vorschau = await postZuschlag({ ...aktuell, probelauf: true });
            vorschauFuer = schluessel(aktuell);
        } catch (e) {
            vorschau = null;
            fehler = e.message ?? "Prüfung fehlgeschlagen.";
        } finally {
            laeuft = false;
        }
    }

    async function buchen() {
        if (!darfBuchen) return;
        laeuft = true;
        fehler = null;
        try {
            ergebnis = await postZuschlag({ ...aktuell, probelauf: false });
            vorschau = null;
            vorschauFuer = null;
        } catch (e) {
            fehler = e.message ?? "Buchung fehlgeschlagen.";
        } finally {
            laeuft = false;
        }
    }

    const feld =
        "w-full px-3 py-2 rounded border border-light-ui-3 dark:border-dark-ui-3 " +
        "bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx text-sm";
</script>

<section class="mt-10 pt-6 border-t border-light-ui-3 dark:border-dark-ui-3">
    <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-1">
        Zuschlag aufbuchen
    </h2>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
        Kommt <strong>obendrauf</strong> — die wöchentliche Aufstockung läuft danach normal
        weiter. Gilt bis zum Ende des Schuljahres. Der Betrag gilt <strong>je Person</strong>.
    </p>

    <div class="flex gap-4 mb-4 text-sm" role="radiogroup" aria-label="Wem aufbuchen?">
        <label class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
            <input type="radio" bind:group={modus} value="gruppe" /> Einer Gruppe
        </label>
        <label class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
            <input type="radio" bind:group={modus} value="person" /> Einer Lehrkraft
        </label>
    </div>

    <div class="grid gap-3 sm:grid-cols-2 mb-3">
        {#if modus === "gruppe"}
            <label class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Gruppe
                <select bind:value={gruppeId} onchange={gruppeGewaehlt} class={feld}>
                    <option value="">— wählen —</option>
                    {#each gruppen as g (g.id)}
                        <option value={g.id}>
                            {g.name} ({g.schueler} S / {g.lehrkraefte} L)
                        </option>
                    {/each}
                </select>
            </label>
            <label class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Wer darin?
                <select bind:value={mitglieder} class={feld}>
                    <option value="schueler">nur Schüler:innen</option>
                    <option value="lehrkraefte">nur Lehrkräfte</option>
                    <option value="alle">alle Mitglieder</option>
                </select>
            </label>
        {:else}
            <label class="text-sm text-light-tx-2 dark:text-dark-tx-2 sm:col-span-2">
                Kennung der Lehrkraft
                <input
                    bind:value={kennungEingabe}
                    placeholder="z. B. a3f9 c2b8 1e04"
                    autocomplete="off"
                    spellcheck="false"
                    class="{feld} font-mono"
                />
                <span class="text-xs">
                    Steht im Profil der Lehrkraft unter „Budget". Die Plattform kennt keine
                    Namen — die Kennung ist der Weg, eine Person zu finden.
                </span>
            </label>
        {/if}
        <label class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Betrag je Person (€)
            <input bind:value={betragEur} inputmode="decimal" placeholder="0,50" class={feld} />
        </label>
        <label class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Grund (steht im Protokoll)
            <input bind:value={grund} placeholder="z. B. Projektwoche" class={feld} />
        </label>
    </div>

    {#if fehler}<ErrorBanner message={fehler} />{/if}

    {#if vorschau}
        <InfoBanner message={vorschauText(vorschau)} />
        {#if vorschauFuer !== schluessel(aktuell)}
            <p class="text-sm text-light-re dark:text-dark-re mt-1">
                Die Eingaben haben sich seit der Prüfung geändert — bitte erneut prüfen.
            </p>
        {/if}
    {/if}

    {#if ergebnis}<SuccessBanner message={ergebnisText(ergebnis)} />{/if}

    <div class="flex gap-3 mt-3">
        <button
            onclick={pruefen}
            disabled={!aktuell || laeuft}
            class="px-4 py-2 rounded border border-light-ui-3 dark:border-dark-ui-3
                   text-light-tx dark:text-dark-tx text-sm
                   disabled:opacity-50 disabled:cursor-not-allowed"
        >
            Prüfen
        </button>
        <button
            onclick={buchen}
            disabled={!darfBuchen}
            class="px-4 py-2 rounded bg-primary dark:bg-primary-dark text-white text-sm
                   disabled:opacity-50 disabled:cursor-not-allowed"
        >
            Jetzt aufbuchen
        </button>
    </div>
</section>
