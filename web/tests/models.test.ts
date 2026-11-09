import { afterEach, describe, expect, it, vi } from "vitest";
import { defaultEffortLabel, effortLabel, fetchModels, resetModelsCache, type ModelsOut } from "../src/lib/models";

const MODELS: ModelsOut = {
  choices: [{ id: "m1", label: "Sonnet 5.5", line: "sonnet", new: false }],
  efforts: ["low", "medium", "high", "max"],
  default_model: "m1",
  default_effort: { m1: "high" },
  notice: null,
};

afterEach(() => { vi.unstubAllGlobals(); resetModelsCache(); });

describe("models lib", () => {
  it("labels efforts", () => {
    expect(effortLabel("max")).toBe("Max");
    expect(effortLabel(null)).toBe("Default");
    expect(defaultEffortLabel(MODELS, "m1")).toBe("Default (high)");
    expect(defaultEffortLabel(MODELS, "other")).toBe("Default");
  });

  it("fetches once and shares the answer", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(MODELS), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    expect(await fetchModels()).toEqual(MODELS);
    await fetchModels();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("forgets a failed fetch so the next call retries", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response("{}", { status: 500 }))
      .mockResolvedValue(new Response(JSON.stringify(MODELS), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(fetchModels()).rejects.toBeTruthy();
    expect(await fetchModels()).toEqual(MODELS);
  });
});
