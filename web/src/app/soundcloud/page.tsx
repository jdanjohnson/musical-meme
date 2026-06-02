"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api, type SCImportStatus } from "@/lib/api";
import {
  Cloud,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Download,
  Key,
  Music,
  Search,
} from "lucide-react";

export default function SoundCloudPage() {
  const [connected, setConnected] = useState(false);
  const [checking, setChecking] = useState(true);
  const [apifyUser, setApifyUser] = useState("");

  // Token input
  const [apifyToken, setApifyToken] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  // Import
  const [scUrl, setScUrl] = useState("");
  const [importing, setImporting] = useState(false);

  // Active imports
  const [imports, setImports] = useState<SCImportStatus[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.scStatus()
      .then((s) => {
        setConnected(s.connected);
        if (s.username) setApifyUser(s.username);
      })
      .catch(() => setConnected(false))
      .finally(() => setChecking(false));

    api.scImports()
      .then((r) => {
        setImports(r.imports);
        const hasActive = r.imports.some(
          (imp) => imp.status !== "complete" && imp.status !== "error"
        );
        if (hasActive) startPolling();
      })
      .catch(() => {});

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleConnect = useCallback(async () => {
    if (!apifyToken.trim()) return;
    setConnecting(true);
    setConnectError(null);
    try {
      const res = await api.scConnect(apifyToken.trim());
      if (res.status === "connected") {
        setConnected(true);
      } else {
        setConnectError(res.message);
      }
    } catch (e) {
      setConnectError(e instanceof Error ? e.message : "Connection failed");
    } finally {
      setConnecting(false);
    }
  }, [apifyToken]);

  const handleImport = useCallback(async () => {
    if (!scUrl.trim()) return;
    setImporting(true);
    try {
      const status = await api.scImport(scUrl.trim());
      setImports((prev) => [status, ...prev]);
      startPolling();
      setScUrl("");
    } catch (e) {
      console.error(e);
    } finally {
      setImporting(false);
    }
  }, [scUrl]);

  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const res = await api.scImports();
        setImports(res.imports);

        const allDone = res.imports.every(
          (imp) => imp.status === "complete" || imp.status === "error"
        );
        if (allDone && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    }, 2000);
  }

  if (checking) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 text-orange-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <Cloud className="w-7 h-7 text-orange-400" />
          SoundCloud Import
        </h1>
        <p className="text-zinc-400 text-sm mt-1">
          Scrape and analyze tracks from your SoundCloud playlists via Apify
        </p>
      </div>

      {/* Connection */}
      {!connected ? (
        <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800 space-y-4">
          <div className="flex items-center gap-2 text-orange-400">
            <Key className="w-5 h-5" />
            <h2 className="text-lg font-semibold">Connect Apify</h2>
          </div>
          <p className="text-sm text-zinc-400">
            Enter your Apify API token. Get one free at{" "}
            <a
              href="https://console.apify.com/account/integrations"
              target="_blank"
              rel="noopener noreferrer"
              className="text-orange-400 underline"
            >
              console.apify.com
            </a>{" "}
            — the free tier ($5/mo) covers thousands of tracks.
          </p>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Apify API Token</label>
              <input
                type="password"
                value={apifyToken}
                onChange={(e) => setApifyToken(e.target.value)}
                placeholder="apify_api_..."
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                onKeyDown={(e) => e.key === "Enter" && handleConnect()}
              />
            </div>
            <button
              onClick={handleConnect}
              disabled={connecting || !apifyToken.trim()}
              className="flex items-center gap-2 px-5 py-2.5 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 rounded-lg text-sm font-medium text-white transition-colors"
            >
              {connecting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Cloud className="w-4 h-4" />}
              {connecting ? "Connecting..." : "Connect"}
            </button>
          </div>

          {connectError && (
            <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
              <AlertCircle className="w-4 h-4 text-red-400" />
              <span className="text-sm text-red-400">{connectError}</span>
            </div>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
          <CheckCircle2 className="w-4 h-4 text-green-400" />
          <span className="text-sm text-green-400">
            Connected to Apify{apifyUser ? ` as ${apifyUser}` : ""}
          </span>
        </div>
      )}

      {/* Import */}
      {connected && (
        <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800 space-y-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Search className="w-5 h-5 text-orange-400" />
            Import from SoundCloud
          </h2>
          <p className="text-sm text-zinc-400">
            Paste any SoundCloud URL — your profile, a playlist, or a single track.
            It will scrape all tracks and analyze them in the background.
          </p>
          <div className="flex gap-3">
            <input
              type="text"
              value={scUrl}
              onChange={(e) => setScUrl(e.target.value)}
              placeholder="https://soundcloud.com/your-username or playlist URL"
              className="flex-1 px-3 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
              onKeyDown={(e) => e.key === "Enter" && handleImport()}
            />
            <button
              onClick={handleImport}
              disabled={importing || !scUrl.trim()}
              className="flex items-center gap-2 px-5 py-2.5 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 rounded-lg text-sm font-medium text-white transition-colors whitespace-nowrap"
            >
              {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              {importing ? "Starting..." : "Import Tracks"}
            </button>
          </div>
        </div>
      )}

      {/* Active imports */}
      {imports.length > 0 && (
        <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800 space-y-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Music className="w-5 h-5 text-orange-400" />
            Import Jobs
          </h2>
          <div className="space-y-3">
            {imports.map((imp) => (
              <ImportRow key={imp.import_id} imp={imp} />
            ))}
          </div>
        </div>
      )}

      {/* How it works */}
      <div className="bg-zinc-900/50 rounded-xl p-6 border border-zinc-800/50 space-y-3">
        <h3 className="text-sm font-semibold text-zinc-400">How it works</h3>
        <ul className="space-y-2 text-sm text-zinc-500">
          <li className="flex gap-2">
            <span className="text-orange-400">1.</span>
            Connect with your Apify API token (free tier works)
          </li>
          <li className="flex gap-2">
            <span className="text-orange-400">2.</span>
            Paste your SoundCloud profile URL — it scrapes all your playlists and tracks
          </li>
          <li className="flex gap-2">
            <span className="text-orange-400">3.</span>
            Each track is downloaded, analyzed for BPM/key/energy, and added to your library
          </li>
          <li className="flex gap-2">
            <span className="text-orange-400">4.</span>
            Previously imported tracks are skipped automatically
          </li>
          <li className="flex gap-2">
            <span className="text-orange-400">5.</span>
            No SoundCloud API credentials needed — Apify handles the scraping
          </li>
        </ul>
      </div>
    </div>
  );
}

function ImportRow({ imp }: { imp: SCImportStatus }) {
  const progress = imp.total_tracks > 0
    ? (imp.processed_tracks / imp.total_tracks) * 100
    : 0;

  const isActive = imp.status !== "complete" && imp.status !== "error";

  const statusLabel: Record<string, string> = {
    scraping: "Scraping SoundCloud...",
    analyzing: "Analyzing tracks...",
    complete: "Complete",
    error: "Error",
  };

  return (
    <div className="p-3 bg-zinc-800/50 rounded-lg space-y-2">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-2">
          {imp.status === "complete" ? (
            <CheckCircle2 className="w-4 h-4 text-green-400" />
          ) : imp.status === "error" ? (
            <AlertCircle className="w-4 h-4 text-red-400" />
          ) : (
            <Loader2 className="w-4 h-4 text-orange-400 animate-spin" />
          )}
          <span className="text-sm font-medium text-zinc-200 truncate max-w-md">
            {imp.label || `Import #${imp.import_id}`}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-zinc-500">
            {statusLabel[imp.status] || imp.status}
          </span>
          {imp.total_tracks > 0 && (
            <span className="text-xs text-zinc-400">
              {imp.processed_tracks} / {imp.total_tracks}
            </span>
          )}
        </div>
      </div>

      {isActive && imp.total_tracks > 0 && (
        <div className="h-1.5 bg-zinc-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-orange-500 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {imp.current_track && isActive && (
        <div className="text-xs text-zinc-500 truncate">
          Analyzing: {imp.current_track}
        </div>
      )}

      {imp.status === "complete" && imp.total_tracks > 0 && (
        <div className="text-xs text-zinc-500">
          {imp.processed_tracks - imp.skipped_tracks - imp.error_tracks} analyzed,{" "}
          {imp.skipped_tracks} cached, {imp.error_tracks} errors
        </div>
      )}

      {imp.error_message && (
        <div className="text-xs text-red-400">{imp.error_message}</div>
      )}
    </div>
  );
}
