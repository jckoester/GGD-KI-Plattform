/**
 * Die Unterbereiche der Bibliothek als Kacheln der Übersicht `/knowledge` (0.48, Päckchen N, G3).
 *
 * Dieselben Bereiche und dieselben Regeln wie in der Seitenleiste: was die Rolle hat, und was
 * die Darstellungsstufe davon zeigt. `seitenleiste_links.test.js` hält beide Listen zusammen.
 * Bis 0.47 lag unter `/knowledge` die Liste aller Bausteine; sie steht jetzt unter
 * `/knowledge/all`.
 */
import { Archive, BookOpen, ChartGantt, Database, FolderHeart, Network, ShieldCheck } from '@lucide/svelte'

/**
 * @param {{ istLehrkraft: boolean, zeigt: (eintrag: string) => boolean }} p
 * @returns {{ href: string, titel: string, text: string, icon: any }[]}
 */
export function bibliothekBereiche({ istLehrkraft, zeigt }) {
    if (!istLehrkraft) return []
    const bereiche = [
        {
            href: '/knowledge/mine',
            titel: 'Meine Bausteine',
            text: 'Was du angelegt hast, mit dem, was Aufmerksamkeit braucht.',
            icon: FolderHeart,
        },
        {
            href: '/knowledge/all',
            titel: 'Alle Bausteine',
            text: 'Der gemeinsame Bestand der Schule: Fachschaftsmaterial, Sammlungen und was Kolleg:innen geteilt haben.',
            icon: Database,
        },
    ]
    if (zeigt('curricula')) {
        // 0.59 (BD): vor den Curricula (Verlaufsplan – Curriculum – Bildungsplan), auf ihrer Darstellungsstufe.
        bereiche.push({
            href: '/knowledge/year-plans',
            titel: 'Jahresverlaufspläne',
            text: 'Wann im Schuljahr was dran ist — je Fach und Klassenstufe, auf dem Kalender der Schule.',
            icon: ChartGantt,
        })
        bereiche.push({
            href: '/knowledge/curricula',
            titel: 'Curricula',
            text: 'Die Schulcurricula der Fachschaften, nach Bildungsplan und Band.',
            icon: BookOpen,
        })
        // BE (0.66): hinter den Curricula, auf ihrer Darstellungsstufe — sie zeigt deren Kapitel.
        bereiche.push({
            href: '/knowledge/connections',
            titel: 'Vernetzung der Fächer',
            text: 'Was in anderen Fächern parallel läuft und worauf ein Kapitel aufbaut — über alle Klassenstufen.',
            icon: Network,
        })
    }
    if (zeigt('education_plans')) {
        bereiche.push(
            {
                href: '/knowledge/education-plans',
                titel: 'Bildungspläne',
                text: 'Die Bildungspläne der Fächer mit ihren Kompetenzen.',
                icon: BookOpen,
            },
            {
                href: '/knowledge/cross-cutting-themes',
                titel: 'Leitperspektiven',
                text: 'Die fächerübergreifenden Leitperspektiven des Bildungsplans.',
                icon: ShieldCheck,
            },
        )
    }
    bereiche.push({
        href: '/knowledge/archive',
        titel: 'Archiv',
        text: 'Archivierte Bausteine zurückholen oder endgültig löschen.',
        icon: Archive,
    })
    return bereiche
}
