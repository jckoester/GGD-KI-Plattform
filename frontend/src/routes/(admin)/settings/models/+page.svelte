<script>
    import {
        getModelMatrix,
        saveModelMatrix,
        getImageModelMatrix,
        saveImageModelMatrix,
    } from "$lib/api.js";
    import { CloudCog } from "lucide-svelte";
    import ModelMatrixTable from "$lib/components/ModelMatrixTable.svelte";
</script>

<div class="p-6 space-y-10">
    <!-- Kopfzeile -->
    <div class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
        <CloudCog />
        <h1 class="text-2xl font-bold">Modell-Freischaltung</h1>
    </div>

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
            die Werkzeug-Gruppe <strong>Bildgenerierung</strong> führen.
        {/snippet}
    </ModelMatrixTable>
</div>
