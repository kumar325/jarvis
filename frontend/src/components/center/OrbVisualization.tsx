import { useEffect, useRef } from "react";

interface Particle {
  angle: number;
  radius: number;
  speed: number;
  baseSize: number;
  baseAlpha: number;
  twinkleSpeed: number;
  phase: number;
  ringOffset: number;
}

interface Ray {
  angle: number;
  lengthFactor: number;
  speedFactor: number;
  phase: number;
}

/** Position in a unit sphere (radius 0-1), scaled up to orbRadius at render time. */
interface NetworkNode {
  x: number;
  y: number;
  z: number;
  baseSize: number;
  baseAlpha: number;
  driftPhase: number;
  driftSpeed: number;
}

type NetworkEdge = [number, number];

interface ScreenNode {
  x: number;
  y: number;
  size: number;
  alpha: number;
}

interface Props {
  /** 0-1 amplitude driving the orb's reactivity; defaults to a slow idle breathing pulse. */
  amplitude?: number;
  active?: boolean;
  /** Jarvis is talking — the orb shifts from gold to red for the duration. */
  speaking?: boolean;
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ];
}

/** Blend two hex colours. Output stays 6-digit hex because the render path appends an
 * alpha byte to it (`${accent}${alphaHex(...)}`) rather than using rgba(). */
function mixHex(from: string, to: string, t: number): string {
  const [r1, g1, b1] = hexToRgb(from);
  const [r2, g2, b2] = hexToRgb(to);
  const channel = (a: number, b: number) =>
    Math.round(a + (b - a) * t)
      .toString(16)
      .padStart(2, "0");
  return `#${channel(r1, r2)}${channel(g1, g2)}${channel(b1, b2)}`;
}

const RING_COUNT = 3;
const PARTICLES_PER_RING = 22;
const RAY_COUNT = 18;
const NODE_COUNT = 260;
const MAX_NEIGHBORS = 3;

function buildParticles(): Particle[] {
  const particles: Particle[] = [];
  for (let ring = 0; ring < RING_COUNT; ring++) {
    for (let i = 0; i < PARTICLES_PER_RING; i++) {
      particles.push({
        angle: (i / PARTICLES_PER_RING) * Math.PI * 2,
        radius: 0.4 + ring * 0.18,
        speed: (ring % 2 === 0 ? 1 : -1) * (0.15 + ring * 0.05),
        baseSize: (1.6 - ring * 0.25) * (0.6 + Math.random() * 0.8),
        baseAlpha: (0.6 - ring * 0.12) * (0.5 + Math.random() * 0.6),
        twinkleSpeed: 0.6 + Math.random() * 1.4,
        phase: Math.random() * Math.PI * 2,
        ringOffset: ring,
      });
    }
  }
  return particles;
}

function buildRays(): Ray[] {
  const rays: Ray[] = [];
  for (let i = 0; i < RAY_COUNT; i++) {
    rays.push({
      angle: (i / RAY_COUNT) * Math.PI * 2 + Math.random() * 0.08,
      lengthFactor: 0.6 + Math.random() * 0.8,
      speedFactor: 0.2 + Math.random() * 0.35,
      phase: Math.random() * Math.PI * 2,
    });
  }
  return rays;
}

/** Nearest-neighbor edges computed once on unrotated unit-sphere positions — a rigid
 * rotation preserves relative distances, so edges don't need recomputing every frame. */
function buildNetwork(): { nodes: NetworkNode[]; edges: NetworkEdge[] } {
  const nodes: NetworkNode[] = [];
  for (let i = 0; i < NODE_COUNT; i++) {
    // Radius skewed toward 0 so nodes pack dense at the core, sparse toward the edge.
    const r = Math.pow(Math.random(), 1.8);
    const cosTheta = 1 - 2 * Math.random();
    const sinTheta = Math.sqrt(1 - cosTheta * cosTheta);
    const phi = Math.random() * Math.PI * 2;
    const coreFactor = 1 - r;
    nodes.push({
      x: r * sinTheta * Math.cos(phi),
      y: r * sinTheta * Math.sin(phi),
      z: r * cosTheta,
      baseSize: 0.5 + coreFactor * 1.7 + Math.random() * 0.5,
      baseAlpha: 0.2 + coreFactor * 0.6 + Math.random() * 0.15,
      driftPhase: Math.random() * Math.PI * 2,
      driftSpeed: 0.15 + Math.random() * 0.25,
    });
  }

  const edges: NetworkEdge[] = [];
  const edgeSet = new Set<string>();
  for (let i = 0; i < nodes.length; i++) {
    const candidates: { j: number; distSq: number }[] = [];
    for (let j = 0; j < nodes.length; j++) {
      if (i === j) continue;
      const dx = nodes[i].x - nodes[j].x;
      const dy = nodes[i].y - nodes[j].y;
      const dz = nodes[i].z - nodes[j].z;
      candidates.push({ j, distSq: dx * dx + dy * dy + dz * dz });
    }
    candidates.sort((a, b) => a.distSq - b.distSq);
    for (let k = 0; k < MAX_NEIGHBORS && k < candidates.length; k++) {
      const j = candidates[k].j;
      const key = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (!edgeSet.has(key)) {
        edgeSet.add(key);
        edges.push([i, j]);
      }
    }
  }

  return { nodes, edges };
}

