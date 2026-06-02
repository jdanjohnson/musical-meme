"use client";

import { useEffect, useRef } from "react";
import type { SetTrack } from "@/lib/api";

interface EnergyArcProps {
  tracks: SetTrack[];
  width?: number;
  height?: number;
}

export function EnergyArc({ tracks, width = 600, height = 200 }: EnergyArcProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || tracks.length === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const padding = { top: 20, right: 20, bottom: 30, left: 40 };
    const plotW = width - padding.left - padding.right;
    const plotH = height - padding.top - padding.bottom;

    // Y axis (energy 1-10)
    ctx.strokeStyle = "rgba(255,255,255,0.1)";
    ctx.lineWidth = 1;
    for (let e = 2; e <= 10; e += 2) {
      const y = padding.top + plotH - ((e - 1) / 9) * plotH;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(padding.left + plotW, y);
      ctx.stroke();

      ctx.fillStyle = "rgba(255,255,255,0.3)";
      ctx.font = "11px system-ui";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(`${e}`, padding.left - 8, y);
    }

    // Plot energy line
    const points = tracks.map((t, i) => ({
      x: padding.left + (i / Math.max(1, tracks.length - 1)) * plotW,
      y: padding.top + plotH - ((t.track.energy_level - 1) / 9) * plotH,
      energy: t.track.energy_level,
    }));

    // Gradient fill under curve
    const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + plotH);
    gradient.addColorStop(0, "rgba(168, 85, 247, 0.4)");
    gradient.addColorStop(1, "rgba(168, 85, 247, 0.02)");

    ctx.beginPath();
    ctx.moveTo(points[0].x, padding.top + plotH);
    points.forEach((p) => ctx.lineTo(p.x, p.y));
    ctx.lineTo(points[points.length - 1].x, padding.top + plotH);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Line
    ctx.beginPath();
    points.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
    ctx.strokeStyle = "#a855f7";
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Dots
    points.forEach((p) => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
      const hue = p.energy <= 3 ? 200 : p.energy <= 6 ? 270 : p.energy <= 8 ? 300 : 0;
      const sat = p.energy <= 3 ? 60 : 80;
      ctx.fillStyle = `hsl(${hue}, ${sat}%, 60%)`;
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });

    // X axis labels (track numbers)
    ctx.fillStyle = "rgba(255,255,255,0.4)";
    ctx.font = "10px system-ui";
    ctx.textAlign = "center";
    points.forEach((p, i) => {
      if (tracks.length <= 20 || i % Math.ceil(tracks.length / 20) === 0) {
        ctx.fillText(`${i + 1}`, p.x, padding.top + plotH + 16);
      }
    });
  }, [tracks, width, height]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width, height }}
      className="rounded-lg"
    />
  );
}
