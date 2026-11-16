<script>
    // „Mit dem Assistenten bearbeiten" (0.46, E18): öffnet den Chat mit Curriculumbezug. Nur für
    // Entwürfe — in ein veröffentlichtes Curriculum schreibt der Assistent nicht (E17). Ohne
    // passenden Assistenten öffnet der Chat trotzdem und sagt, dass keiner eingerichtet ist.
    import { goto } from "$app/navigation";
    import { getAssistants } from "$lib/api.js";
    import { neuerChatPfad } from "$lib/chatziel.js";
    import { passendeAssistenten } from "$lib/assistentenwahl.js";
    import { user } from "$lib/stores/user.js";
    import AssistentenKnopf from "$lib/components/AssistentenKnopf.svelte";

    let { curriculum, gesperrt = false } = $props();

    let assistenten = $state([]);
    $effect(() => {
        getAssistants().then((d) => { assistenten = d.items ?? []; }).catch(() => {});
    });
    const kandidaten = $derived(
        passendeAssistenten(assistenten, "curriculum_planning", {
            pseudonym: $user?.pseudonym ?? null,
            fachId: curriculum?.subject_id ?? null,
        }),
    );

    function oeffne(assistent) {
        goto(neuerChatPfad({
            subjectId: curriculum?.subject_id ?? null,
            curriculumId: curriculum.id,
            assistantId: assistent?.id ?? null,
        }));
    }
</script>

<span title={gesperrt ? "Erst speichern oder abbrechen" : "Mit dem Assistenten bearbeiten"}>
    <AssistentenKnopf {kandidaten} onwaehle={oeffne} beschaeftigt={gesperrt} />
</span>
