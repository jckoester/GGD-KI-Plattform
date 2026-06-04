/**
 * Adapter-Funktionen für den Curriculum-Import
 * KS-Phase-6 Schritt 5a
 */

/**
 * Konvertiert ein CurriculumDraft-Objekt (YAML-Zwischenformat vom Backend)
 * in ein CurriculumRead-ähnliches Objekt für die Vorschau in CurriculumTable.
 * 
 * @param {Object} draft - Das Draft-Objekt vom Backend (CurriculumDraft)
 * @returns {Object} CurriculumRead-ähnliches Objekt mit synthetischen IDs
 */
export function draftToPreview(draft) {
    const data = draft.data;
    return {
        id: null,
        title: `${data.fach} ${data.schulart} Kl. ${data.jahrgangsstufe}`,
        metadata: {
            schule: data.schule,
            schulart: data.schulart,
            bp_version: data.bp_version,
            jahrgangsstufe: data.jahrgangsstufe,
        },
        kapitel: (data.kapitel ?? []).map((kap, ki) => ({
            id: `preview-kap-${ki}`,
            title: kap.titel,
            metadata: { std: kap.std, einleitung: kap.hinweis },
            lernsequenzen: (kap.lernsequenzen ?? []).map((ls, li) => ({
                id: `preview-ls-${ki}-${li}`,
                title: ls.bp_titel ?? '',
                metadata: {
                    bp_leitidee: ls.bp_leitidee,
                    eintraege: ls.eintraege ?? [],
                },
                ik_refs: ls.eintraege?.flatMap(e =>
                    (e.ik_resolved ?? []).map(ik => ({
                        node_id: ik.node_id,
                        title: ik.nr,
                        partiell: ik.partiell ?? false,
                    }))
                ) ?? [],
                pk_refs: ls.eintraege?.flatMap(e =>
                    (e.pk_resolved ?? []).map(pk => ({
                        node_id: pk.node_id,
                        title: pk.id,
                    }))
                ) ?? [],
            }))
        }))
    };
}
