import { describe, expect, it } from "vitest";
import { downsample, encodeWav, joinChunks, recordingToWav, VOICE_MAX_SECONDS, VOICE_SAMPLE_RATE } from "../src/lib/wav";

const text = (view: DataView, offset: number, length: number) =>
  Array.from({ length }, (_, i) => String.fromCharCode(view.getUint8(offset + i))).join("");

function readBlob(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

describe("the browser's WAV encoder (voice V3)", () => {
  it("writes a 44-byte PCM header: RIFF/WAVE, 16-bit, mono, 16 kHz", () => {
    const view = new DataView(encodeWav(new Float32Array(10), VOICE_SAMPLE_RATE));
    expect(view.byteLength).toBe(44 + 20);
    expect(text(view, 0, 4)).toBe("RIFF");
    expect(view.getUint32(4, true)).toBe(36 + 20);
    expect(text(view, 8, 4)).toBe("WAVE");
    expect(text(view, 12, 4)).toBe("fmt ");
    expect(view.getUint32(16, true)).toBe(16);
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(16_000);
    expect(view.getUint32(28, true)).toBe(32_000); // bytes per second
    expect(view.getUint16(32, true)).toBe(2); // block align
    expect(view.getUint16(34, true)).toBe(16); // bits per sample
    expect(text(view, 36, 4)).toBe("data");
    expect(view.getUint32(40, true)).toBe(20);
  });

  it("turns floats into clamped little-endian 16-bit samples", () => {
    const view = new DataView(encodeWav(Float32Array.from([0, 1, -1, 2, -2, 0.5])));
    const samples = Array.from({ length: 6 }, (_, i) => view.getInt16(44 + 2 * i, true));
    expect(samples).toEqual([0, 32767, -32768, 32767, -32768, 16384]);
  });

  it("downsamples 48 kHz to 16 kHz: a third as many samples, each the average it covers", () => {
    const second = new Float32Array(48_000).fill(0.25);
    const out = downsample(second, 48_000);
    expect(out.length).toBe(16_000);
    expect(out[100]).toBeCloseTo(0.25);
    expect(downsample(Float32Array.from([0, 0.3, 0.6, 0.9, 0.9, 0.9]), 48_000)).toEqual(Float32Array.from([0.3, 0.9]));
  });

  it("downsamples 44.1 kHz to the right length too, and leaves a lower rate alone", () => {
    expect(downsample(new Float32Array(44_100), 44_100).length).toBe(16_000);
    const low = new Float32Array(800);
    expect(downsample(low, 8_000)).toBe(low);
  });

  it("joins the recorder's chunks in order", () => {
    expect(joinChunks([Float32Array.from([1, 2]), Float32Array.from([3])])).toEqual(Float32Array.from([1, 2, 3]));
  });

  it("makes an audio/wav Blob at 16 kHz mono, cut at two minutes", async () => {
    const wav = recordingToWav([new Float32Array(48_000), new Float32Array(48_000)], 48_000);
    expect(wav.type).toBe("audio/wav");
    expect(wav.size).toBe(44 + 2 * 32_000);
    const long = recordingToWav([new Float32Array(16_000 * (VOICE_MAX_SECONDS + 5))], 16_000);
    expect(long.size).toBe(44 + 2 * 16_000 * VOICE_MAX_SECONDS);
    const view = new DataView(await readBlob(wav));
    expect(view.getUint32(24, true)).toBe(16_000);
    expect(view.getUint16(22, true)).toBe(1);
  });
});
