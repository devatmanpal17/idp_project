import { useState, useEffect } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { motion, AnimatePresence } from "motion/react";
import {
  Activity,
  Award,
  ChevronDown,
  ChevronUp,
  Maximize2,
  Minimize2,
  MonitorSmartphone,
  Pause,
  Play,
  Radio,
  RotateCcw,
  Sparkles,
  Volume2,
  Wand2,
} from "lucide-react";
import { Panel, MasteryPill, Meter } from "@/components/chaigaram/primitives";
import { QuizGenerator } from "@/components/chaigaram/QuizGenerator";
import { streamSimulatorTranscript } from "@/lib/ai-client";

export const Route = createFileRoute("/simulator")({
  head: () => ({
    meta: [
      { title: "Extension Simulator | ChaiGaram" },
      {
        name: "description",
        content: "Interactive Chrome extension overlay simulator on MOOC video player",
      },
    ],
  }),
  component: ExtensionSimulatorScreen,
});

const SIMULATED_TRANSCRIPT_FEED = [
  {
    time: "14:20",
    text: "So the key intuition behind the kernel trick is that we don't actually need to compute the explicit coordinates phi(x) in Hilbert space...",
    topic: "Support Vector Machines",
    mastery: 41,
  },
  {
    time: "14:35",
    text: "Instead, any algorithm that only accesses data through inner products can be kernelized by substituting K(x, z)...",
    topic: "Support Vector Machines",
    mastery: 42,
  },
  {
    time: "14:50",
    text: "Notice how support vectors define the margin boundaries. Points outside the margin have zero influence on the hyperplane position...",
    topic: "Support Vector Machines",
    mastery: 44,
  },
  {
    time: "15:10",
    text: "Now when we introduce the soft-margin slack variable xi_i, hyperparameter C dictates how severely margin violations are penalized...",
    topic: "Support Vector Machines",
    mastery: 43,
  },
];