function alphaHex(alpha: number): string {
  const clamped = Math.max(0, Math.min(1, alpha));
  return Math.round(clamped * 255)
    .toString(16)
    .padStart(2, "0");
}

export function OrbVisualization({ amplitude = 0, active = false, speaking = false }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>(buildParticles());
  const raysRef = useRef<Ray[]>(buildRays());
  const networkRef = useRef(buildNetwork());
  const screenNodesRef = useRef<ScreenNode[]>(
    Array.from({ length: NODE_COUNT }, () => ({ x: 0, y: 0, size: 0, alpha: 0 }))
  );
  const amplitudeRef = useRef(amplitude);
  const speakingRef = useRef(speaking);
  /** Eased 0-1 position between gold and red, stepped per frame rather than per render. */
  const speakMixRef = useRef(0);

  useEffect(() => {
    amplitudeRef.current = amplitude;
  }, [amplitude]);

  // A ref, not an effect dependency: the render effect resets `t` when it re-runs, so
  // adding `speaking` to its deps would jolt the breathing and orbit animations every time
  // Jarvis started or stopped talking.
  useEffect(() => {
    speakingRef.current = speaking;
  }, [speaking]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let frameId: number;
    let width = 0;
    let height = 0;

    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      width = parent.clientWidth;
      height = parent.clientHeight;
      canvas.width = width * devicePixelRatio;
      canvas.height = height * devicePixelRatio;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.scale(devicePixelRatio, devicePixelRatio);
    };

    resize();
    const resizeObserver = new ResizeObserver(resize);
    if (canvas.parentElement) resizeObserver.observe(canvas.parentElement);

    let t = 0;

    const render = () => {
      t += 0.016;
      ctx.clearRect(0, 0, width, height);

      const styles = getComputedStyle(document.documentElement);
      const gold = styles.getPropertyValue("--accent").trim() || "#d4a244";
      const red = styles.getPropertyValue("--accent-speaking").trim() || "#d2503f";

      // Ease toward the target instead of snapping: at ~0.06 per frame the crossfade lands
      // in roughly three quarters of a second, short enough to track who is talking and
      // slow enough not to flicker on a clipped or stuttering playback stream.
      const target = speakingRef.current ? 1 : 0;
      speakMixRef.current += (target - speakMixRef.current) * 0.06;
      const accent = mixHex(gold, red, speakMixRef.current);

      const cx = width / 2;
      const cy = height / 2;
      const baseRadius = Math.min(width, height) * 0.16;
      const breathing = 1 + Math.sin(t * 0.8) * 0.04;
      const reactive = 1 + amplitudeRef.current * 0.6;
      const orbRadius = baseRadius * breathing * reactive;

      // Slow independent pulse for the core glow's intensity, distinct from the radius breathing above
      const glowPulse = 0.75 + Math.sin(t * 0.35) * 0.25;

      // Corona: faint wispy rays radiating outward from the core, additive-blended
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      const coronaGradient = ctx.createRadialGradient(
        cx,
        cy,
        orbRadius * 0.85,
        cx,
        cy,
        orbRadius * 3
      );
      coronaGradient.addColorStop(0, `${accent}${alphaHex(0.22 * glowPulse)}`);
      coronaGradient.addColorStop(1, "transparent");
      ctx.strokeStyle = coronaGradient;
      ctx.lineCap = "round";
      ctx.lineWidth = 1;
      for (const ray of raysRef.current) {
        const wobble = 0.8 + Math.sin(t * ray.speedFactor + ray.phase) * 0.2;
        const angle = ray.angle + t * 0.025;
        const innerR = orbRadius * 0.9;
        const outerR = orbRadius * (1.7 + ray.lengthFactor * 1.6) * wobble;
        ctx.globalAlpha = 0.5 * wobble;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(angle) * innerR, cy + Math.sin(angle) * innerR);
        ctx.lineTo(cx + Math.cos(angle) * outerR, cy + Math.sin(angle) * outerR);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      ctx.restore();

      // Outer glow halo, breathing independently of the orb's own radius pulse
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, orbRadius * (3.0 + glowPulse * 0.4));
      glow.addColorStop(0, `${accent}${alphaHex(0.4 * glowPulse)}`);
      glow.addColorStop(1, "transparent");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, width, height);

      // Dense particle-network sphere: rotate + wobble-tilt each node, then project with
      // weak perspective so depth reads as size/brightness. Edges were precomputed once.
      const rotY = t * 0.12;
      const rotX = Math.sin(t * 0.12) * 0.12;
      const cosY = Math.cos(rotY);
      const sinY = Math.sin(rotY);
      const cosX = Math.cos(rotX);
      const sinX = Math.sin(rotX);
      const driftAmp = orbRadius * 0.05;
      const focal = orbRadius * 3.2;

      const nodes = networkRef.current.nodes;
      const screenNodes = screenNodesRef.current;

      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        const drift = t * n.driftSpeed + n.driftPhase;
        const lx = n.x * orbRadius + Math.sin(drift) * driftAmp;
        const ly = n.y * orbRadius + Math.sin(drift + 2.094) * driftAmp;
        const lz = n.z * orbRadius + Math.sin(drift + 4.188) * driftAmp;

        const rx = lx * cosY + lz * sinY;
        const rzY = -lx * sinY + lz * cosY;
        const ry = ly * cosX - rzY * sinX;
        const rz = ly * sinX + rzY * cosX;

        const scale = focal / (focal - rz);
        const depthNorm = Math.max(-1, Math.min(1, rz / orbRadius));
        const depthShade = 0.35 + 0.65 * ((depthNorm + 1) / 2);

        const sn = screenNodes[i];
        sn.x = cx + rx * scale;
        sn.y = cy + ry * scale;
        sn.size = n.baseSize * depthShade * scale * (active ? 1.25 : 1);
        sn.alpha = n.baseAlpha * depthShade;
      }

      ctx.save();
      ctx.globalCompositeOperation = "lighter";

      ctx.strokeStyle = accent;
      ctx.lineWidth = 0.6;
      for (const [i, j] of networkRef.current.edges) {
        const a = screenNodes[i];
        const b = screenNodes[j];
        ctx.globalAlpha = Math.min(a.alpha, b.alpha) * 0.35;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }

      ctx.fillStyle = accent;
      for (const sn of screenNodes) {
        ctx.globalAlpha = sn.alpha;
        ctx.beginPath();
        ctx.arc(sn.x, sn.y, Math.max(sn.size, 0.4), 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      ctx.restore();

      // Orbiting particle rings, each twinkling on its own size/opacity cycle
      const maxDim = Math.min(width, height) * 0.42;
      for (const p of particlesRef.current) {
        p.angle += p.speed * 0.016 * (1 + amplitudeRef.current);
        const r = maxDim * p.radius;
        const x = cx + Math.cos(p.angle) * r;
        const y = cy + Math.sin(p.angle) * r * 0.55;
        const twinkle = 0.55 + Math.sin(t * p.twinkleSpeed + p.phase) * 0.45;
        const size = p.baseSize * twinkle * (active ? 1.4 : 1);
        const alpha = p.baseAlpha * (0.5 + 0.5 * twinkle);

        ctx.beginPath();
        ctx.fillStyle = accent;
        ctx.globalAlpha = alpha;
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
      }

      // Inner scan ring, dashes drifting one direction
      ctx.save();
      ctx.strokeStyle = `${accent}88`;
      ctx.lineWidth = 1;
      ctx.setLineDash([1, 8]);
      ctx.lineDashOffset = t * 30;
      ctx.beginPath();
      ctx.ellipse(cx, cy, maxDim * 0.7, maxDim * 0.7 * 0.55, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      // Outer ring counter-rotating against the inner scan ring, slower and sparser
      ctx.save();
      ctx.strokeStyle = `${accent}55`;
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 14]);
      ctx.lineDashOffset = -t * 18;
      ctx.beginPath();
      ctx.ellipse(cx, cy, maxDim * 0.88, maxDim * 0.88 * 0.55, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      frameId = requestAnimationFrame(render);
    };

    frameId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
    };
  }, [active]);

  return (
    <div className="relative w-full h-full">
      <canvas ref={canvasRef} className="block w-full h-full" />
    </div>
  );
}
