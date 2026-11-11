import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { ModelPicker } from "../src/components/profile/ModelPicker";
import { ToastProvider } from "../src/ui/Toast";
import { resetModelsCache, type ModelsOut } from "../src/lib/models";
import { makeBot } from "./fixtures";

const MODELS: ModelsOut = {
  choices: [
    { id: "fable-id", label: "Fable 5.2", line: "fable", new: false },
    { id: "sonnet-id", label: "Sonnet 5.5", line: "sonnet", new: false },
    { id: "opus-id", label: "Opus 5.5", line: "opus", new: false },
    { id: "haiku-id", label: "Haiku 5.5", line: "haiku", new: false },
  ],
  efforts: ["low", "medium", "high", "max"],
  default_model: "sonnet-id",
  default_effort: { "sonnet-id": "high", "opus-id": "medium" },
  notice: null,
};

function stub(models: ModelsOut = MODELS, put = vi.fn()) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT") { put(JSON.parse(String(init.body))); return new Response(JSON.stringify(makeBot({ model: "opus-id", model_label: "Opus 5.5" })), { status: 200 }); }
    return new Response(JSON.stringify(models), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return put;
}

function renderPicker(url = "/bots/bot-1", onChange = vi.fn()) {
  render(<MemoryRouter initialEntries={[url]}><ToastProvider><ModelPicker bot={makeBot({ model: "sonnet-id" })} onChange={onChange} /></ToastProvider></MemoryRouter>);
  return onChange;
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); resetModelsCache(); });

describe("ModelPicker", () => {
  it('shows the model and "Default (high)" for a new bot', async () => {
    stub();
    renderPicker();
    expect(await screen.findByRole("combobox", { name: "Model" })).toHaveTextContent("Sonnet 5.5");
    expect(screen.getByRole("combobox", { name: "Effort" })).toHaveTextContent("Default (high)");
  });

  it("saving a model calls PUT and shows a toast", async () => {
    const put = stub();
    const onChange = renderPicker();
    await userEvent.click(await screen.findByRole("combobox", { name: "Model" }));
    await userEvent.click(await screen.findByRole("option", { name: /^Opus 5\.5/ }));
    await waitFor(() => expect(put).toHaveBeenCalledWith({ model: "opus-id", effort: null }));
    expect(await screen.findByText("Scout now runs on Opus 5.5")).toBeInTheDocument();
    expect(onChange).toHaveBeenCalled();
  });

  it("the effort list is Default, Low, Medium, High, Max", async () => {
    stub();
    renderPicker();
    await userEvent.click(await screen.findByRole("combobox", { name: "Effort" }));
    const names = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(names).toEqual(["Default (high)", "Low", "Medium", "High", "Max"]);
  });

  it("lists Fable, Sonnet, Opus and Haiku, each with a short hint, and the chosen one shows only its name", async () => {
    stub();
    renderPicker();
    const model = await screen.findByRole("combobox", { name: "Model" });
    expect(model).toHaveTextContent(/^Sonnet 5\.5$/);
    expect(screen.getByText("Sonnet 5.5: balanced, the usual choice")).toBeInTheDocument();
    await userEvent.click(model);
    const options = await screen.findAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([
      "Fable 5.2the most capable", "Sonnet 5.5balanced, the usual choice", "Opus 5.5careful, deep work", "Haiku 5.5fast and cheap",
    ]);
  });

  it("a new model from the check is listed with a New mark", async () => {
    stub({ ...MODELS, choices: [...MODELS.choices, { id: "new-id", label: "Opus 5.6", line: "new", new: true }] });
    renderPicker();
    await userEvent.click(await screen.findByRole("combobox", { name: "Model" }));
    expect(await screen.findByRole("option", { name: "Opus 5.6 · New" })).toBeInTheDocument();
  });

  it("?try=<id> opens the Model select", async () => {
    stub();
    renderPicker("/bots/bot-1?panel=info&try=opus-id");
    expect(await screen.findByRole("option", { name: /^Opus 5\.5/ })).toBeInTheDocument();
  });
});
