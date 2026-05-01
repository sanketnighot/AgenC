/** Radial hub: emitter center, one spoke per worker index (0..n-1). */

export type MeshNodeId = "emitter" | string;

export type PacketTone =
  | "amber"
  | "emerald"
  | "emeraldBright"
  | "red"
  | "emeraldDim";

export interface MeshPacket {
  id: string;
  spokeIndex: number;
  dir: "ltr" | "rtl";
  tone: PacketTone;
}

export interface PathStep {
  spokeIndex: number;
  dir: "ltr" | "rtl";
}

function resolveIndex(id: MeshNodeId, workerKeys: string[]): number {
  if (id === "emitter") return -1;
  const i = workerKeys.indexOf(id);
  return i;
}

/** Routes along spoke(s); worker↔worker goes via emitter (two hops). */
export function routePath(
  from: MeshNodeId,
  to: MeshNodeId,
  workerKeys: string[],
): PathStep[] {
  if (from === to || workerKeys.length === 0) return [];

  const fi = resolveIndex(from, workerKeys);
  const fj = resolveIndex(to, workerKeys);

  if (fi === -1 && fj >= 0) {
    return [{ spokeIndex: fj, dir: "ltr" }];
  }
  if (fj === -1 && fi >= 0) {
    return [{ spokeIndex: fi, dir: "rtl" }];
  }
  if (fi >= 0 && fj >= 0 && fi !== fj) {
    return [
      { spokeIndex: fi, dir: "rtl" },
      { spokeIndex: fj, dir: "ltr" },
    ];
  }
  return [];
}

export function schedulePacketTrain(
  steps: PathStep[],
  tone: PacketTone,
  onAdd: (p: MeshPacket) => void,
  onRemove: (id: string) => void,
  staggerMs = 300,
  durationMs = 600,
): () => void {
  const timeouts: ReturnType<typeof setTimeout>[] = [];

  const spawnOne = (step: PathStep) => {
    const id =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `pkt-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    onAdd({
      id,
      spokeIndex: step.spokeIndex,
      dir: step.dir,
      tone,
    });
    timeouts.push(setTimeout(() => onRemove(id), durationMs));
  };

  steps.forEach((step, k) => {
    if (k === 0) {
      spawnOne(step);
      return;
    }
    const spawnId = setTimeout(() => spawnOne(step), k * staggerMs);
    timeouts.push(spawnId);
  });

  return () => {
    timeouts.forEach(clearTimeout);
    timeouts.length = 0;
  };
}

export function resolveWorkerNodeBySpecialty(
  specialty: string,
  nodes: Record<string, { specialty?: string }>,
  workerKeys: string[],
): string | null {
  for (const k of workerKeys) {
    if (nodes[k]?.specialty === specialty) return k;
  }
  return null;
}
