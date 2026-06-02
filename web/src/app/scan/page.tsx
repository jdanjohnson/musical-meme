"use client";

import { useState, useEffect, useRef } from "react";
import { api, type ScanStatus } from "@/lib/api";
import { FolderSearch, Loader2, CheckCircle2, AlertCircle, HardDrive } from "lucide-react";

export default function ScanPage() {
  const [folderPath, setFolderPath] = useState("");
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function handleScan() {
    if (!folderPath.trim()) return;
    setError(null);
    setScanning(true);

    try {
      const status = await api.startScan(folderPath.trim());
      setScanStatus(status);

      pollRef.current = setInterval(async () => {
        try {
          const updated = await api.getScanStatus(status.job_id);
          setScanStatus(updated);

          if (updated.status === "complete" || updated.status === "error") {
            if (pollRef.current) clearInterval(pollRef.current);
            setScanning(false);
          }
        } catch {
          if (pollRef.current) clearInterval(pollRef.current);
          setScanning(false);
        }
      }, 1000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start scan");
      setScanning(false);
    }
  }

  const progress = scanStatus
    ? scanStatus.total_files > 0
      ? (scanStatus.processed_files / scanStatus.total_files) * 100
      : 0
    : 0;

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Scan Library</h1>
        <p className="text-zinc-400 text-sm mt-1">
          Point to your music folder and we&apos;ll analyze every track — BPM, key, energy, the works.
        </p>
      </div>

      {/* Scan input */}
      <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800 space-y-4">
        <div>
          <label className="text-sm text-zinc-400 block mb-2">Music Folder Path</label>
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <HardDrive className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <input
                type="text"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                placeholder="/Users/you/Music/DJ Library"
                className="w-full pl-10 pr-4 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
                onKeyDown={(e) => e.key === "Enter" && handleScan()}
              />
            </div>
            <button
              onClick={handleScan}
              disabled={scanning || !folderPath.trim()}
              className="flex items-center gap-2 px-5 py-2.5 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 rounded-lg text-sm font-medium text-white transition-colors"
            >
              {scanning ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <FolderSearch className="w-4 h-4" />
              )}
              {scanning ? "Scanning..." : "Scan"}
            </button>
          </div>
          <p className="text-xs text-zinc-600 mt-2">
            This is the folder path on the machine running the analyzer backend.
            Subfolders are used as genre labels.
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <AlertCircle className="w-4 h-4 text-red-400" />
            <span className="text-sm text-red-400">{error}</span>
          </div>
        )}
      </div>

      {/* Progress */}
      {scanStatus && (
        <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800 space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              {scanStatus.status === "complete" ? (
                <>
                  <CheckCircle2 className="w-5 h-5 text-green-400" /> Scan Complete
                </>
              ) : scanStatus.status === "error" ? (
                <>
                  <AlertCircle className="w-5 h-5 text-red-400" /> Scan Failed
                </>
              ) : (
                <>
                  <Loader2 className="w-5 h-5 text-purple-400 animate-spin" /> Analyzing...
                </>
              )}
            </h2>
            <span className="text-sm text-zinc-400">
              {scanStatus.processed_files} / {scanStatus.total_files} files
            </span>
          </div>

          {/* Progress bar */}
          <div className="h-3 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${progress}%`,
                backgroundColor:
                  scanStatus.status === "complete"
                    ? "#22c55e"
                    : scanStatus.status === "error"
                    ? "#ef4444"
                    : "#a855f7",
              }}
            />
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold text-green-400">
                {scanStatus.processed_files - scanStatus.skipped_files - scanStatus.error_files}
              </div>
              <div className="text-xs text-zinc-500">Analyzed</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-zinc-400">{scanStatus.skipped_files}</div>
              <div className="text-xs text-zinc-500">Skipped (cached)</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-red-400">{scanStatus.error_files}</div>
              <div className="text-xs text-zinc-500">Errors</div>
            </div>
          </div>

          {/* Current file */}
          {scanStatus.current_file && (
            <div className="text-xs text-zinc-500 truncate">
              Analyzing: {scanStatus.current_file}
            </div>
          )}

          {scanStatus.error_message && (
            <div className="text-sm text-red-400">{scanStatus.error_message}</div>
          )}
        </div>
      )}

      {/* Instructions */}
      <div className="bg-zinc-900/50 rounded-xl p-6 border border-zinc-800/50 space-y-3">
        <h3 className="text-sm font-semibold text-zinc-400">How it works</h3>
        <ul className="space-y-2 text-sm text-zinc-500">
          <li className="flex gap-2">
            <span className="text-purple-400">1.</span>
            Point to your root music folder (e.g. <code className="text-zinc-400">/Music/DJ Library</code>)
          </li>
          <li className="flex gap-2">
            <span className="text-purple-400">2.</span>
            We recursively find all audio files (MP3, WAV, FLAC, AIFF, M4A, OGG)
          </li>
          <li className="flex gap-2">
            <span className="text-purple-400">3.</span>
            Each track is analyzed for BPM, musical key, energy level, loudness, and brightness
          </li>
          <li className="flex gap-2">
            <span className="text-purple-400">4.</span>
            Subfolder names become genre labels (e.g. <code className="text-zinc-400">/House/track.mp3</code> → genre: House)
          </li>
          <li className="flex gap-2">
            <span className="text-purple-400">5.</span>
            Results are cached — re-scanning only processes new or changed files
          </li>
        </ul>
      </div>
    </div>
  );
}
