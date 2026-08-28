<script>
    import { onMount } from "svelte";
    import {
        getModelMatrix,
        saveModelMatrix,
        getImageModelMatrix,
        saveImageModelMatrix,
        getAssistantModelCheck,
        getImageKinds,
    } from "$lib/api.js";
    import { CloudCog } from "lucide-svelte";
    import ModelMatrixTable from "$lib/components/ModelMatrixTable.svelte";
    import WarningBanner from "$lib/components/WarningBanner.svelte";
    import InfoBanner from "$lib/components/InfoBanner.svelte";

    // Assistenten, die auf ein nicht mehr vorhandenes Modell verweisen (Schritt 11).
    // Gerade hier relevant: Wer die Modell-Konfiguration ändert, verursacht das Problem.
    let orphaned = $state([]);

    // Drift zwischen config/image_models.yaml und der LiteLLM-Config. Beide Richtungen
    // sind still: Eine Bildart auf ein unbekanntes Modell scheitert erst im Gespräch,
    // ein Bildmodell ohne Bildart ist freischaltbar, aber von niemandem nutzbar.
    let bildarten = $state([]);
    let bildModelleImProxy = $state(null); // null = nicht ermittelt → nichts behaupten

    let bildartenOhneModell = $derived(
        bildModelleImProxy === null
            ? []
            : bildarten.filter((b) => !bildModelleImProxy.includes(b.modell)),
    );
    let modelleOhneBildart = $derived(
        bildModelleImProxy === null
            ? []
            : bildModelleImProxy.filter(
                  (m) => !bildarten.some((b) => b.modell === m),
              ),
    );

    onMount(async () => {
        try {
            const result = await getAssistantModelCheck();
            // `checked: false` = Proxy nicht erreichbar → nichts behaupten.
            if (result.checked) orphaned = result.orphaned;
        } catch {
            // Nur ein Zusatzhinweis — die Matrix bleibt ohne ihn benutzbar.
        }

        try {
            const [kinds, matrix] = await Promise.all([
                getImageKinds(),
                getImageModelMatrix(),
            ]);
            bildarten = kinds.bildarten ?? [];
            bildModelleImProxy = matrix.models ?? [];
        } catch {
            bildModelleImProxy = null; // ungeprüft, nicht „alles in Ordnung"
        }
    });
</script>

<div class="p-6 space-y-10">
    <!-- Kopfzeile -->
    <div class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
        <CloudCog />
        <h1 class="text-2xl font-bold">Modell-Freischaltung</h1>
    </div>

    {#if orphaned.length > 0}
        <WarningBanner
            message={`${orphaned.length === 1 ? "Ein Assistent ist" : `${orphaned.length} Assistenten sind`} an ein Modell gebunden, das hier nicht mehr auftaucht: ${orphaned.map((o) => `„${o.name}" (${o.model})`).join(", ")}. Solche Assistenten schlagen beim Chatten fehl — unter „Assistenten verwalten" ein verfügbares Modell wählen oder das Feld leeren (schulweiter Standard).`}
        />
    {/if}

    <!-- Chat-Modelle -->
    <ModelMatrixTable
        title="Chat-Modelle"
        modelLabel="Modell"
        getMatrix={getModelMatrix}
        saveMatrix={saveModelMatrix}
    >
        {#snippet intro()}
            Hier kannst du die Modelle für Lehrkräfte und Schüler:innen
            freischalten. Die Modelle selbst müssen in LiteLLM konfiguriert sein,
            damit sie in dieser Auflistung auftreten. Die Freigabe betrifft nur die
            Chatfunktion, Assistenten können unabhängig von den hier getroffenen
            Einstellung auch andere Modelle nutzen.
        {/snippet}
    </ModelMatrixTable>

    <!-- Bild-Modelle (Bildgenerierung) -->
    <ModelMatrixTable
        title="Bild-Modelle"
        modelLabel="Bild-Modell"
        getMatrix={getImageModelMatrix}
        saveMatrix={saveImageModelMatrix}
        emptyMessage="Es sind keine Bild-Modelle konfiguriert. Trage ein Bild-Modell mit model_info.mode: image_generation in die LiteLLM-Config ein, damit es hier zur Freischaltung erscheint."
    >
        {#snippet intro()}
            Hier schaltest du die <strong>Bildgenerierungs-Modelle</strong> frei.
            Sie müssen in LiteLLM mit
            <code>model_info.mode: image_generation</code> konfiguriert sein. Damit
            im Chat tatsächlich Bilder erzeugt werden, muss zusätzlich ein Assistent
            die Fähigkeit <strong>Bildgenerierung</strong> haben.
        {/snippet}
    </ModelMatrixTable>

    {#if bildartenOhneModell.length > 0}
        <WarningBanner
            message={`${bildartenOhneModell.length === 1 ? "Eine Bildart verweist" : `${bildartenOhneModell.length} Bildarten verweisen`} auf ein Modell, das der Proxy nicht kennt: ${bildartenOhneModell.map((b) => `„${b.label}" (${b.modell})`).join(", ")}. Sie lassen sich nicht freischalten und scheitern im Chat. Entweder das Modell in die LiteLLM-Config eintragen oder den Namen in config/image_models.yaml korrigieren.`}
        />
    {/if}

    {#if modelleOhneBildart.length > 0}
        <InfoBanner
            message={`Ohne Bildart: ${modelleOhneBildart.join(", ")}. ${modelleOhneBildart.length === 1 ? "Dieses Modell lässt sich" : "Diese Modelle lassen sich"} zwar freischalten, aber kein Assistent kann ${modelleOhneBildart.length === 1 ? "es" : "sie"} nutzen — dafür fehlt ein Eintrag in config/image_models.yaml.`}
        />
    {/if}
</div>
