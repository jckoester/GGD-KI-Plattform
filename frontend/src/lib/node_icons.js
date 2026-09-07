// GENERIERT aus backend/app/context/taxonomy.yaml — nicht von Hand ändern.
// Neu erzeugen: python scripts/generate_taxonomy.py
//
// Ein eigenes Symbol je Knotentyp: Die Form unterscheidet den Typ, die Farbe
// die Kategorie (`CATEGORY_COLORS` in taxonomy.js). Gepflegt wird das Symbol
// am Typ in der Taxonomie, nicht hier.

import {
    Album,
    Beaker,
    BookMarked,
    BookOpen,
    BookText,
    Boxes,
    Braces,
    CalendarRange,
    Circle,
    ClipboardCheck,
    ClipboardList,
    Compass,
    Cpu,
    FileCode,
    FileSignature,
    FileText,
    FileType,
    GraduationCap,
    Languages,
    Layers,
    LayoutTemplate,
    Library,
    Lightbulb,
    ListChecks,
    Map,
    MessageSquareQuote,
    Network,
    NotebookPen,
    Package,
    PencilRuler,
    Presentation,
    ScrollText,
    ShieldCheck,
    Sparkles,
    SquareChartGantt,
    Target,
    Users,
    Waypoints,
    Zap,
} from 'lucide-svelte'

/** content_type → Symbol. Vollständig über alle Typen der Taxonomie. */
export const NODE_ICONS = {
    formatierungsvorlage: LayoutTemplate,
    vokabelliste: Languages,
    quelltext: FileCode,
    konvention: FileSignature,
    methodenblatt: ScrollText,
    operatorenblatt: Zap,
    praesentation: Presentation,
    fachplan: Compass,
    themengebiet: Layers,
    leitidee: Lightbulb,
    ik_kompetenz: Target,
    pk_gruppe: Boxes,
    pk_kompetenz: Target,
    leitperspektive: ShieldCheck,
    leitperspektive_aspekt: ShieldCheck,
    lfdb_baustein: Package,
    lfdb_themenblock: BookOpen,
    lfdb_kompetenz: Target,
    curriculum: Library,
    kapitel: BookText,
    lernsequenz: Waypoints,
    methode: Sparkles,
    sozialform: Users,
    operator: Zap,
    jahresplan: CalendarRange,
    pruefungsanforderung: ClipboardCheck,
    unterrichtsstunde: SquareChartGantt,
    unterrichtseinheit: Map,
    arbeitsblatt: PencilRuler,
    aufgabe: ClipboardList,
    klausur: GraduationCap,
    code_beispiel: Braces,
    lerntext: FileText,
    lernplan: ListChecks,
    schuelertext: NotebookPen,
    schuelerpraesentation: Album,
    strukturierung: Network,
    feedback_text: MessageSquareQuote,
    funktion: Braces,
    bauteil: Cpu,
    begriff: BookMarked,
}

/** Rückfall je Kategorie — greift nur, wenn ein Knoten keinen content_type hat. */
export const CATEGORY_ICONS = {
    document: FileType,
    knowledge: BookOpen,
    artifact: Package,
    concept: Beaker,
}

/** Letzter Rückfall, wenn auch die Kategorie fehlt. */
export const FALLBACK_ICON = Circle
