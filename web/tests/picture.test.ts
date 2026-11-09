import { afterEach, describe, expect, it, vi } from "vitest";
import { PictureError, shrinkPicture } from "../src/lib/picture";

afterEach(() => vi.unstubAllGlobals());

describe("shrinkPicture", () => {
  it("refuses a file that is not a picture, in plain words", async () => {
    await expect(shrinkPicture(new Blob(["%PDF"], { type: "application/pdf" }))).rejects.toThrow(
      new PictureError("That file is not a picture. Pick a PNG, JPEG or WebP."));
  });

  it("says so when the browser can't read the picture", async () => {
    vi.stubGlobal("createImageBitmap", () => Promise.reject(new Error("decode failed")));
    await expect(shrinkPicture(new Blob(["x"], { type: "image/png" }))).rejects.toThrow(
      "Roost could not read that picture. Try another one.");
  });

  it("crops the middle square and writes it at 256 px", async () => {
    const close = vi.fn();
    vi.stubGlobal("createImageBitmap", () => Promise.resolve({ width: 400, height: 200, close }));
    const drawImage = vi.fn();
    const out = new Blob(["webp"], { type: "image/webp" });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(function (callback: BlobCallback) { callback(out); });
    expect(await shrinkPicture(new Blob(["x"], { type: "image/png" }))).toBe(out);
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 100, 0, 200, 200, 0, 0, 256, 256);
    expect(close).toHaveBeenCalled();
    vi.restoreAllMocks();
  });
});
