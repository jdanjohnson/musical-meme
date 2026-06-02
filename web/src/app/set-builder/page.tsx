"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type Track, type SetTrack, type ArcType, type TransitionScore } from "@/lib/api";
import { TrackTable } from "@/components/track-table";
import { EnergyArc } from "@/components/energy-arc";
import { CAMELOT_COLORS, formatDuration } from "@/lib/camelot";
import { SetPlayer } from "@/components/set-player";
import { Disc3, Wand2, Plus, Trash2, GripVertical, ArrowRight, Download, FolderDown, ExternalLink, Music, AlertTriangle, Search, Sparkles } from "lucide-react";

export default function SetBuilderPage() {
  const [allTracks, setAllTracks] = useState<Track[]>([]);
  const [setTracks, setSetTracks] = useState<SetTrack[]>([]);
  const [arcTypes, setArcTypes] = useState<ArcType[]>([]);
  const [selectedArc, setSelectedArc] = useState("standard");
  const [targetMinutes, setTargetMinutes] = useState(60);
  const [bpmRange, setBpmRange] = useState(8);
  const [genreFilter, setGenreFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [suggestions, setSuggestions] = useState<Array<{ track: Track; score: TransitionScore }>>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [gaps, setGaps] = useState<Array<{
    type: string; severity: string; position: number;
    time_in_set: string; message: string; suggestion: string;
  }>>([]);
  const [analyzingGaps, setAnalyzingGaps] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<string | null>(null);
  const [vibeText, setVibeText] = useState("");
  const [vibeResult, setVibeResult] = useState<{ description: string; energy_range: [number, number]; bpm_range: [number, number]; keywords_matched: string[] } | null>(null);

  useEffect(() => {
    Promise.all([api.getTracks(), api.getArcTypes()])
      .then(([tracksRes, arcsRes]) => {
        setAllTracks(tracksRes.tracks);
        setArcTypes(arcsRes.arc_types);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const genres = [...new Set(allTracks.map((t) => t.genre).filter(Boolean))] as string[];
  const totalDurationRaw = setTracks.reduce((sum, t) => sum + t.track.duration, 0);
  const totalDuration = totalDurationRaw;

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setVibeResult(null);
    try {
      const result = await api.generateSet({
        target_minutes: targetMinutes,
        arc_type: selectedArc,
        bpm_range: bpmRange,
        genre_filter: genreFilter || undefined,
        vibe: vibeText || undefined,
      });
      setSetTracks(result.set);
      setShowSuggestions(false);
      if (result.vibe) setVibeResult(result.vibe);
    } catch (e) {
      console.error(e);
    } finally {
      setGenerating(false);
    }
  }, [targetMinutes, selectedArc, bpmRange, genreFilter, vibeText]);

  const handleAddTrack = useCallback(
    async (track: Track) => {
      const position = setTracks.length;
      const positionInSet = setTracks.length > 0 ? position / Math.max(1, Math.ceil(targetMinutes / 5)) : 0;

      let transition: TransitionScore | null = null;
      if (setTracks.length > 0) {
        const lastTrack = setTracks[setTracks.length - 1].track;
        try {
          const result = await api.scoreTransition(lastTrack.id, track.id, positionInSet);
          transition = result.score;
        } catch (e) {
          console.error(e);
        }
      }

      setSetTracks((prev) => [...prev, { position: prev.length + 1, track, transition }]);
      setShowSuggestions(false);
    },
    [setTracks, targetMinutes]
  );

  const handleRemoveTrack = useCallback((index: number) => {
    setSetTracks((prev) => {
      const next = [...prev];
      next.splice(index, 1);
      return next.map((t, i) => ({ ...t, position: i + 1 }));
    });
  }, []);

  const handleSuggestNext = useCallback(async () => {
    if (setTracks.length === 0) return;
    const lastTrack = setTracks[setTracks.length - 1].track;
    const positionInSet = setTracks.length / Math.max(1, Math.ceil(targetMinutes / 5));
    const excludeIds = setTracks.map((t) => t.track.id);

    try {
      const result = await api.suggestNext({
        track_id: lastTrack.id,
        position_in_set: Math.min(1, positionInSet),
        arc_type: selectedArc,
        bpm_range: bpmRange,
        exclude_ids: excludeIds,
        limit: 15,
      });
      setSuggestions(result.suggestions);
      setShowSuggestions(true);
    } catch (e) {
      console.error(e);
    }
  }, [setTracks, targetMinutes, selectedArc, bpmRange]);

  const handleAnalyzeGaps = useCallback(async () => {
    setAnalyzingGaps(true);
    try {
      const result = await api.analyzeGaps({
        arc_type: selectedArc,
        target_minutes: targetMinutes,
        bpm_range: bpmRange,
      });
      setGaps(result.gaps);
    } catch (e) {
      console.error(e);
    } finally {
      setAnalyzingGaps(false);
    }
  }, [selectedArc, targetMinutes, bpmRange]);

  const handleExportText = useCallback(() => {
    const lines = [
      `DJ Set — ${setTracks.length} tracks — ${formatDuration(totalDurationRaw)}`,
      `Arc: ${arcTypes.find((a) => a.id === selectedArc)?.name || selectedArc}`,
      "",
      "# | Track | Artist | BPM | Key | Energy | Transition | SoundCloud",
      "-".repeat(100),
    ];

    for (const st of setTracks) {
      const t = st.track;
      const scLink = t.soundcloud_url || "";
      const transition = st.transition?.harmonic_move || "";
      lines.push(
        `${st.position}. ${t.title || t.filename} | ${t.artist || "?"} | ${t.bpm?.toFixed(1)} | ${t.camelot} | ${t.energy_level}/10 | ${transition} | ${scLink}`
      );
    }

    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dj-set-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }, [setTracks, selectedArc, arcTypes]);

  const handleExportXml = useCallback(() => {
    const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    const indent = (n: number) => "  ".repeat(n);

    const lines: string[] = [
      '<?xml version="1.0" encoding="UTF-8"?>',
      '<djset',
      `  generated="${new Date().toISOString()}"`,
      `  total_tracks="${setTracks.length}"`,
      `  total_duration_seconds="${Math.round(totalDurationRaw)}"`,
      `  total_duration_formatted="${formatDuration(totalDurationRaw)}"`,
      `  arc_type="${esc(selectedArc)}"`,
    ];
    if (vibeResult) {
      lines.push(`  vibe_description="${esc(vibeResult.description)}"`);
      lines.push(`  vibe_energy_range="${vibeResult.energy_range[0]}-${vibeResult.energy_range[1]}"`);
      lines.push(`  vibe_bpm_range="${vibeResult.bpm_range[0]}-${vibeResult.bpm_range[1]}"`);
      lines.push(`  vibe_keywords="${esc(vibeResult.keywords_matched.join(", "))}"`);
    }
    lines.push('>');

    for (const st of setTracks) {
      const t = st.track;
      const tr = st.transition;
      lines.push(`${indent(1)}<track position="${st.position}">`);
      lines.push(`${indent(2)}<title>${esc(t.title || t.filename)}</title>`);
      lines.push(`${indent(2)}<artist>${esc(t.artist || "Unknown")}</artist>`);
      lines.push(`${indent(2)}<filename>${esc(t.filename)}</filename>`);
      lines.push(`${indent(2)}<bpm>${t.bpm?.toFixed(2) || "0"}</bpm>`);
      lines.push(`${indent(2)}<key musical="${esc(t.key || "")}" camelot="${esc(t.camelot || "")}" />`);
      lines.push(`${indent(2)}<energy level="${t.energy_level}" raw="${t.energy?.toFixed(4) || "0"}" />`);
      lines.push(`${indent(2)}<duration seconds="${Math.round(t.duration)}" formatted="${formatDuration(t.duration)}" />`);
      lines.push(`${indent(2)}<genre>${esc(t.genre || "Unknown")}</genre>`);
      lines.push(`${indent(2)}<vocals detected="${t.has_vocals}" confidence="${(t.vocal_confidence || 0).toFixed(3)}" />`);
      lines.push(`${indent(2)}<brightness>${(t.brightness || 0).toFixed(4)}</brightness>`);
      lines.push(`${indent(2)}<cue_points intro_end="${t.intro_end_sec || 0}" outro_start="${t.outro_start_sec || 0}" phrase_length="${t.phrase_length_sec || 0}" />`);
      if (t.soundcloud_url) {
        lines.push(`${indent(2)}<soundcloud_url>${esc(t.soundcloud_url)}</soundcloud_url>`);
      }
      if (tr) {
        lines.push(`${indent(2)}<transition>`);
        lines.push(`${indent(3)}<harmonic_score>${tr.harmonic_score.toFixed(4)}</harmonic_score>`);
        lines.push(`${indent(3)}<bpm_score>${tr.bpm_score.toFixed(4)}</bpm_score>`);
        lines.push(`${indent(3)}<energy_score>${tr.energy_score.toFixed(4)}</energy_score>`);
        lines.push(`${indent(3)}<overall_score>${tr.overall_score.toFixed(4)}</overall_score>`);
        lines.push(`${indent(3)}<harmonic_move>${esc(tr.harmonic_move)}</harmonic_move>`);
        lines.push(`${indent(3)}<bpm_delta>${tr.bpm_delta.toFixed(2)}</bpm_delta>`);
        lines.push(`${indent(3)}<energy_delta>${tr.energy_delta}</energy_delta>`);
        lines.push(`${indent(3)}<explanation>${esc(tr.explanation)}</explanation>`);
        lines.push(`${indent(2)}</transition>`);
      }
      lines.push(`${indent(1)}</track>`);
    }

    // Summary stats for AI assessment
    const bpms = setTracks.map(st => st.track.bpm).filter(Boolean);
    const energies = setTracks.map(st => st.track.energy_level).filter(Boolean);
    const scores = setTracks.map(st => st.transition?.overall_score).filter((s): s is number => s != null);
    lines.push(`${indent(1)}<summary>`);
    lines.push(`${indent(2)}<bpm_range min="${Math.min(...bpms).toFixed(1)}" max="${Math.max(...bpms).toFixed(1)}" avg="${(bpms.reduce((a, b) => a + b, 0) / bpms.length).toFixed(1)}" />`);
    lines.push(`${indent(2)}<energy_range min="${Math.min(...energies)}" max="${Math.max(...energies)}" avg="${(energies.reduce((a, b) => a + b, 0) / energies.length).toFixed(1)}" />`);
    if (scores.length > 0) {
      lines.push(`${indent(2)}<transition_scores avg="${(scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(4)}" min="${Math.min(...scores).toFixed(4)}" max="${Math.max(...scores).toFixed(4)}" />`);
    }
    const keys = setTracks.map(st => st.track.camelot).filter(Boolean);
    const keyDist: Record<string, number> = {};
    keys.forEach(k => { keyDist[k] = (keyDist[k] || 0) + 1; });
    lines.push(`${indent(2)}<key_distribution>${esc(JSON.stringify(keyDist))}</key_distribution>`);
    lines.push(`${indent(1)}</summary>`);

    lines.push('</djset>');

    const blob = new Blob([lines.join("\n")], { type: "application/xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dj-set-${new Date().toISOString().slice(0, 10)}.xml`;
    a.click();
    URL.revokeObjectURL(url);
  }, [setTracks, selectedArc, vibeResult, totalDurationRaw]);

  const handleExportFolder = useCallback(async () => {
    if (setTracks.length === 0) return;
    setExporting(true);
    setExportResult(null);
    try {
      const result = await api.exportSetFolder({
        track_ids: setTracks.map((st) => st.track.id),
        name: `DJ Set - ${arcTypes.find((a) => a.id === selectedArc)?.name || selectedArc} - ${new Date().toISOString().slice(0, 10)}`,
      });
      setExportResult(`${result.tracks_copied} tracks copied to: ${result.export_path}`);
    } catch (e) {
      console.error(e);
      setExportResult("Export failed — is the backend running?");
    } finally {
      setExporting(false);
    }
  }, [setTracks, selectedArc, arcTypes]);

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
        <h1 className="text-2xl font-bold text-white">Set Builder</h1>
        <p className="text-zinc-400 text-sm mt-1">
          Plan your DJ set with music theory
        </p>
      </div>

      {/* Controls */}
      <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Energy Arc</label>
            <select
              value={selectedArc}
              onChange={(e) => setSelectedArc(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200"
            >
              {arcTypes.map((arc) => (
                <option key={arc.id} value={arc.id}>
                  {arc.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs text-zinc-500 block mb-1">Target Duration (min)</label>
            <input
              type="number"
              value={targetMinutes}
              onChange={(e) => setTargetMinutes(Number(e.target.value))}
              min={15}
              max={480}
              className="w-24 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200"
            />
          </div>

          <div>
            <label className="text-xs text-zinc-500 block mb-1">BPM Range (±)</label>
            <input
              type="number"
              value={bpmRange}
              onChange={(e) => setBpmRange(Number(e.target.value))}
              min={1}
              max={30}
              className="w-20 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200"
            />
          </div>

          <div>
            <label className="text-xs text-zinc-500 block mb-1">Genre Filter</label>
            <select
              value={genreFilter}
              onChange={(e) => setGenreFilter(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200"
            >
              <option value="">All genres</option>
              {genres.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </div>

          <div className="flex-1 min-w-[200px]">
            <label className="text-xs text-zinc-500 block mb-1">Describe your vibe</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={vibeText}
                onChange={(e) => setVibeText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !generating) handleGenerate(); }}
                placeholder='e.g. "chill indie sunset vibes" or "high energy pride night"'
                className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-purple-500"
              />
              <button
                onClick={handleGenerate}
                disabled={generating || allTracks.length === 0}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 rounded-lg text-sm font-medium text-white transition-colors whitespace-nowrap"
              >
                {vibeText.trim() ? <Sparkles className="w-4 h-4" /> : <Wand2 className="w-4 h-4" />}
                {generating ? "Generating..." : vibeText.trim() ? "Vibe Generate" : "Auto-Generate"}
              </button>
            </div>
          </div>

          {setTracks.length > 0 && (
            <>
              <button
                onClick={handleExportText}
                className="flex items-center gap-2 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-sm font-medium text-zinc-200 transition-colors"
              >
                <Download className="w-4 h-4" />
                Export .txt
              </button>
              <button
                onClick={handleExportXml}
                className="flex items-center gap-2 px-4 py-2 bg-blue-700/60 hover:bg-blue-600/60 rounded-lg text-sm font-medium text-blue-200 transition-colors"
              >
                <Download className="w-4 h-4" />
                Export .xml
              </button>
              <button
                onClick={handleExportFolder}
                disabled={exporting}
                className="flex items-center gap-2 px-4 py-2 bg-emerald-700/60 hover:bg-emerald-600/60 disabled:opacity-50 rounded-lg text-sm font-medium text-emerald-200 transition-colors"
              >
                <FolderDown className="w-4 h-4" />
                {exporting ? "Copying..." : "Export Folder"}
              </button>
            </>
          )}
        </div>

        {arcTypes.find((a) => a.id === selectedArc) && (
          <p className="text-xs text-zinc-500 mt-2">
            {arcTypes.find((a) => a.id === selectedArc)!.description}
          </p>
        )}

        {exportResult && (
          <div className="mt-2 px-3 py-2 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs text-emerald-300">
            {exportResult}
          </div>
        )}

        {vibeResult && (
          <div className="mt-2 px-3 py-2 bg-purple-500/10 border border-purple-500/20 rounded-lg text-xs text-purple-300 flex items-center gap-3">
            <Sparkles className="w-3.5 h-3.5 shrink-0" />
            <span>
              Vibe: <strong>&quot;{vibeResult.description}&quot;</strong>
              {" "}&mdash; Energy {vibeResult.energy_range[0]}-{vibeResult.energy_range[1]}/10, BPM {vibeResult.bpm_range[0]}-{vibeResult.bpm_range[1]}
              {vibeResult.keywords_matched.length > 0 && (
                <span className="text-zinc-500 ml-1">
                  (matched: {vibeResult.keywords_matched.join(", ")})
                </span>
              )}
            </span>
          </div>
        )}

        {/* Quick presets */}
        <div className="flex gap-2 mt-3 flex-wrap">
          <button
            onClick={() => { setSelectedArc("pride_night"); setTargetMinutes(240); }}
            className="px-3 py-1 bg-gradient-to-r from-red-500/20 via-purple-500/20 to-blue-500/20 border border-purple-500/30 rounded-full text-xs text-purple-300 hover:border-purple-400/50 transition-colors"
          >
            Pride Night (4hr)
          </button>
          <button
            onClick={() => { setSelectedArc("sexy_groovy"); setTargetMinutes(180); }}
            className="px-3 py-1 bg-pink-500/10 border border-pink-500/20 rounded-full text-xs text-pink-300 hover:border-pink-400/40 transition-colors"
          >
            Sexy & Groovy
          </button>
          <button
            onClick={() => { setSelectedArc("long_build"); setTargetMinutes(300); }}
            className="px-3 py-1 bg-amber-500/10 border border-amber-500/20 rounded-full text-xs text-amber-300 hover:border-amber-400/40 transition-colors"
          >
            Long Build (5hr)
          </button>
        </div>
      </div>

      {/* Energy Arc Visualization */}
      {setTracks.length > 1 && (
        <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-lg font-semibold text-white">Energy Arc</h2>
            <span className="text-sm text-zinc-400">
              {setTracks.length} tracks &middot; {formatDuration(totalDuration)} &middot; target {targetMinutes}min
            </span>
          </div>
          <EnergyArc tracks={setTracks} width={700} height={180} />
        </div>
      )}

      {/* Set Player */}
      {setTracks.length > 0 && <SetPlayer tracks={setTracks} />}

      {/* Set Tracklist */}
      <div className="bg-zinc-900 rounded-xl border border-zinc-800">
        <div className="p-5 border-b border-zinc-800 flex justify-between items-center">
          <h2 className="text-lg font-semibold text-white">
            Tracklist
            {setTracks.length > 0 && (
              <span className="text-sm text-zinc-500 ml-2">
                ({setTracks.length} tracks, {formatDuration(totalDuration)})
              </span>
            )}
          </h2>
          <div className="flex gap-2">
            {setTracks.length > 0 && (
              <button
                onClick={handleSuggestNext}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-xs text-zinc-300 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" /> Suggest Next
              </button>
            )}
          </div>
        </div>

        {setTracks.length === 0 ? (
          <div className="p-8 text-center text-zinc-500">
            <p>No tracks in set yet.</p>
            <p className="text-sm mt-1">Use Auto-Generate or pick tracks from your library below.</p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800/50">
            {setTracks.map((setTrack, index) => (
              <SetTrackRow
                key={`${setTrack.track.id}-${index}`}
                setTrack={setTrack}
                index={index}
                onRemove={() => handleRemoveTrack(index)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Suggestions panel */}
      {showSuggestions && suggestions.length > 0 && (
        <div className="bg-zinc-900 rounded-xl p-5 border border-purple-500/30">
          <h2 className="text-lg font-semibold text-white mb-3">
            Suggested Next Tracks
          </h2>
          <div className="space-y-2">
            {suggestions.map(({ track, score }) => (
              <div
                key={track.id}
                onClick={() => handleAddTrack(track)}
                className="flex items-center gap-4 p-3 bg-zinc-800/50 rounded-lg hover:bg-zinc-800 cursor-pointer transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-zinc-200 truncate">
                    {track.title || track.filename}
                  </div>
                  <div className="text-xs text-zinc-500">
                    {track.genre} &middot; {track.bpm?.toFixed(1)} BPM
                  </div>
                </div>

                <span
                  className="px-2 py-0.5 rounded text-xs font-bold shrink-0"
                  style={{
                    backgroundColor: (CAMELOT_COLORS[track.camelot] || "#666") + "30",
                    color: CAMELOT_COLORS[track.camelot] || "#999",
                  }}
                >
                  {track.camelot}
                </span>

                <span className={`text-sm font-bold shrink-0 ${scoreColorClass(score.overall_score)}`}>
                  {(score.overall_score * 100).toFixed(0)}%
                </span>

                <div className="text-xs text-zinc-500 max-w-[250px] truncate shrink-0">
                  {score.harmonic_move}
                </div>

                <Plus className="w-4 h-4 text-purple-400 shrink-0" />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Gap Analysis */}
      {setTracks.length > 2 && (
        <div className="bg-zinc-900 rounded-xl border border-zinc-800">
          <div className="p-5 border-b border-zinc-800 flex justify-between items-center">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Search className="w-5 h-5 text-amber-400" />
              Vibe Gap Analysis
            </h2>
            <button
              onClick={handleAnalyzeGaps}
              disabled={analyzingGaps}
              className="flex items-center gap-2 px-3 py-1.5 bg-amber-600/20 hover:bg-amber-600/30 border border-amber-500/30 rounded-lg text-xs text-amber-300 transition-colors"
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              {analyzingGaps ? "Analyzing..." : "Find Gaps"}
            </button>
          </div>

          {gaps.length === 0 ? (
            <div className="p-6 text-center text-zinc-500 text-sm">
              Click &quot;Find Gaps&quot; to analyze your set for energy, harmonic, and BPM holes
            </div>
          ) : (
            <div className="divide-y divide-zinc-800/50">
              {gaps.map((gap, i) => (
                <div key={i} className="px-5 py-3 flex items-start gap-3">
                  <span className={`mt-0.5 px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                    gap.severity === "high" ? "bg-red-500/20 text-red-400" :
                    gap.severity === "medium" ? "bg-amber-500/20 text-amber-400" :
                    "bg-blue-500/20 text-blue-400"
                  }`}>
                    {gap.type}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-zinc-300">{gap.message}</div>
                    <div className="text-xs text-purple-400 mt-1">💡 {gap.suggestion}</div>
                  </div>
                  <span className="text-xs text-zinc-500 shrink-0">@{gap.time_in_set}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Full library for manual picking */}
      <div className="bg-zinc-900 rounded-xl p-5 border border-zinc-800">
        <h2 className="text-lg font-semibold text-white mb-3">Pick from Library</h2>
        <TrackTable tracks={allTracks} onTrackSelect={handleAddTrack} compact />
      </div>
    </div>
  );
}

function SetTrackRow({
  setTrack,
  index,
  onRemove,
}: {
  setTrack: SetTrack;
  index: number;
  onRemove: () => void;
}) {
  const { track, transition } = setTrack;

  return (
    <div className="flex items-center gap-3 px-5 py-3 hover:bg-zinc-800/30 group">
      <GripVertical className="w-4 h-4 text-zinc-700 group-hover:text-zinc-500" />

      <span className="text-xs text-zinc-600 font-mono w-6">{index + 1}</span>

      {/* Transition indicator */}
      {transition && (
        <div className="flex items-center gap-1">
          <ArrowRight className="w-3 h-3 text-zinc-600" />
          <span className={`text-xs font-bold ${scoreColorClass(transition.overall_score)}`}>
            {(transition.overall_score * 100).toFixed(0)}%
          </span>
        </div>
      )}

      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-zinc-200 truncate">
          {track.title || track.filename}
        </div>
        {transition && (
          <div className="text-[11px] text-zinc-500 truncate">{transition.harmonic_move}</div>
        )}
      </div>

      <span className="text-xs text-zinc-400">{track.genre}</span>

      <span className="text-xs font-mono text-zinc-400">{track.bpm?.toFixed(1)}</span>

      <span
        className="px-2 py-0.5 rounded text-xs font-bold"
        style={{
          backgroundColor: (CAMELOT_COLORS[track.camelot] || "#666") + "30",
          color: CAMELOT_COLORS[track.camelot] || "#999",
        }}
      >
        {track.camelot}
      </span>

      <span className="text-xs font-mono text-zinc-400 w-12 text-right">
        {formatDuration(track.duration)}
      </span>

      {track.soundcloud_url && (
        <a
          href={track.soundcloud_url}
          target="_blank"
          rel="noopener noreferrer"
          className="opacity-0 group-hover:opacity-100 text-orange-400 hover:text-orange-300 transition"
          title="Open on SoundCloud"
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink className="w-4 h-4" />
        </a>
      )}

      <button
        onClick={onRemove}
        className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 transition"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
}

function scoreColorClass(score: number): string {
  if (score >= 0.8) return "text-green-400";
  if (score >= 0.6) return "text-yellow-400";
  if (score >= 0.4) return "text-orange-400";
  return "text-red-400";
}
