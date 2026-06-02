"use client";

import { useState, useMemo } from "react";
import type { Track, TransitionScore } from "@/lib/api";
import { CAMELOT_COLORS, formatDuration } from "@/lib/camelot";
import { ChevronUp, ChevronDown, Music2 } from "lucide-react";

interface TrackTableProps {
  tracks: Track[];
  onTrackSelect?: (track: Track) => void;
  selectedTrackId?: number | null;
  scores?: Map<number, TransitionScore>;
  compact?: boolean;
}

type SortKey = "filename" | "bpm" | "camelot" | "energy_level" | "genre" | "duration" | "key";
type SortDir = "asc" | "desc";

export function TrackTable({ tracks, onTrackSelect, selectedTrackId, scores, compact }: TrackTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("filename");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    let result = tracks;
    if (filter) {
      const q = filter.toLowerCase();
      result = result.filter(
        (t) =>
          t.filename.toLowerCase().includes(q) ||
          (t.genre || "").toLowerCase().includes(q) ||
          (t.camelot || "").toLowerCase().includes(q) ||
          (t.artist || "").toLowerCase().includes(q)
      );
    }
    result.sort((a, b) => {
      const aVal = a[sortKey] ?? "";
      const bVal = b[sortKey] ?? "";
      const cmp = typeof aVal === "number" && typeof bVal === "number" ? aVal - bVal : String(aVal).localeCompare(String(bVal));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return result;
  }, [tracks, filter, sortKey, sortDir]);

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return null;
    return sortDir === "asc" ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />;
  };

  return (
    <div>
      <input
        type="text"
        placeholder="Filter tracks..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="w-full mb-3 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
      />

      <div className="overflow-auto max-h-[600px] rounded-lg border border-zinc-800">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900 sticky top-0 z-10">
            <tr>
              {!compact && <th className="w-8 px-3 py-2" />}
              <th className="text-left px-3 py-2 cursor-pointer hover:text-purple-300" onClick={() => handleSort("filename")}>
                <span className="flex items-center gap-1">Track <SortIcon col="filename" /></span>
              </th>
              {!compact && (
                <th className="text-left px-3 py-2 cursor-pointer hover:text-purple-300" onClick={() => handleSort("genre")}>
                  <span className="flex items-center gap-1">Genre <SortIcon col="genre" /></span>
                </th>
              )}
              <th className="text-center px-3 py-2 cursor-pointer hover:text-purple-300" onClick={() => handleSort("bpm")}>
                <span className="flex items-center gap-1 justify-center">BPM <SortIcon col="bpm" /></span>
              </th>
              <th className="text-center px-3 py-2 cursor-pointer hover:text-purple-300" onClick={() => handleSort("camelot")}>
                <span className="flex items-center gap-1 justify-center">Key <SortIcon col="camelot" /></span>
              </th>
              <th className="text-center px-3 py-2 cursor-pointer hover:text-purple-300" onClick={() => handleSort("energy_level")}>
                <span className="flex items-center gap-1 justify-center">Energy <SortIcon col="energy_level" /></span>
              </th>
              <th className="text-right px-3 py-2 cursor-pointer hover:text-purple-300" onClick={() => handleSort("duration")}>
                <span className="flex items-center gap-1 justify-end">Duration <SortIcon col="duration" /></span>
              </th>
              {scores && <th className="text-center px-3 py-2">Score</th>}
            </tr>
          </thead>
          <tbody>
            {filtered.map((track) => {
              const score = scores?.get(track.id);
              const isSelected = selectedTrackId === track.id;
              return (
                <tr
                  key={track.id}
                  onClick={() => onTrackSelect?.(track)}
                  className={`cursor-pointer border-b border-zinc-800/50 transition-colors ${
                    isSelected ? "bg-purple-500/20" : "hover:bg-zinc-800/50"
                  }`}
                >
                  {!compact && (
                    <td className="px-3 py-2">
                      <Music2 className="w-4 h-4 text-zinc-600" />
                    </td>
                  )}
                  <td className="px-3 py-2">
                    <div className="font-medium text-zinc-200 truncate max-w-[200px]">
                      {track.title || track.filename}
                    </div>
                    {track.artist && (
                      <div className="text-xs text-zinc-500">{track.artist}</div>
                    )}
                  </td>
                  {!compact && (
                    <td className="px-3 py-2 text-zinc-400 text-xs">{track.genre || "—"}</td>
                  )}
                  <td className="px-3 py-2 text-center font-mono text-xs">{track.bpm?.toFixed(1)}</td>
                  <td className="px-3 py-2 text-center">
                    <span
                      className="px-2 py-0.5 rounded text-xs font-bold"
                      style={{
                        backgroundColor: (CAMELOT_COLORS[track.camelot] || "#666") + "30",
                        color: CAMELOT_COLORS[track.camelot] || "#999",
                      }}
                    >
                      {track.camelot}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-center">
                    <EnergyBar level={track.energy_level} />
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-zinc-400">
                    {formatDuration(track.duration)}
                  </td>
                  {scores && (
                    <td className="px-3 py-2 text-center">
                      {score ? (
                        <span className={`text-xs font-bold ${scoreColorClass(score.overall_score)}`}>
                          {(score.overall_score * 100).toFixed(0)}%
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center py-8 text-zinc-500">No tracks found</div>
        )}
      </div>
      <div className="mt-2 text-xs text-zinc-500">
        {filtered.length} of {tracks.length} tracks
      </div>
    </div>
  );
}

function EnergyBar({ level }: { level: number }) {
  const bars = Array.from({ length: 10 }, (_, i) => i < level);
  return (
    <div className="flex gap-px justify-center" title={`Energy: ${level}/10`}>
      {bars.map((active, i) => (
        <div
          key={i}
          className="w-1.5 h-3 rounded-sm"
          style={{
            backgroundColor: active
              ? i < 3 ? "#22d3ee" : i < 6 ? "#a855f7" : i < 8 ? "#f97316" : "#ef4444"
              : "rgba(255,255,255,0.08)",
          }}
        />
      ))}
    </div>
  );
}

function scoreColorClass(score: number): string {
  if (score >= 0.8) return "text-green-400";
  if (score >= 0.6) return "text-yellow-400";
  if (score >= 0.4) return "text-orange-400";
  return "text-red-400";
}
