/**
 * Was eine Lehrkraft mit ihrem eigenen Assistenten tun darf — das Spiegelbild der Matrix in
 * `app/api/assistants.py` (`tests/unit/test_assistant_lebenszyklus.py`):
 *
 * | | privat · Gruppe · Fachschaft | schulweit |
 * |---|---|---|
 * | Löschen | jederzeit | Entwurf/eingereicht selbst, sonst Antrag |
 *
 * ⚠️ **`SCHOOLWIDE_SCOPES` gibt es ein zweites Mal im Backend.** Laufen die beiden auseinander,
 * bietet die Oberfläche an, was der Server mit 409 ablehnt. Ein Wächter hält sie zusammen
 * (`test_frontend_kennt_dieselben_schulweiten_reichweiten`).
 */
export const SCHOOLWIDE_SCOPES = new Set(["teachers", "grade", "all_students", "all"]);

/** Reichweiten, mit denen ein Assistent geteilt ist — wer ihn dort nutzt, verliert ihn beim Löschen. */
export const GETEILT_SCOPES = new Set(["subject_department", "activity_group", "teaching_group"]);

/**
 * Warum sich ein eigener Assistent nicht löschen lässt — `null`, wenn er sich löschen lässt.
 *
 * @param {{scope: string, status: string}} assistent
 * @returns {string|null}
 */
export function loeschsperre(assistent) {
  if (!SCHOOLWIDE_SCOPES.has(assistent.scope)) return null;
  if (assistent.status === "draft" || assistent.status === "pending_review") return null;
  return "Schulweit freigegeben – die Löschung wird im Editor beantragt.";
}
