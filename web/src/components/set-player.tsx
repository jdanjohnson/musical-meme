"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX } from "lucide-react";
import type { SetTrack } from "@/lib/api";
import { CAMELOT_COLORS, formatDuration } from "@/lib/camelot";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const CROSSFADE_SECONDS = 8;

interface SetPlayerProps {
  tracks: SetTrack[];
}

export function SetPlayer({ tracks }: SetPlayerProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const [muted, setMuted] = useState(false);
  const [crossfading, setCrossfading] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const nextAudioRef = useRef<HTMLAudioElement | null>(null);
  const crossfadeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentTrack = tracks[currentIndex]?.track;

  const audioUrl = useCallback(
    (trackId: number) => `${API_BASE}/api/tracks/${trackId}/audio`,
    []
  );

  // Load track when index changes
  useEffect(() => {
    if (!currentTrack) return;
    const audio = audioRef.current;
    if (!audio) return;

    audio.src = audioUrl(currentTrack.id);
    audio.volume = muted ? 0 : volume;
    audio.load();

    if (isPlaying) {
      audio.play().catch(() => {});
    }
  }, [currentIndex, currentTrack]);

  // Update volume
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = muted ? 0 : volume;
    }
  }, [volume, muted]);

  // Time update
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTimeUpdate = () => {
      setCurrentTime(audio.currentTime);
      setDuration(audio.duration || 0);

      // Start crossfade near end
      if (
        audio.duration &&
        audio.currentTime > audio.duration - CROSSFADE_SECONDS &&
        currentIndex < tracks.length - 1 &&
        !crossfading
      ) {
        startCrossfade();
      }
    };

    const onEnded = () => {
      if (currentIndex < tracks.length - 1) {
        setCurrentIndex((i) => i + 1);
      } else {
        setIsPlaying(false);
      }
    };

    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("ended", onEnded);
    return () => {
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("ended", onEnded);
    };
  }, [currentIndex, tracks.length, crossfading]);

  const startCrossfade = useCallback(() => {
    if (crossfading || currentIndex >= tracks.length - 1) return;
    setCrossfading(true);

    const curTrack = tracks[currentIndex]?.track;
    const nextTrack = tracks[currentIndex + 1]?.track;
    if (!nextTrack) return;

    // BPM matching: adjust playback rate so both tracks align to a target BPM
    const curBpm = curTrack?.bpm || 0;
    const nextBpm = nextTrack?.bpm || 0;
    let targetBpm = curBpm;
    if (curBpm && nextBpm) {
      // Target BPM = midpoint, clamped to ±6% stretch max
      targetBpm = (curBpm + nextBpm) / 2;
    }

    const curRate = curBpm && targetBpm ? Math.min(Math.max(targetBpm / curBpm, 0.94), 1.06) : 1;
    const nextRate = nextBpm && targetBpm ? Math.min(Math.max(targetBpm / nextBpm, 0.94), 1.06) : 1;

    const nextAudio = new Audio(audioUrl(nextTrack.id));
    nextAudio.volume = 0;
    nextAudio.playbackRate = nextRate;
    nextAudioRef.current = nextAudio;
    nextAudio.play().catch(() => {});

    const mainAudio = audioRef.current;
    if (mainAudio) mainAudio.playbackRate = curRate;

    const steps = CROSSFADE_SECONDS * 10;
    let step = 0;

    crossfadeTimerRef.current = setInterval(() => {
      step++;
      const progress = step / steps;

      if (mainAudio) {
        mainAudio.volume = Math.max(0, (1 - progress) * (muted ? 0 : volume));
      }
      nextAudio.volume = progress * (muted ? 0 : volume);

      if (step >= steps) {
        if (crossfadeTimerRef.current) clearInterval(crossfadeTimerRef.current);
        if (mainAudio) {
          mainAudio.pause();
          mainAudio.playbackRate = 1;
        }
        // Reset to normal speed after transition
        nextAudio.playbackRate = 1;

        audioRef.current = nextAudio;
        nextAudioRef.current = null;
        setCurrentIndex((i) => i + 1);
        setCrossfading(false);
      }
    }, 100);
  }, [crossfading, currentIndex, tracks, volume, muted, audioUrl]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (crossfadeTimerRef.current) clearInterval(crossfadeTimerRef.current);
      audioRef.current?.pause();
      nextAudioRef.current?.pause();
    };
  }, []);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;

    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
    } else {
      audio.play().catch(() => {});
      setIsPlaying(true);
    }
  }, [isPlaying]);

  const skipTo = useCallback(
    (index: number) => {
      if (index < 0 || index >= tracks.length) return;
      if (crossfadeTimerRef.current) {
        clearInterval(crossfadeTimerRef.current);
        setCrossfading(false);
      }
      nextAudioRef.current?.pause();
      nextAudioRef.current = null;
      setCurrentIndex(index);
    },
    [tracks.length]
  );

  const seek = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const audio = audioRef.current;
    if (!audio || !audio.duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    audio.currentTime = pct * audio.duration;
  }, []);

  const formatTime = (s: number) => {
    if (!s || isNaN(s)) return "0:00";
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  if (tracks.length === 0) return null;

  return (
    <div className="bg-zinc-900 rounded-xl border border-zinc-800 overflow-hidden">
      <div className="p-4 border-b border-zinc-800 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <Volume2 className="w-5 h-5 text-purple-400" />
          Set Preview Player
        </h2>
        {crossfading && (
          <span className="text-xs text-purple-400 animate-pulse">Crossfading...</span>
        )}
      </div>

      {/* Now playing */}
      {currentTrack && (
        <div className="px-4 py-3 bg-zinc-800/50">
          <div className="flex items-center gap-3">
            <span className="text-xs text-zinc-500 font-mono w-6">
              {currentIndex + 1}/{tracks.length}
            </span>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-white truncate">
                {currentTrack.title || currentTrack.filename}
              </div>
              <div className="text-xs text-zinc-500">
                {currentTrack.bpm?.toFixed(1)} BPM
                <span
                  className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-bold"
                  style={{
                    backgroundColor: (CAMELOT_COLORS[currentTrack.camelot] || "#666") + "30",
                    color: CAMELOT_COLORS[currentTrack.camelot] || "#999",
                  }}
                >
                  {currentTrack.camelot}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Progress bar */}
      <div className="px-4 py-2">
        <div
          className="h-1.5 bg-zinc-700 rounded-full cursor-pointer group"
          onClick={seek}
        >
          <div
            className="h-full bg-purple-500 rounded-full relative group-hover:bg-purple-400 transition-colors"
            style={{ width: `${duration ? (currentTime / duration) * 100 : 0}%` }}
          >
            <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        </div>
        <div className="flex justify-between text-[10px] text-zinc-500 mt-1">
          <span>{formatTime(currentTime)}</span>
          <span>{formatTime(duration)}</span>
        </div>
      </div>

      {/* Controls */}
      <div className="px-4 pb-4 flex items-center gap-4 justify-center">
        <button
          onClick={() => skipTo(currentIndex - 1)}
          disabled={currentIndex === 0}
          className="text-zinc-400 hover:text-white disabled:text-zinc-700 transition-colors"
        >
          <SkipBack className="w-5 h-5" />
        </button>

        <button
          onClick={togglePlay}
          className="w-10 h-10 rounded-full bg-purple-600 hover:bg-purple-500 flex items-center justify-center text-white transition-colors"
        >
          {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
        </button>

        <button
          onClick={() => skipTo(currentIndex + 1)}
          disabled={currentIndex >= tracks.length - 1}
          className="text-zinc-400 hover:text-white disabled:text-zinc-700 transition-colors"
        >
          <SkipForward className="w-5 h-5" />
        </button>

        {/* Volume */}
        <div className="flex items-center gap-2 ml-4">
          <button
            onClick={() => setMuted(!muted)}
            className="text-zinc-400 hover:text-white transition-colors"
          >
            {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
          </button>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={muted ? 0 : volume}
            onChange={(e) => {
              setVolume(Number(e.target.value));
              if (muted) setMuted(false);
            }}
            className="w-20 accent-purple-500"
          />
        </div>
      </div>

      {/* Mini tracklist */}
      <div className="border-t border-zinc-800 max-h-48 overflow-y-auto">
        {tracks.map((st, i) => (
          <button
            key={`${st.track.id}-${i}`}
            onClick={() => {
              skipTo(i);
              if (!isPlaying) {
                setTimeout(() => {
                  audioRef.current?.play().catch(() => {});
                  setIsPlaying(true);
                }, 100);
              }
            }}
            className={`w-full flex items-center gap-3 px-4 py-2 text-left hover:bg-zinc-800/50 transition-colors ${
              i === currentIndex ? "bg-purple-500/10 border-l-2 border-purple-500" : ""
            }`}
          >
            <span className="text-xs text-zinc-600 font-mono w-5">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <div className={`text-xs truncate ${i === currentIndex ? "text-purple-300 font-medium" : "text-zinc-400"}`}>
                {st.track.title || st.track.filename}
              </div>
            </div>
            <span className="text-[10px] text-zinc-600">{formatDuration(st.track.duration)}</span>
            {st.transition && (
              <span className={`text-[10px] font-bold ${
                st.transition.overall_score >= 0.8 ? "text-green-400" :
                st.transition.overall_score >= 0.6 ? "text-yellow-400" : "text-orange-400"
              }`}>
                {(st.transition.overall_score * 100).toFixed(0)}%
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Hidden audio element */}
      <audio ref={audioRef} preload="auto" />
    </div>
  );
}
