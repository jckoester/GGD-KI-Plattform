// Valide content_types pro category
export const CONTENT_TYPES = {
  document: [
    'formatierungsvorlage', 'vokabelliste', 'aufgabenblatt', 'quelltext',
    'konvention', 'methodenblatt', 'operatorenblatt', 'praesentation',
  ],
  knowledge: [
    'fachplan', 'themengebiet', 'leitidee', 'ik_kompetenz', 'pk_gruppe',
    'pk_kompetenz', 'leitperspektive', 'leitperspektive_aspekt', 'curriculum',
    'unterrichtseinheit', 'methode', 'operator_didaktisch', 'jahresplan',
    'pruefungsanforderung',
  ],
  artifact: [
    'unterrichtsentwurf', 'unterrichtsstunde', 'reflexion', 'arbeitsblatt',
    'aufgabe', 'klausur', 'code_beispiel', 'lerntext', 'gliederung',
    'mindmap', 'lernplan', 'schuelertext', 'feedback_text',
  ],
  concept: ['funktion', 'bauteil', 'operator_math', 'abstrakt'],
}

// content_types, die als retrieval_scope-Anker zulässig sind (= Einstiegsknoten).
// Muss identisch mit VALID_SCOPE_ANCHOR_TYPES in backend/app/context/retrieval.py sein.
export const SCOPE_ANCHOR_CONTENT_TYPES = new Set([
  'fachplan', 'leitidee', 'pk_gruppe', 'curriculum',
  'themengebiet', 'unterrichtseinheit', 'unterrichtsstunde',
])

// Deutsche Labels für categories
export const CATEGORY_LABELS = {
  document: 'Dokument',
  knowledge: 'Wissen',
  artifact: 'Artefakt',
  concept: 'Konzept',
}

// Farb-Tokens für Kategorien
export const CATEGORY_COLORS = {
  document: 'bl',
  knowledge: 'gr',
  artifact: 'or',
  concept: 'pu',
}

// Lesbare Labels für content_types (Auswahl der häufigsten)
export const CONTENT_TYPE_LABELS = {
  fachplan: 'Fachplan', themengebiet: 'Themengebiet', leitidee: 'Leitidee',
  curriculum: 'Schulcurriculum', unterrichtseinheit: 'Unterrichtseinheit',
  unterrichtsstunde: 'Unterrichtsstunde',
  arbeitsblatt: 'Arbeitsblatt', aufgabe: 'Aufgabe', konvention: 'Konvention',
  funktion: 'Funktion', bauteil: 'Bauteil', abstrakt: 'Abstraktes Konzept',
  code_beispiel: 'Code-Beispiel',
  // Fallback: content_type direkt anzeigen
}

// Scope-Defaults pro content_type: [read_scope, write_scope]
export const SCOPE_DEFAULTS = {
  fachplan:              ['global',  'global' ],
  leitidee:              ['global',  'global' ],
  themengebiet:          ['school',  'school' ],
  curriculum:            ['school',  'subject'], 
  unterrichtseinheit:    ['school',  'subject'], 
  methode:               ['school',  'subject'], 
  operator_didaktisch:   ['school',  'subject'], 
  jahresplan:            ['private', 'private'],
  pruefungsanforderung:  ['school',  'school' ],
  formatierungsvorlage:  ['school',  'school' ],
  konvention:            ['school',  'school' ],
  methodenblatt:         ['school',  'subject'],
  operatorenblatt:       ['school',  'subject'],
  praesentation:         ['school',  'subject'],
  aufgabenblatt:         ['group',   'private'],
  vokabelliste:          ['group',   'private'],
  quelltext:             ['group',   'private'],
  unterrichtsentwurf:    ['private', 'private'],
  unterrichtsstunde:     ['private', 'private'],
  reflexion:             ['private', 'private'],
  arbeitsblatt:          ['group',   'private'],
  aufgabe:               ['group',   'private'],
  klausur:               ['private', 'private'],
  code_beispiel:         ['school',  'private'],
  lerntext:              ['school',  'private'],
  gliederung:            ['private', 'private'],
  mindmap:               ['private', 'private'],
  lernplan:              ['private', 'private'],
  schuelertext:          ['private', 'private'],
  feedback_text:         ['private', 'private'],
  funktion:              ['school',  'school' ],
  bauteil:               ['school',  'school' ],
  operator_math:         ['school',  'school' ],
  abstrakt:              ['school',  'school' ],
}
