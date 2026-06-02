"use client";

import { useEffect, useState } from "react";
import { api, type Track } from "@/lib/api";
import { TrackTable } from "@/components/track-table";
import { CAMELOT_COLORS, CAMELOT_TO_KEY, formatDuration } from "@/lib/camelot";
import { Disc3, Trash2, X } from "lucide-react";

export default function LibraryPage() {
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTrack, setSelectedTrack] = useState<Track | null>(null);

  useEffect(() => {
    api.getTracks()
      .then((res) => setTracks(res.tracks))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Disc3 className="w-12 h-12 text-purple-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Library</h1>
        <p className="text-zinc-400 text-sm mt-1">{tracks.length} tracks</p>
      </div>

      <div className="flex gap-6">
        <div className={selectedTrack ? "flex-1" : "w-full"}>
          <TrackTable
            tracks={tracks}
            onTrackSelect={setSelectedTrack}
            selectedTrackId={selectedTrack?.id}
            onDeleteTrack={async (id) => {
              try {
                await api.deleteTrack(id);
                setTracks((prev) => prev.filter((t) => t.id !== id));
                if (selectedTrack?.id === id) setSelectedTrack(null);
              } catch (e) {
                console.error("Failed to delete track", e);
              }
            }}
          />
        </div>

        {selectedTrack && (
          <TrackDetail track={selectedTrack} onClose={() => setSelectedTrack(null)} />
        )}
      </div>
    </div>
  );
}

function TrackDetail({ track, onClose }: { track: Track; onClose: () => void }) {
  return (
    <div className="w-80 bg-zinc-900 rounded-xl border border-zinc-800 p-5 sticky top-0 h-fit space-y-4">
      <div className="flex justify-between items-start">
        <h3 className="text-lg font-bold text-white truncate pr-2">
          {track.title || track.filename}
        </h3>
        <button onClick={onClose} className="text-zinc-500 hover:text-white">
          <X className="w-5 h-5" />
        </button>
      </div>

      {track.artist && <p className="text-sm text-zinc-400">{track.artist}</p>}

      <div className="space-y-3">
        <DetailRow label="BPM" value={track.bpm?.toFixed(1)} confidence={track.bpm_confidence} />
        <DetailRow
          label="Key"
          value={
            <span className="flex items-center gap-2">
              <span
                className="px-2 py-0.5 rounded text-xs font-bold"
                style={{
                  backgroundColor: (CAMELOT_COLORS[track.camelot] || "#666") + "30",
                  color: CAMELOT_COLORS[track.camelot] || "#999",
                }}
              >
                {track.camelot}
              </span>
              <span className="text-zinc-400">{CAMELOT_TO_KEY[track.camelot] || track.key}</span>
            </span>
          }
          confidence={track.key_confidence}
        />
        <DetailRow label="Energy" value={`${track.energy_level}/10`} />
        <DetailRow label="Duration" value={formatDuration(track.duration)} />
        <DetailRow label="Genre" value={track.genre || "—"} />
        <DetailRow label="Format" value={`${track.format} · ${track.sample_rate}Hz`} />
        <DetailRow label="Loudness" value={`${track.loudness} dB`} />
        <DetailRow label="Brightness" value={`${(track.brightness * 100).toFixed(0)}%`} />
      </div>

      <div className="pt-3 border-t border-zinc-800">
        <p className="text-xs text-zinc-500 truncate" title={track.file_path}>
          {track.file_path}
        </p>
      </div>
    </div>
  );
}

function DetailRow({
  label,
  value,
  confidence,
}: {
  label: string;
  value: React.ReactNode;
  confidence?: number;
}) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-xs text-zinc-500">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-sm text-zinc-200">{value}</span>
        {confidence !== undefined && (
          <span
            className={`text-[10px] ${confidence >= 0.7 ? "text-green-500" : confidence >= 0.4 ? "text-yellow-500" : "text-red-500"}`}
          >
            {(confidence * 100).toFixed(0)}%
          </span>
        )}
      </div>
    </div>
  );
}
