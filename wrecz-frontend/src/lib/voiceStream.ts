/**
 * Rolling buffer of the assistant's speech audio.
 *
 * The bridge forwards each slice of Kokoro audio as it is written to the
 * speakers, encoded exactly like AnalyserNode.getByteTimeDomainData: uint8
 * with 128 as silence. This holds the most recent samples so the visualizer
 * can read a window of "what is being heard right now" on every frame.
 */

const SILENCE = 128;

export class VoiceStream {
  private readonly ring: Uint8Array;
  private writePos = 0;

  constructor(capacity = 16384) {
    this.ring = new Uint8Array(capacity).fill(SILENCE);
  }

  push(samples: Uint8Array) {
    const capacity = this.ring.length;

    for (let i = 0; i < samples.length; i++) {
      this.ring[this.writePos] = samples[i];
      this.writePos = (this.writePos + 1) % capacity;
    }
  }

  /** Fill `out` with the most recent samples, oldest first. */
  read(out: Uint8Array) {
    const capacity = this.ring.length;
    let start = (this.writePos - out.length) % capacity;
    if (start < 0) start += capacity;

    for (let i = 0; i < out.length; i++) {
      out[i] = this.ring[(start + i) % capacity];
    }
  }

  reset() {
    this.ring.fill(SILENCE);
    this.writePos = 0;
  }
}

/** Decode one base64 voice frame from the bridge. */
export function decodeVoiceFrame(data: string): Uint8Array {
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);

  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }

  return bytes;
}