function ExtensionSimulatorScreen() {
  const [isPlaying, setIsPlaying] = useState(true);
  const [transcriptIndex, setTranscriptIndex] = useState(0);
  const [overlayExpanded, setOverlayExpanded] = useState(true);
  const [quizTriggered, setQuizTriggered] = useState(false);
  const [liveMastery, setLiveMastery] = useState(41);

  // Auto-advance transcript simulation when playing
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(() => {
      setTranscriptIndex((prev) => {
        const next = (prev + 1) % SIMULATED_TRANSCRIPT_FEED.length;
        const currentItem = SIMULATED_TRANSCRIPT_FEED[next] ?? SIMULATED_TRANSCRIPT_FEED[0]!;
        setLiveMastery(currentItem.mastery);

        // Send to backend stream API
        streamSimulatorTranscript({
          video_title: "Machine Learning A-Z: Kernel Methods",
          timestamp: currentItem.time,
          transcript_segment: currentItem.text,
          current_topic: currentItem.topic,
          dwell_seconds: 15,
        });

        return next;
      });
    }, 4500);
    return () => clearInterval(interval);
  }, [isPlaying]);

  const currentSegment = SIMULATED_TRANSCRIPT_FEED[transcriptIndex] ?? SIMULATED_TRANSCRIPT_FEED[0]!;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
            Chrome Extension Overlay Simulator
          </h1>
          <p className="text-xs text-muted-foreground">
            Simulating the ChaiGaram client-side overlay injected directly into a MOOC video player
            (Udemy / Coursera / edX).
          </p>
        </div>
      </div>

      {/* Main Mock Video Player Container with Docked Floating Overlay */}
      <div className="relative overflow-hidden rounded-xl border border-border bg-[#0d0f14] shadow-2xl">
        {/* Mock Udemy / Coursera Video Top Bar */}
        <div className="flex items-center justify-between border-b border-border/40 bg-[#161a22] px-4 py-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-warn" />
            <span className="font-semibold text-foreground">Udemy Course Player Mock</span>
            <span>· Section 14: Support Vector Machines & Kernel Methods</span>
          </div>
          <span className="num text-[11px] text-muted-foreground">1080p HD</span>
        </div>

        {/* Video Canvas Area */}
        <div className="relative flex min-h-[440px] flex-col justify-between p-6">
          {/* Subtle Video Background Visualization */}
          <div className="absolute inset-0 flex items-center justify-center opacity-10 pointer-events-none">
            <div className="text-center">
              <Radio className="mx-auto h-24 w-24 text-primary animate-pulse" />
              <p className="font-mono text-sm">VIDEO STREAM ACTIVE</p>
            </div>
          </div>

          {/* Top Video Overlay Text */}
          <div className="relative z-10">
            <span className="rounded bg-black/60 px-2 py-1 text-[11px] text-zinc-300 backdrop-blur">
              Lecture 48: The Mathematics of Dual Optimization
            </span>
          </div>

          {/* Subtitle / Live Transcript Display at bottom of video */}
          <div className="relative z-10 mx-auto max-w-xl text-center">
            <div className="inline-block rounded-lg bg-black/80 px-4 py-2 text-xs leading-relaxed text-zinc-200 backdrop-blur shadow-lg border border-white/10">
              <span className="num mr-2 font-mono text-primary">[{currentSegment.time}]</span>"
              {currentSegment.text}"
            </div>
          </div>

          {/* Video Control Bar */}
          <div className="relative z-10 mt-6 flex items-center justify-between rounded-lg bg-black/60 px-4 py-2.5 backdrop-blur">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className="grid h-8 w-8 place-items-center rounded-full bg-primary text-primary-foreground hover:bg-primary/90"
              >
                {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 ml-0.5" />}
              </button>
              <Volume2 className="h-4 w-4 text-zinc-400" />
              <span className="num text-xs text-zinc-300">{currentSegment.time} / 38:45</span>
            </div>

            {/* Scrubber */}
            <div className="mx-4 flex-1">
              <div className="h-1.5 w-full rounded-full bg-zinc-700">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-500"
                  style={{ width: `${(transcriptIndex + 1) * 25}%` }}
                />
              </div>
            </div>

            <Maximize2 className="h-4 w-4 text-zinc-400" />
          </div>

          {/* ---------------- FLOATING CHAIGARAM OVERLAY UI ---------------- */}
          <div className="absolute right-6 top-6 z-20 w-80">
            <motion.div
              layout
              className="overflow-hidden rounded-xl border border-primary/40 bg-[#12161f]/95 p-4 text-foreground shadow-2xl backdrop-blur-md ring-1 ring-primary/20"
            >
              {/* Overlay Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="grid h-6 w-6 place-items-center rounded bg-primary/20 text-primary">
                    <Activity className="h-3.5 w-3.5" />
                  </div>
                  <div>
                    <span className="font-display text-xs font-bold text-foreground">
                      ChaiGaram Companion
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  <div className="flex items-center gap-1 text-[10px] text-positive">
                    <span className="live-dot h-1.5 w-1.5 rounded-full bg-positive" />
                    <span>Live RAG</span>
                  </div>
                  <button
                    onClick={() => setOverlayExpanded(!overlayExpanded)}
                    className="rounded p-1 text-muted-foreground hover:text-foreground"
                  >
                    {overlayExpanded ? (
                      <Minimize2 className="h-3 w-3" />
                    ) : (
                      <Maximize2 className="h-3 w-3" />
                    )}
                  </button>
                </div>
              </div>

              {/* Expanded Overlay Body */}
              <AnimatePresence>
                {overlayExpanded && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-3 space-y-3 border-t border-border/60 pt-3"
                  >
                    {/* Live Section Mastery Gauge */}
                    <div>
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-muted-foreground">Current Section Mastery</span>
                        <span className="num font-bold text-primary">{liveMastery}%</span>
                      </div>
                      <Meter value={liveMastery} tone="primary" className="mt-1" />
                    </div>

                    {/* Dwell Telemetry */}
                    <div className="rounded bg-surface-2/80 p-2 text-[10px] text-muted-foreground space-y-1">
                      <div className="flex justify-between">
                        <span>DOM Signal:</span>
                        <span className="text-positive font-mono">Capturing Transcript</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Chunk Vector:</span>
                        <span className="text-foreground font-mono">chunk_0417 (sim 0.912)</span>
                      </div>
                    </div>

                    {/* "Quiz me on this" Button */}
                    <button
                      onClick={() => setQuizTriggered(true)}
                      className="w-full flex items-center justify-center gap-1.5 rounded-md bg-primary py-2 text-xs font-semibold text-primary-foreground shadow transition hover:bg-primary/90"
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      Quiz me on this section
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          </div>
        </div>
      </div>

      {/* Quiz Modal / Container Triggered from Overlay */}
      {quizTriggered && (
        <Panel className="border-primary/50 bg-surface p-6 shadow-xl">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <span className="label-xs text-primary">EXTENSION SIMULATOR TRIGGER</span>
              <h2 className="font-display text-base font-bold text-foreground">
                In-Video Adaptive RAG Quiz
              </h2>
            </div>
            <button
              onClick={() => setQuizTriggered(false)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Close
            </button>
          </div>

          <QuizGenerator
            topicTitle="Support Vector Machines"
            masteryScore={liveMastery}
            onMasteryUpdated={(newScore) => setLiveMastery(newScore)}
          />
        </Panel>
      )}
    </div>
  );
}
