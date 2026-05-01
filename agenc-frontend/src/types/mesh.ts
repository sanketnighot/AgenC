/** Shared mesh / topology view models (bridge `mesh_state` + UI). */

export interface MeshWorkerView {
  node_key: string;
  label: string;
  specialty: string;
  short_id: string;
  peer_id: string;
  mesh_connected: boolean;
}
