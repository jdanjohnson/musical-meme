"use client";

import { useEffect, useState } from "react";
import { api, type LibraryStats } from "@/lib/api";
import { CamelotWheel } from "@/components/camelot-wheel";
import { Disc3, Clock, Music2, Zap, BarChart3 } from "lucide-react";

export default function DashboardPage() {
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getStats()
      .then(setStats)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;
  if (!stats || stats.total_tracks === 0) return <EmptyState />;

  const topGenres = Object.entries(stats.genre_distribution).slice(0, 8);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Library Dashboard</h1>
        <p className="text-zinc-400 text-sm mt-1">
          {stats.total_tracks} tracks analyzed &middot; {stats.total_duration_hours}h of music
        </p>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard icon={Music2} label="Total Tracks" value={stats.total_tracks.toLocaleString()} />
        <StatCard icon={Clock} label="Total Duration" value={`${stats.total_duration_hours}h`} />
        <StatCard icon={Zap} label="Avg BPM" value={stats.avg_bpm.toFixed(1)} />
        <StatCard
          icon={BarChart3}
          label="BPM Range"
          value={`${stats.bpm_range[0].toFixed(0)}–${stats.bpm_range[1].toFixed(0)}`}
        />
      </div>

      {/* Main viz row */}
      <div className="grid grid-cols-2 gap-6">
        {/* Camelot Wheel */}
        <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800">
          <h2 className="text-lg font-semibold text-white mb-4">Key Distribution</h2>
          <div className="flex justify-center">
            <CamelotWheel distribution={stats.camelot_distribution} size={350} />
          </div>
        </div>

        {/* Genre breakdown */}
        <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800">
          <h2 className="text-lg font-semibold text-white mb-4">Genres</h2>
          <div className="space-y-3">
            {topGenres.map(([genre, count]) => {
              const pct = (count / stats.total_tracks) * 100;
              return (
                <div key={genre}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-zinc-300">{genre}</span>
                    <span className="text-zinc-500">{count} tracks ({pct.toFixed(1)}%)</span>
                  </div>
                  <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-purple-500 rounded-full transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* BPM Histogram */}
      <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800">
        <h2 className="text-lg font-semibold text-white mb-4">BPM Distribution</h2>
        <BpmHistogram data={stats.bpm_histogram} />
      </div>

      {/* Energy Distribution */}
      <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800">
        <h2 className="text-lg font-semibold text-white mb-4">Energy Distribution</h2>
        <EnergyHistogram data={stats.energy_distribution} />
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-purple-500/20 rounded-lg">
          <Icon className="w-5 h-5 text-purple-400" />
        </div>
        <div>
          <div className="text-xs text-zinc-500">{label}</div>
          <div className="text-xl font-bold text-white">{value}</div>
        </div>
      </div>
    </div>
  );
}

function BpmHistogram({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...Object.values(data));

  return (
    <div className="flex items-end gap-1 h-40">
      {entries.map(([bucket, count]) => (
        <div key={bucket} className="flex-1 flex flex-col items-center gap-1">
          <div
            className="w-full bg-purple-500/60 rounded-t hover:bg-purple-400/80 transition-colors"
            style={{ height: `${(count / max) * 100}%` }}
            title={`${bucket} BPM: ${count} tracks`}
          />
          <span className="text-[9px] text-zinc-500 rotate-[-45deg] origin-top-left whitespace-nowrap mt-1">
            {bucket}
          </span>
        </div>
      ))}
    </div>
  );
}

function EnergyHistogram({ data }: { data: Record<string, number> }) {
  const max = Math.max(1, ...Object.values(data));
  const levels = Array.from({ length: 10 }, (_, i) => i + 1);
  const colors = ["#22d3ee", "#22d3ee", "#22d3ee", "#a855f7", "#a855f7", "#a855f7", "#f97316", "#f97316", "#ef4444", "#ef4444"];

  return (
    <div className="flex items-end gap-2 h-32">
      {levels.map((level) => {
        const count = data[level] || 0;
        return (
          <div key={level} className="flex-1 flex flex-col items-center gap-1">
            <span className="text-xs text-zinc-500">{count}</span>
            <div
              className="w-full rounded-t transition-colors"
              style={{
                height: `${(count / max) * 100}%`,
                backgroundColor: colors[level - 1] + "80",
                minHeight: count > 0 ? 4 : 0,
              }}
              title={`Energy ${level}: ${count} tracks`}
            />
            <span className="text-xs text-zinc-400 font-mono">{level}</span>
          </div>
        );
      })}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center h-96">
      <Disc3 className="w-12 h-12 text-purple-400 animate-spin" />
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-96 gap-4">
      <p className="text-red-400">Failed to load: {message}</p>
      <p className="text-zinc-500 text-sm">Make sure the analyzer backend is running on port 8000</p>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-96 gap-4">
      <Disc3 className="w-16 h-16 text-zinc-700" />
      <h2 className="text-xl font-bold text-zinc-400">No tracks analyzed yet</h2>
      <p className="text-zinc-500 text-sm">Head to Scan Library to analyze your music folder</p>
    </div>
  );
}
