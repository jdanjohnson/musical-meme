/** Camelot wheel constants and utilities */

export const CAMELOT_KEYS = [
  "1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B",
  "5A", "5B", "6A", "6B", "7A", "7B", "8A", "8B",
  "9A", "9B", "10A", "10B", "11A", "11B", "12A", "12B",
] as const;

export const CAMELOT_COLORS: Record<string, string> = {
  "1A": "#8B5CF6", "1B": "#A78BFA",
  "2A": "#6366F1", "2B": "#818CF8",
  "3A": "#3B82F6", "3B": "#60A5FA",
  "4A": "#0EA5E9", "4B": "#38BDF8",
  "5A": "#06B6D4", "5B": "#22D3EE",
  "6A": "#14B8A6", "6B": "#2DD4BF",
  "7A": "#10B981", "7B": "#34D399",
  "8A": "#22C55E", "8B": "#4ADE80",
  "9A": "#84CC16", "9B": "#A3E635",
  "10A": "#EAB308", "10B": "#FACC15",
  "11A": "#F97316", "11B": "#FB923C",
  "12A": "#EF4444", "12B": "#F87171",
};

export const CAMELOT_TO_KEY: Record<string, string> = {
  "1A": "Ab min", "1B": "B maj",
  "2A": "Eb min", "2B": "F# maj",
  "3A": "Bb min", "3B": "Db maj",
  "4A": "F min", "4B": "Ab maj",
  "5A": "C min", "5B": "Eb maj",
  "6A": "G min", "6B": "Bb maj",
  "7A": "D min", "7B": "F maj",
  "8A": "A min", "8B": "C maj",
  "9A": "E min", "9B": "G maj",
  "10A": "B min", "10B": "D maj",
  "11A": "F# min", "11B": "A maj",
  "12A": "C# min", "12B": "E maj",
};

export function parseCamelot(code: string): { number: number; letter: string } | null {
  const match = code.match(/^(\d{1,2})([AB])$/i);
  if (!match) return null;
  const num = parseInt(match[1]);
  const letter = match[2].toUpperCase();
  if (num < 1 || num > 12) return null;
  return { number: num, letter };
}

export function camelotDistance(code1: string, code2: string): number {
  const p1 = parseCamelot(code1);
  const p2 = parseCamelot(code2);
  if (!p1 || !p2) return 12;
  const dist = Math.min(
    Math.abs(p1.number - p2.number),
    12 - Math.abs(p1.number - p2.number)
  );
  return dist;
}

export function isCompatible(code1: string, code2: string): boolean {
  const p1 = parseCamelot(code1);
  const p2 = parseCamelot(code2);
  if (!p1 || !p2) return false;
  const dist = camelotDistance(code1, code2);
  // Same key, adjacent, or mode switch
  if (p1.number === p2.number) return true; // same number (same key or mode switch)
  if (dist <= 1 && p1.letter === p2.letter) return true; // adjacent same letter
  return false;
}

export function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function scoreColor(score: number): string {
  if (score >= 0.8) return "text-green-400";
  if (score >= 0.6) return "text-yellow-400";
  if (score >= 0.4) return "text-orange-400";
  return "text-red-400";
}
