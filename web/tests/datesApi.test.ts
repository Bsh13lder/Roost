import { beforeEach, describe, expect, it, vi } from "vitest";

const apiRequestMock = vi.fn();
vi.mock("../src/api/client", () => ({ apiRequest: (...args: unknown[]) => apiRequestMock(...args) }));
import { parseDate } from "../src/api/dates";

beforeEach(() => apiRequestMock.mockReset().mockResolvedValue({ due_date: null }));

describe("parseDate", () => {
  it("asks for the task-due reading unless told otherwise", async () => {
    await parseDate("tomorrow at 9");
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", "/api/dates/parse?text=tomorrow%20at%209&kind=due");
  });

  it("asks for an expense's reading with kind=spent", async () => {
    await parseDate("hace 3 días", "spent");
    expect(apiRequestMock).toHaveBeenLastCalledWith("GET", `/api/dates/parse?text=${encodeURIComponent("hace 3 días")}&kind=spent`);
  });
});
