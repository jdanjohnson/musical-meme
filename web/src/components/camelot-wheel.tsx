"use client";

import { useEffect, useRef, useState } from "react";
import { CAMELOT_COLORS, CAMELOT_TO_KEY, parseCamelot } from "@/lib/camelot";

interface CamelotWheelProps {
  distribution: Record<string, number>;
  onKeySelect?: (key: string | null) => void;
  selectedKey?: string | null;
  size?: number;
}

const WHEEL_ORDER_OUTER = ["1B", "2B", "3B", "4B", "5B", "6B", "7B", "8B", "9B", "10B", "11B", "12B"];
const WHEEL_ORDER_INNER = ["1A", "2A", "3A", "4A", "5A", "6A", "7A", "8A", "9A", "10A", "11A", "12A"];

export function CamelotWheel({ distribution, onKeySelect, selectedKey, size = 400 }: CamelotWheelProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  const maxCount = Math.max(1, ...Object.values(distribution));
  const center = size / 2;
  const outerRadius = size * 0.45;
  const innerRadius = size * 0.28;
  const innerInnerRadius = size * 0.12;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, size, size);

    const sliceAngle = (Math.PI * 2) / 12;

    // Draw outer ring (major / B keys)
    WHEEL_ORDER_OUTER.forEach((key, i) => {
      const startAngle = i * sliceAngle - Math.PI / 2 - sliceAngle / 2;
      const endAngle = startAngle + sliceAngle;
      const count = distribution[key] || 0;
      const intensity = count / maxCount;
      const color = CAMELOT_COLORS[key];

      ctx.beginPath();
      ctx.arc(center, center, outerRadius, startAngle, endAngle);
      ctx.arc(center, center, innerRadius, endAngle, startAngle, true);
      ctx.closePath();

      const isSelected = selectedKey === key;
      const isHovered = hoveredKey === key;
      const alpha = count > 0 ? 0.3 + intensity * 0.7 : 0.1;

      ctx.fillStyle = color + Math.round(alpha * 255).toString(16).padStart(2, "0");
      if (isSelected || isHovered) {
        ctx.fillStyle = color;
      }
      ctx.fill();

      ctx.strokeStyle = isSelected ? "#fff" : "rgba(255,255,255,0.15)";
      ctx.lineWidth = isSelected ? 2 : 0.5;
      ctx.stroke();

      // Label
      const midAngle = (startAngle + endAngle) / 2;
      const labelR = (outerRadius + innerRadius) / 2;
      const lx = center + Math.cos(midAngle) * labelR;
      const ly = center + Math.sin(midAngle) * labelR;

      ctx.fillStyle = count > 0 ? "#fff" : "rgba(255,255,255,0.4)";
      ctx.font = `bold ${size * 0.028}px system-ui`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(key, lx, ly - 6);

      if (count > 0) {
        ctx.font = `${size * 0.022}px system-ui`;
        ctx.fillStyle = "rgba(255,255,255,0.7)";
        ctx.fillText(`${count}`, lx, ly + 8);
      }
    });

    // Draw inner ring (minor / A keys)
    WHEEL_ORDER_INNER.forEach((key, i) => {
      const startAngle = i * sliceAngle - Math.PI / 2 - sliceAngle / 2;
      const endAngle = startAngle + sliceAngle;
      const count = distribution[key] || 0;
      const intensity = count / maxCount;
      const color = CAMELOT_COLORS[key];

      ctx.beginPath();
      ctx.arc(center, center, innerRadius, startAngle, endAngle);
      ctx.arc(center, center, innerInnerRadius, endAngle, startAngle, true);
      ctx.closePath();

      const isSelected = selectedKey === key;
      const isHovered = hoveredKey === key;
      const alpha = count > 0 ? 0.3 + intensity * 0.7 : 0.1;

      ctx.fillStyle = color + Math.round(alpha * 255).toString(16).padStart(2, "0");
      if (isSelected || isHovered) {
        ctx.fillStyle = color;
      }
      ctx.fill();

      ctx.strokeStyle = isSelected ? "#fff" : "rgba(255,255,255,0.15)";
      ctx.lineWidth = isSelected ? 2 : 0.5;
      ctx.stroke();

      const midAngle = (startAngle + endAngle) / 2;
      const labelR = (innerRadius + innerInnerRadius) / 2;
      const lx = center + Math.cos(midAngle) * labelR;
      const ly = center + Math.sin(midAngle) * labelR;

      ctx.fillStyle = count > 0 ? "#fff" : "rgba(255,255,255,0.4)";
      ctx.font = `bold ${size * 0.025}px system-ui`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(key, lx, ly - 5);

      if (count > 0) {
        ctx.font = `${size * 0.02}px system-ui`;
        ctx.fillStyle = "rgba(255,255,255,0.7)";
        ctx.fillText(`${count}`, lx, ly + 7);
      }
    });

    // Center label
    ctx.beginPath();
    ctx.arc(center, center, innerInnerRadius, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(24, 24, 27, 0.9)";
    ctx.fill();

    const displayKey = hoveredKey || selectedKey;
    if (displayKey) {
      ctx.fillStyle = CAMELOT_COLORS[displayKey] || "#fff";
      ctx.font = `bold ${size * 0.04}px system-ui`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(displayKey, center, center - 12);
      ctx.fillStyle = "rgba(255,255,255,0.6)";
      ctx.font = `${size * 0.025}px system-ui`;
      ctx.fillText(CAMELOT_TO_KEY[displayKey] || "", center, center + 8);
      const count = distribution[displayKey] || 0;
      ctx.fillText(`${count} tracks`, center, center + 24);
    } else {
      ctx.fillStyle = "rgba(255,255,255,0.5)";
      ctx.font = `${size * 0.025}px system-ui`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("Camelot", center, center - 6);
      ctx.fillText("Wheel", center, center + 10);
    }
  }, [distribution, selectedKey, hoveredKey, size, maxCount, center, outerRadius, innerRadius, innerInnerRadius]);

  function handleClick(e: React.MouseEvent<HTMLCanvasElement>) {
    const key = getKeyAtPosition(e);
    if (key) {
      onKeySelect?.(selectedKey === key ? null : key);
    }
  }

  function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    const key = getKeyAtPosition(e);
    setHoveredKey(key);
  }

  function getKeyAtPosition(e: React.MouseEvent<HTMLCanvasElement>): string | null {
    const rect = canvasRef.current!.getBoundingClientRect();
    const x = e.clientX - rect.left - center;
    const y = e.clientY - rect.top - center;
    const dist = Math.sqrt(x * x + y * y);
    let angle = Math.atan2(y, x) + Math.PI / 2;
    if (angle < 0) angle += Math.PI * 2;

    const sliceAngle = (Math.PI * 2) / 12;
    const index = Math.floor((angle + sliceAngle / 2) / sliceAngle) % 12;

    if (dist >= innerRadius && dist <= outerRadius) {
      return WHEEL_ORDER_OUTER[index];
    }
    if (dist >= innerInnerRadius && dist <= innerRadius) {
      return WHEEL_ORDER_INNER[index];
    }
    return null;
  }

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      style={{ width: size, height: size }}
      onClick={handleClick}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setHoveredKey(null)}
      className="cursor-pointer"
    />
  );
}
