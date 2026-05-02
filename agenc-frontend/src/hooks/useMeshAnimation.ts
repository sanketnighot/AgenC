"use client";

import { useCallback, useState, type MutableRefObject } from "react";
import {
  routePath,
  schedulePacketTrain,
  type MeshNodeId,
  type MeshPacket,
  type PacketTone,
} from "@/lib/meshPackets";

/**
 * Packet train animations on the mesh canvas (depends on worker topology ref).
 */
export function useMeshAnimation(workerKeysRef: MutableRefObject<string[]>) {
  const [meshPackets, setMeshPackets] = useState<MeshPacket[]>([]);

  const spawnTrain = useCallback(
    (from: MeshNodeId, to: MeshNodeId, tone: PacketTone) => {
      const steps = routePath(from, to, workerKeysRef.current);
      if (steps.length === 0) return;
      schedulePacketTrain(
        steps,
        tone,
        (p) => setMeshPackets((prev) => [...prev, p]),
        (id) => setMeshPackets((prev) => prev.filter((x) => x.id !== id)),
      );
    },
    [workerKeysRef],
  );

  return { meshPackets, spawnTrain };
}
