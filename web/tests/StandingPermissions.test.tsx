import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StandingPermissions } from "../src/components/routines/StandingPermissions";
import { standingDay, permissionWords } from "../src/components/routines/standingWords";
import { ApiError } from "../src/api/client";
import type { PermissionOut } from "../src/api/standing";

const api = { listPermissions: vi.fn(), addPermission: vi.fn(), revokePermission: vi.fn() };
vi.mock("../src/api/standing", () => ({
  listPermissions: (...a: unknown[]) => api.listPermissions(...a),
  addPermission: (...a: unknown[]) => api.addPermission(...a),
  revokePermission: (...a: unknown[]) => api.revokePermission(...a),
}));

afterEach(() => { cleanup(); Object.values(api).forEach((mock) => mock.mockReset()); });

const PERMISSION: PermissionOut = {
  id: "p1", routine_id: "r1", host: "x.com", action: "post", max_per_day: 1, until: "2026-11-01", used_today: 0,
  created_at: "2026-10-23T08:00:00+00:00",
};

describe("standing permission words", () => {
  it("say the permission in the owner's words with a Madrid day", () => {
    expect(standingDay("2026-11-01")).toBe("Sun 1 Nov");
    expect(standingDay("soon")).toBe("soon");
    expect(permissionWords(PERMISSION)).toBe("Let it post on x.com up to 1 a day until Sun 1 Nov");
  });
});

describe("StandingPermissions", () => {
  it("lists the routine's permission and Revoke removes it at once", async () => {
    api.listPermissions.mockResolvedValue([PERMISSION]);
    api.revokePermission.mockResolvedValue(undefined);
    render(<StandingPermissions routineId="r1" />);
    expect(await screen.findByText("Let it post on x.com up to 1 a day until Sun 1 Nov")).toBeInTheDocument();
    expect(screen.getByText("Used 0 today")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(api.revokePermission).toHaveBeenCalledWith("r1", "p1"));
    await waitFor(() => expect(screen.queryByText(/Let it post on x.com/)).not.toBeInTheDocument());
  });

  it("Save sends the row as typed and shows the new permission", async () => {
    api.listPermissions.mockResolvedValue([]);
    api.addPermission.mockResolvedValue({ ...PERMISSION, id: "p2", host: "linkedin.com", max_per_day: 2 });
    render(<StandingPermissions routineId="r1" />);
    expect(await screen.findByText("None. Everything it posts, sends or submits asks you first.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Site"), { target: { value: "linkedin.com" } });
    fireEvent.change(screen.getByLabelText("A day"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Until"), { target: { value: "2026-11-01" } });
    await userEvent.click(screen.getByRole("button", { name: "Save permission" }));
    await waitFor(() => expect(api.addPermission).toHaveBeenCalledWith("r1", {
      host: "linkedin.com", action: "post", max_per_day: 2, until: "2026-11-01" }));
    expect(await screen.findByText(/Let it post on linkedin.com up to 2 a day/)).toBeInTheDocument();
  });

  it("a refusal shows the server's sentence", async () => {
    api.listPermissions.mockResolvedValue([]);
    api.addPermission.mockRejectedValue(new ApiError(422, "Name the site as a plain address, such as x.com."));
    render(<StandingPermissions routineId="r1" />);
    await screen.findByText(/None\./);
    fireEvent.change(screen.getByLabelText("Site"), { target: { value: "https://x" } });
    await userEvent.click(screen.getByRole("button", { name: "Save permission" }));
    expect(await screen.findByText("Name the site as a plain address, such as x.com.")).toBeInTheDocument();
  });

  it("a failed load says so", async () => {
    api.listPermissions.mockRejectedValue(new ApiError(404, "Routine not found"));
    render(<StandingPermissions routineId="r1" />);
    expect(await screen.findByText("Routine not found")).toBeInTheDocument();
  });
});
