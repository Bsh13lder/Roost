// What you say, as the voice service takes it (voice plan V1): a WAV of PCM 16-bit, one channel, made here in the
// browser from the microphone's float samples. No library: a 44-byte header and the samples.

export const VOICE_SAMPLE_RATE = 16_000; // what the composer sends; the server takes 8–48 kHz
export const VOICE_MAX_SECONDS = 120; // the server's cap on one recording
// Live words while recording (voice tuning D4): the whole buffer so far goes for a partial transcript this often,
// while it is at most this long (the server's VOICE_PARTIAL_EVERY_MS and VOICE_PARTIAL_MAX_S).
export const VOICE_PARTIAL_EVERY_MS = 1000;
export const VOICE_PARTIAL_MAX_S = 30;

const HEADER_BYTES = 44;
const BYTES_PER_SAMPLE = 2;
const BITS_PER_SAMPLE = 16;
const PCM_FORMAT = 1;
const MONO = 1;
const FMT_CHUNK_BYTES = 16;
const INT16_MAX = 0x7fff;
const INT16_MIN_ABS = 0x8000;

// The chunks the recorder collected, as one run of samples.
export function joinChunks(chunks: readonly Float32Array[]): Float32Array {
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const joined = new Float32Array(total);
  chunks.reduce((offset, chunk) => {
    joined.set(chunk, offset);
    return offset + chunk.length;
  }, 0);
  return joined;
}

// Fewer samples per second: each new sample is the average of the source samples it covers (a simple low-pass, so
// the higher sounds don't fold back as noise). A source at or below the target rate is returned as it is.
export function downsample(input: Float32Array, fromRate: number, toRate: number = VOICE_SAMPLE_RATE): Float32Array {
  if (fromRate <= toRate) return input;
  const ratio = fromRate / toRate;
  const length = Math.round(input.length / ratio);
  const output = new Float32Array(length);
  for (let i = 0; i < length; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.max(start + 1, Math.floor((i + 1) * ratio)));
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += input[j];
    output[i] = sum / (end - start);
  }
  return output;
}

function writeText(view: DataView, offset: number, text: string): void {
  for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
}

function toInt16(sample: number): number {
  const clamped = Math.max(-1, Math.min(1, sample));
  return clamped < 0 ? Math.round(clamped * INT16_MIN_ABS) : Math.round(clamped * INT16_MAX);
}

// Float samples in [-1, 1] → a mono 16-bit PCM WAV file's bytes.
export function encodeWav(samples: Float32Array, sampleRate: number = VOICE_SAMPLE_RATE): ArrayBuffer {
  const dataBytes = samples.length * BYTES_PER_SAMPLE;
  const buffer = new ArrayBuffer(HEADER_BYTES + dataBytes);
  const view = new DataView(buffer);
  writeText(view, 0, "RIFF");
  view.setUint32(4, HEADER_BYTES - 8 + dataBytes, true);
  writeText(view, 8, "WAVE");
  writeText(view, 12, "fmt ");
  view.setUint32(16, FMT_CHUNK_BYTES, true);
  view.setUint16(20, PCM_FORMAT, true);
  view.setUint16(22, MONO, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * MONO * BYTES_PER_SAMPLE, true);
  view.setUint16(32, MONO * BYTES_PER_SAMPLE, true);
  view.setUint16(34, BITS_PER_SAMPLE, true);
  writeText(view, 36, "data");
  view.setUint32(40, dataBytes, true);
  samples.forEach((sample, i) => view.setInt16(HEADER_BYTES + i * BYTES_PER_SAMPLE, toInt16(sample), true));
  return buffer;
}

// The recorder's chunks at the microphone's rate → the WAV the composer sends (16 kHz mono), cut at the server's cap.
export function recordingToWav(chunks: readonly Float32Array[], fromRate: number): Blob {
  const samples = downsample(joinChunks(chunks), fromRate);
  const rate = Math.min(fromRate, VOICE_SAMPLE_RATE);
  const capped = samples.subarray(0, rate * VOICE_MAX_SECONDS);
  return new Blob([encodeWav(capped, rate)], { type: "audio/wav" });
}
