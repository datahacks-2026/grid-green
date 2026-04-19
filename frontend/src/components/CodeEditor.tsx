"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef } from "react";
import type { DetectedPattern } from "@/lib/api";

const MonacoEditor = dynamic(
  () => import("@monaco-editor/react").then((m) => m.default),
  { ssr: false, loading: () => <div className="h-full grid place-items-center text-gg-muted">Loading editor…</div> },
);

type Props = {
  value: string;
  onChange: (next: string) => void;
  patterns: DetectedPattern[];
};

export default function CodeEditor({ value, onChange, patterns }: Props) {
  const decorationsRef = useRef<string[]>([]);
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);

  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;

    const newDecorations = patterns.map((p) => ({
      range: new monaco.Range(p.line, 1, p.line, 1),
      options: {
        isWholeLine: true,
        className: `gg-impact-${p.impact}`,
        glyphMarginClassName: `gg-glyph-${p.impact}`,
        hoverMessage: { value: `**${p.pattern}** — impact: ${p.impact}` },
      },
    }));

    decorationsRef.current = editor.deltaDecorations(decorationsRef.current, newDecorations);
  }, [patterns]);

  return (
    <MonacoEditor
      height="100%"
      defaultLanguage="python"
      theme="vs-dark"
      value={value}
      onChange={(v) => onChange(v ?? "")}
      onMount={(editor, monaco) => {
        editorRef.current = editor;
        monacoRef.current = monaco;
      }}
      options={{
        fontSize: 13,
        minimap: { enabled: false },
        glyphMargin: true,
        scrollBeyondLastLine: false,
        automaticLayout: true,
        wordWrap: "on",
      }}
    />
  );
}
