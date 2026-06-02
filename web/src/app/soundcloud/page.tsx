"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { api, type SCPlaylist, type SCImportStatus } from "@/lib/api";
import {
  Cloud,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ListMusic,
  Download,
  Key,
  ExternalLink,
} from "lucide-react";

export default function SoundCloudPage() {
  const [connected, setConnected] = useState(false);
  const [checking, setChecking] = useState(true);

  // Credentials
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);

  // Playlists
  const [userUrl, setUserUrl] = useState("");
  const [playlists, setPlaylists] = useState<SCPlaylist[]>([]);
  const [loadingPlaylists, setLoadingPlaylists] = useState(false);
  const [playlistError, setPlaylistError] = useState<string | null>(null);

  // Imports
  const [activeImports, setActiveImports] = useState<SCImportStatus[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.scStatus()
      .then((s) => setConnected(s.connected))
      .catch(() => setConnected(false))
      .finally(() => setChecking(false));

    api.scImports()
      .then((r) => setActiveImports(r.imports))
      .catch(() => {});

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleConnect = useCallback(async () => {
    if (!clientId.trim() || !clientSecret.trim()) return;
    setConnecting(true);
    setConnectError(null);
    try {
      const res = await api.scConnect(clientId.trim(), clientSecret.trim());
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
  }, [clientId, clientSecret]);

  const handleLoadPlaylists = useCallback(async () => {
    if (!userUrl.trim()) return;
    setLoadingPlaylists(true);
    setPlaylistError(null);
    try {
      const res = await api.scPlaylists(userUrl.trim());
      setPlaylists(res.playlists);
    } catch (e) {
      setPlaylistError(e instanceof Error ? e.message : "Failed to load playlists");
    } finally {
      setLoadingPlaylists(false);
    }
  }, [userUrl]);

  const handleImportPlaylist = useCallback(async (playlist: SCPlaylist) => {
    try {
      const status = await api.scImport({ playlist_id: playlist.id });
      setActiveImports((prev) => [status, ...prev]);
      startPolling(status.import_id);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const handleImportAll = useCallback(async () => {
    if (!userUrl.trim()) return;
    try {
      const status = await api.scImport({ user_url: userUrl.trim() });
      setActiveImports((prev) => [status, ...prev]);
      startPolling(status.import_id);
    } catch (e) {
      console.error(e);
    }
  }, [userUrl]);

  function startPolling(importId: number) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        // Refresh all active imports
        const res = await api.scImports();
        setActiveImports(res.imports);

        const allDone = res.imports.every(
          (imp) => imp.status === "complete" || imp.status === "error"
        );
        if (allDone && pollRef.current) {
          clearInterval(pollRef.current);
        }
      } catch {
        if (pollRef.current) clearInterval(pollRef.current);
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
          SoundCloud Integration
        </h1>
        <p className="text-zinc-400 text-sm mt-1">
          Import and analyze tracks from your SoundCloud playlists
        </p>
      </div>

      {/* Connection status */}
      {!connected ? (
        <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800 space-y-4">
          <div className="flex items-center gap-2 text-orange-400">
            <Key className="w-5 h-5" />
            <h2 className="text-lg font-semibold">Connect SoundCloud</h2>
          </div>
          <p className="text-sm text-zinc-400">
            Enter your SoundCloud API credentials. You need an{" "}
            <a
              href="https://soundcloud.com/you/apps"
              target="_blank"
              rel="noopener noreferrer"
              className="text-orange-400 underline"
            >
              Artist Pro account
            </a>{" "}
            with a registered app to get these.
          </p>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Client ID</label>
              <input
                type="text"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="Your SoundCloud Client ID"
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Client Secret</label>
              <input
                type="password"
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                placeholder="Your SoundCloud Client Secret"
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
              />
            </div>
            <button
              onClick={handleConnect}
              disabled={connecting || !clientId.trim() || !clientSecret.trim()}
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
          <span className="text-sm text-green-400">Connected to SoundCloud</span>
        </div>
      )}

      {/* Playlist browser */}
      {connected && (
        <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800 space-y-4">
          <h2 className="text-lg font-semibold text-white">Browse Playlists</h2>
          <div className="flex gap-3">
            <input
              type="text"
              value={userUrl}
              onChange={(e) => setUserUrl(e.target.value)}
              placeholder="https://soundcloud.com/your-username"
              className="flex-1 px-3 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
              onKeyDown={(e) => e.key === "Enter" && handleLoadPlaylists()}
            />
            <button
              onClick={handleLoadPlaylists}
              disabled={loadingPlaylists || !userUrl.trim()}
              className="flex items-center gap-2 px-4 py-2.5 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 rounded-lg text-sm font-medium text-white transition-colors"
            >
              {loadingPlaylists ? <Loader2 className="w-4 h-4 animate-spin" /> : <ListMusic className="w-4 h-4" />}
              Load Playlists
            </button>
          </div>

          {playlistError && (
            <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
              <AlertCircle className="w-4 h-4 text-red-400" />
              <span className="text-sm text-red-400">{playlistError}</span>
            </div>
          )}

          {playlists.length > 0 && (
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-sm text-zinc-400">{playlists.length} playlists found</span>
                <button
                  onClick={handleImportAll}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-600/20 hover:bg-orange-600/30 border border-orange-500/30 rounded-lg text-xs text-orange-300 transition-colors"
                >
                  <Download className="w-3.5 h-3.5" />
                  Import All Playlists
                </button>
              </div>

              {playlists.map((pl) => (
                <div
                  key={pl.id}
                  className="flex items-center gap-4 p-3 bg-zinc-800/50 rounded-lg hover:bg-zinc-800 transition-colors"
                >
                  {pl.artwork_url ? (
                    <img
                      src={pl.artwork_url}
                      alt={pl.title}
                      className="w-12 h-12 rounded object-cover"
                    />
                  ) : (
                    <div className="w-12 h-12 rounded bg-zinc-700 flex items-center justify-center">
                      <ListMusic className="w-6 h-6 text-zinc-500" />
                    </div>
                  )}

                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-zinc-200 truncate">{pl.title}</div>
                    <div className="text-xs text-zinc-500">
                      {pl.track_count} tracks &middot;{" "}
                      {Math.round(pl.duration_ms / 60000)} min
                    </div>
                  </div>

                  <a
                    href={pl.permalink_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-zinc-500 hover:text-zinc-300"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </a>

                  <button
                    onClick={() => handleImportPlaylist(pl)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-600 hover:bg-orange-500 rounded-lg text-xs font-medium text-white transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Import
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Active imports */}
      {activeImports.length > 0 && (
        <div className="bg-zinc-900 rounded-xl p-6 border border-zinc-800 space-y-4">
          <h2 className="text-lg font-semibold text-white">Imports</h2>
          <div className="space-y-3">
            {activeImports.map((imp) => (
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
            Connect your SoundCloud API credentials (requires Artist Pro)
          </li>
          <li className="flex gap-2">
            <span className="text-orange-400">2.</span>
            Enter your SoundCloud profile URL to browse your playlists
          </li>
          <li className="flex gap-2">
            <span className="text-orange-400">3.</span>
            Import individual playlists or all at once — runs in the background
          </li>
          <li className="flex gap-2">
            <span className="text-orange-400">4.</span>
            Each track is downloaded, analyzed for BPM/key/energy, and added to your library
          </li>
          <li className="flex gap-2">
            <span className="text-orange-400">5.</span>
            Previously imported tracks are skipped automatically
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
          <span className="text-sm font-medium text-zinc-200">
            {imp.playlist_title || `Import #${imp.import_id}`}
          </span>
        </div>
        <span className="text-xs text-zinc-500">
          {imp.processed_tracks} / {imp.total_tracks}
        </span>
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

      {imp.status === "complete" && (
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
