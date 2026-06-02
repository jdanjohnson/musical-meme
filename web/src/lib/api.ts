const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetcher<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

export interface Track {
  id: number;
  file_path: string;
  filename: string;
  folder: string;
  genre: string | null;
  duration: number;
  bpm: number;
  bpm_confidence: number;
  key: string;
  key_confidence: number;
  camelot: string;
  energy: number;
  loudness: number;
  spectral_centroid: number;
  energy_level: number;
  brightness: number;
  title: string | null;
  artist: string | null;
  format: string;
  sample_rate: number;
  channels: number;
  soundcloud_url: string | null;
}

export interface TransitionScore {
  harmonic_score: number;
  bpm_score: number;
  energy_score: number;
  overall_score: number;
  harmonic_move: string;
  bpm_delta: number;
  energy_delta: number;
  camelot_distance: number;
  explanation: string;
}

export interface ScanStatus {
  job_id: number;
  status: string;
  total_files: number;
  processed_files: number;
  skipped_files: number;
  error_files: number;
  current_file: string | null;
  error_message: string | null;
}

export interface LibraryStats {
  total_tracks: number;
  total_duration_hours: number;
  avg_bpm: number;
  bpm_range: [number, number];
  camelot_distribution: Record<string, number>;
  genre_distribution: Record<string, number>;
  bpm_histogram: Record<string, number>;
  energy_distribution: Record<string, number>;
  formats: string[];
}

export interface SetTrack {
  position: number;
  track: Track;
  transition: TransitionScore | null;
}

export interface ArcType {
  id: string;
  name: string;
  description: string;
}

export interface SCImportStatus {
  import_id: number;
  label: string | null;
  status: string;
  total_tracks: number;
  processed_tracks: number;
  skipped_tracks: number;
  error_tracks: number;
  current_track: string | null;
  error_message: string | null;
}

// --- API calls ---

export const api = {
  // Scanning
  startScan: (folderPath: string) =>
    fetcher<ScanStatus>("/api/scan", {
      method: "POST",
      body: JSON.stringify({ folder_path: folderPath }),
    }),

  getScanStatus: (jobId: number) => fetcher<ScanStatus>(`/api/scan/${jobId}`),

  // Library
  getTracks: () => fetcher<{ tracks: Track[]; total: number }>("/api/tracks"),

  getTrack: (id: number) => fetcher<Track>(`/api/tracks/${id}`),

  getStats: () => fetcher<LibraryStats>("/api/stats"),

  // Theory / Set Planning
  suggestNext: (params: {
    track_id: number;
    position_in_set?: number;
    arc_type?: string;
    bpm_range?: number;
    exclude_ids?: number[];
    limit?: number;
  }) =>
    fetcher<{ suggestions: Array<{ track: Track; score: TransitionScore }> }>(
      "/api/suggest",
      { method: "POST", body: JSON.stringify(params) }
    ),

  scoreTransition: (trackAId: number, trackBId: number, positionInSet?: number) =>
    fetcher<{ track_a: Track; track_b: Track; score: TransitionScore }>(
      "/api/transition",
      {
        method: "POST",
        body: JSON.stringify({
          track_a_id: trackAId,
          track_b_id: trackBId,
          position_in_set: positionInSet ?? 0.5,
        }),
      }
    ),

  generateSet: (params: {
    start_track_id?: number;
    target_minutes?: number;
    arc_type?: string;
    bpm_range?: number;
    genre_filter?: string;
  }) =>
    fetcher<{
      set: SetTrack[];
      total_tracks: number;
      total_duration_minutes: number;
      arc_type: string;
    }>("/api/generate-set", { method: "POST", body: JSON.stringify(params) }),

  getArcTypes: () => fetcher<{ arc_types: ArcType[] }>("/api/arc-types"),

  // SoundCloud (via Apify)
  scConnect: (apifyToken: string) =>
    fetcher<{ status: string; message: string }>("/api/soundcloud/connect", {
      method: "POST",
      body: JSON.stringify({ apify_token: apifyToken }),
    }),

  scStatus: () =>
    fetcher<{ connected: boolean; username?: string; error?: string }>("/api/soundcloud/status"),

  scImport: (soundcloudUrl: string, maxItems?: number) =>
    fetcher<SCImportStatus>("/api/soundcloud/import", {
      method: "POST",
      body: JSON.stringify({ soundcloud_url: soundcloudUrl, max_items: maxItems ?? 500 }),
    }),

  scImportStatus: (importId: number) =>
    fetcher<SCImportStatus>(`/api/soundcloud/import/${importId}`),

  scImports: () =>
    fetcher<{ imports: SCImportStatus[] }>("/api/soundcloud/imports"),

  // Gap Analysis
  analyzeGaps: (params: {
    arc_type?: string;
    target_minutes?: number;
    bpm_range?: number;
  }) =>
    fetcher<{
      gaps: Array<{
        type: string;
        severity: string;
        position: number;
        time_in_set: string;
        message: string;
        suggestion: string;
      }>;
      total_gaps: number;
      high_severity: number;
      set_tracks: number;
      set_duration_minutes: number;
    }>("/api/analyze-gaps", { method: "POST", body: JSON.stringify(params) }),

  // Export
  exportSet: (params: {
    soundcloud_only?: boolean;
    genre_filter?: string;
    start_track_id?: number;
    target_minutes?: number;
    arc_type?: string;
    bpm_range?: number;
  }) =>
    fetcher<{
      set: Array<{
        position: number;
        title: string;
        artist: string;
        bpm: number;
        key: string;
        energy: number;
        genre: string;
        soundcloud_url: string;
        transition: string;
        tags?: string[];
      }>;
      total_tracks: number;
      total_duration_minutes: number;
      arc_type: string;
    }>("/api/export-set", { method: "POST", body: JSON.stringify(params) }),
};
