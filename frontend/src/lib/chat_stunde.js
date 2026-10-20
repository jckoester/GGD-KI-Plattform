// Die Bezugsstunde einer Konversation im Kopf des Chats (0.19, Schritt 2).
//
// Das Backend liefert sie als `stunde` — beim Öffnen der Konversation und im Ereignis
// `bezug` (`bezug_fuer_anzeige` in `planning/stundenbezug.py`). Ohne Lesezugang oder für
// eine gelöschte Stunde kommt `null`, dann gibt es keinen Link.

const WOCHENTAGE = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];

/** Der Pfad zur Entwurfsansicht — oder null, wenn ein Teil fehlt. */
export function stundenPfad(stunde) {
  if (!stunde?.stunde_node_id || !stunde?.group_id || !stunde?.fach_slug) return null;
  return `/subjects/${encodeURIComponent(stunde.fach_slug)}/groups/${stunde.group_id}/planner/lessons/${stunde.stunde_node_id}`;
}

/** „Di 14.10." aus `2026-10-14` — oder "" ohne Termin. */
export function stundenDatum(datum) {
  if (!datum) return "";
  const [j, m, t] = datum.split("-").map(Number);
  if (!j || !m || !t) return "";
  const tag = new Date(j, m - 1, t);
  return `${WOCHENTAGE[tag.getDay()]} ${t}.${m}.`;
}

/** Die Beschriftung des Links: „Titel · Di 14.10." */
export function stundenText(stunde) {
  const datum = stundenDatum(stunde?.datum);
  return [stunde?.titel || "Stunde", datum].filter(Boolean).join(" · ");
}
