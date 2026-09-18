import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get } from "svelte/store"

vi.mock("$lib/api.js", () => ({ getGroupsConfig: vi.fn() }))

import { getGroupsConfig } from "$lib/api.js"

/** Frisches Modul je Test — der Store hält seinen Zustand über die Lebensdauer. */
async function frisch() {
    vi.resetModules()
    return import("./groupsConfig.js")
}

beforeEach(() => vi.mocked(getGroupsConfig).mockReset())
afterEach(() => vi.restoreAllMocks())

describe("groupsConfig", () => {
    it("meldet den Erprobungsmodus, wenn der Server ihn meldet", async () => {
        vi.mocked(getGroupsConfig).mockResolvedValue({
            allow_manual_teaching_groups: true,
            student_subjects_opt_in: true,
        })
        const { groupsConfig, refreshGroupsConfig } = await frisch()

        await refreshGroupsConfig()

        expect(get(groupsConfig).student_subjects_opt_in).toBe(true)
    })

    it("steht vor der ersten Antwort auf AUS", async () => {
        // Sonst blitzten beim Laden kurz die Fächer weg, die gleich wieder erscheinen.
        const { groupsConfig } = await frisch()

        expect(get(groupsConfig).student_subjects_opt_in).toBe(false)
    })

    it("bleibt bei einem Netzwerkfehler auf AUS", async () => {
        // Die wichtigere Richtung: Ein gescheiterter Abruf darf Schüler:innen nicht
        // ihre Fächer nehmen. Zu viel zu zeigen ist im Zweifel das kleinere Übel als
        // eine leere Oberfläche, deren Ursache niemand sieht.
        vi.mocked(getGroupsConfig).mockRejectedValue(new Error("offline"))
        const { groupsConfig, refreshGroupsConfig } = await frisch()

        await refreshGroupsConfig()

        expect(get(groupsConfig).student_subjects_opt_in).toBe(false)
        expect(get(groupsConfig).allow_manual_teaching_groups).toBe(true)
    })
})
