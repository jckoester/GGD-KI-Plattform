// Vorschaumodus (0.29, ADR-016, Ansatz C): die App als Schüler:in sehen und ausprobieren.
//
// Das Backend stellt dafür ein Token mit der Rolle `student` aus; `/auth/me` liefert dann
// `roles: ["student"]` und das Merkmal `vorschau`. Der Store `user` zeigt die Rollen aus dem
// Token — Seitenleiste, Darstellungsstufen und jede `roles.includes`-Abfrage folgen also
// ohne eigene Änderung. Hier stehen nur die Regeln für Band, Dialog und Rückweg, als Modul,
// damit sie sich prüfen lassen.

import { STUDENT_GRADES } from "./grades.js";

/** Schlüssel in `sessionStorage` für den Hinweis nach dem Rückweg. */
export const HINWEIS_SCHLUESSEL = "vorschau_hinweis";

/** Darf diese Person die Vorschau betreten? Lehrkräfte und Admins, nicht aus einer Vorschau. */
export function kannVorschauBetreten(user) {
  if (!user || user.vorschau) return false;
  return (user.roles ?? []).some((r) => r === "teacher" || r === "admin");
}

/** Ganze Minuten bis zum Ablauf, aufgerundet, nie negativ. `ablauf` in Unix-Sekunden. */
export function restMinuten(ablauf, jetztMs = Date.now()) {
  if (!Number.isFinite(ablauf)) return null;
  return Math.max(0, Math.ceil((ablauf * 1000 - jetztMs) / 60000));
}

/** Der Satz im Band. */
export function bandText(vorschau, gruppenName = null) {
  if (!vorschau) return "";
  const teile = [`Klasse ${vorschau.jahrgang}`];
  if (gruppenName) teile.push(`Gruppe ${gruppenName}`);
  return `Du siehst die App als Schüler:in — ${teile.join(", ")}`;
}

/**
 * Jahrgang, mit dem die Vorschau aus dem Editor beginnt: die unterste Stufe des Assistenten,
 * sofern es sie an der Schule gibt — sonst die erste, die in seinen Bereich fällt, sonst die
 * erste der Schule. So sieht die Lehrkraft den Assistenten, statt eine leere Liste.
 */
export function jahrgangFuerAssistent(assistent, stufen = STUDENT_GRADES) {
  const unten = assistent?.min_grade ?? null;
  const oben = assistent?.max_grade ?? null;
  const passend = stufen.find((s) => (unten == null || s >= unten) && (oben == null || s <= oben));
  return passend ?? stufen[0];
}

/** Gruppen, die der Dialog anbietet (F3): Unterrichtsgruppen des laufenden Schuljahres. */
export function vorschauGruppen(gruppen) {
  return (gruppen ?? []).filter((g) => g.type === "teaching_group" && g.aktuell !== false);
}

/** Wohin es nach dem Eintritt geht: direkt in den Chat mit dem Assistenten, sonst zur Startseite. */
export function zielNachEintritt(assistentId) {
  return assistentId != null ? `/chat?assistant_id=${assistentId}` : "/welcome";
}

/** Der Hinweis nach dem Rückweg. */
export function hinweisText(grund) {
  if (grund === "abgelaufen") {
    return "Die Vorschau ist nach einer Stunde abgelaufen. Du siehst die App wieder als Lehrkraft.";
  }
  if (grund === "beendet") return "Vorschau beendet. Du siehst die App wieder als Lehrkraft.";
  return null;
}
