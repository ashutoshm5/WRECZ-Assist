import { useCallback, useEffect, useRef } from "react";
import type { VoiceStream } from "@/lib/voiceStream";

/**
 * WRECZ voice visualizer.
 *
 * The waveform engine (RMS energy, organic modulation, quadratic smoothing,
 * two-pass stroke) is the locked visualizer kit, unchanged.
 *
 * Everything is drawn on one canvas with the same stroke, including the
 * resting line. There is no element swap, so the line never changes weight
 * and waking up is a continuous animation rather than a cut.
 *
 * Three phases:
 *   dormant - a perfectly straight line, until WRECZ first speaks
 *   speaking - the waveform, fed by the voice engine in real time
 *   live     - a slow idle wave between utterances, so the assistant reads
 *              as awake rather than switched off
 */

const POINTS = 140;
const WINDOW_SAMPLES = 2048;
const SILENCE = 128;

// How quickly the line blooms out of the dormant straight line. Low and slow:
// this is the one transition the user actually watches.
const WAKE_LERP = 0.035;

type Point = { x: number; y: number };

function smoothPath(ctx: CanvasRenderingContext2D, points: Point[]) {
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);

  for (let i = 1; i < points.length - 1; i++) {
    const cx = (points[i].x + points[i + 1].x) * 0.5;
    const cy = (points[i].y + points[i + 1].y) * 0.5;
    ctx.quadraticCurveTo(points[i].x, points[i].y, cx, cy);
  }

  const last = points[points.length - 1];
  ctx.lineTo(last.x, last.y);
  ctx.stroke();
}

/** The two-pass stroke from the kit. Every line in this component uses it. */
function strokeWave(ctx: CanvasRenderingContext2D, points: Point[]) {
  ctx.save();
  ctx.lineJoin = "round";
  ctx.lineCap = "round";

  // Soft outer pass.
  ctx.shadowColor = "rgba(17,17,17,0.22)";
  ctx.shadowBlur = 12;
  ctx.strokeStyle = "rgba(17,17,17,0.20)";
  ctx.lineWidth = 8;
  smoothPath(ctx, points);

  // Crisp main waveform.
  ctx.shadowBlur = 0;
  ctx.strokeStyle = "#111111";
  ctx.lineWidth = 3.2;
  smoothPath(ctx, points);

  ctx.restore();
}

export default function VoiceVisualizer({
  speaking,
  voice,
}: {
  speaking: boolean;
  voice: VoiceStream;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const speakingRef = useRef(speaking);
  const awake = useRef(false);
  const running = useRef(false);
  const rafRef = useRef(0);

  const data = useRef(new Uint8Array(WINDOW_SAMPLES).fill(SILENCE));
  const smoothed = useRef(new Float32Array(POINTS));
  const target = useRef(new Float32Array(POINTS));
  const visualEnergy = useRef(0);
  const phase = useRef(0);
  const wake = useRef(0);

  const context = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return null;

    const rect = canvas.getBoundingClientRect();
    return { ctx, w: rect.width, h: rect.height };
  }, []);

  /** Straight line, same stroke as the waveform. Used before WRECZ wakes. */
  const drawResting = useCallback(() => {
    const frame = context();
    if (!frame) return;

    const { ctx, w, h } = frame;
    const mid = h * 0.5;

    ctx.clearRect(0, 0, w, h);
    strokeWave(ctx, [
      { x: 0, y: mid },
      { x: w * 0.5, y: mid },
      { x: w, y: mid },
    ]);
  }, [context]);

  const fitCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    canvas.width = Math.max(1, Math.round(rect.width * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    if (!running.current) drawResting();
  }, [drawResting]);

  const drawFrame = useCallback(() => {
    rafRef.current = requestAnimationFrame(drawFrame);

    const frame = context();
    if (!frame) return;

    const { ctx, w, h } = frame;
    const mid = h * 0.5;

    ctx.clearRect(0, 0, w, h);

    // Blooms 0 -> 1 once, the first time WRECZ speaks, and stays there.
    wake.current += (1 - wake.current) * WAKE_LERP;

    // Between utterances the buffer reads as silence, which leaves only the
    // organic modulation: the slow idle wave.
    if (speakingRef.current) {
      voice.read(data.current);
    } else {
      data.current.fill(SILENCE);
    }

    const samples = data.current;

    let rms = 0;
    for (let i = 0; i < samples.length; i++) {
      const v = (samples[i] - 128) / 128;
      rms += v * v;
    }

    rms = Math.sqrt(rms / samples.length);

    // Smooth the measured energy so the waveform feels fluid.
    visualEnergy.current += (rms - visualEnergy.current) * 0.18;

    const energy = Math.min(1, visualEnergy.current * 7.5);
    phase.current += 0.015 + energy * 0.025;

    const step = samples.length / POINTS;

    for (let i = 0; i < POINTS; i++) {
      const t = i / (POINTS - 1);

      const sample =
        (samples[Math.min(samples.length - 1, Math.floor(i * step))] - 128) / 128;

      // No center weighting: the waveform extends continuously
      // from the left edge all the way to the right edge.
      const organic =
        Math.sin(t * Math.PI * 3.4 + phase.current) * 0.022 +
        Math.sin(t * Math.PI * 8.0 - phase.current * 0.62) * 0.01;

      target.current[i] = sample * (0.05 + energy * 0.6) + organic;

      smoothed.current[i] += (target.current[i] - smoothed.current[i]) * 0.2;
    }

    const points = new Array<Point>(POINTS);

    for (let i = 0; i < POINTS; i++) {
      const t = i / (POINTS - 1);
      points[i] = { x: t * w, y: mid - smoothed.current[i] * h * wake.current };
    }

    strokeWave(ctx, points);
  }, [context, voice]);

  useEffect(() => {
    speakingRef.current = speaking;

    // The first utterance wakes the visualizer for good: from here on it keeps
    // a live idle wave instead of dropping back to a dead straight line.
    if (speaking && !awake.current) {
      awake.current = true;

      if (!running.current) {
        running.current = true;
        rafRef.current = requestAnimationFrame(drawFrame);
      }
    }
  }, [speaking, drawFrame]);

  useEffect(() => {
    fitCanvas();

    window.addEventListener("resize", fitCanvas);
    return () => window.removeEventListener("resize", fitCanvas);
  }, [fitCanvas]);

  useEffect(
    () => () => {
      cancelAnimationFrame(rafRef.current);
      running.current = false;
    },
    [],
  );

  return (
    <div className="wrecz-visualizer" aria-hidden="true">
      <canvas ref={canvasRef} className="wrecz-visualizer-canvas" />
    </div>
  );
}
