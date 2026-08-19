import type {
  Course,
  Topic,
  Quiz,
  StudyEvent,
  Recommendation,
  ActivityEntry,
} from "./types";

export const MOCK_COURSES: Course[] = [
  {
    id: "c1",
    title: "Machine Learning A-Z",
    platform: "Udemy",
    thumbnail_url: null,
    completion_pct: 78,
    overall_mastery: 41,
    created_at: new Date().toISOString(),
  },
  {
    id: "c2",
    title: "Data Structures & Algorithms",
    platform: "Coursera",
    thumbnail_url: null,
    completion_pct: 62,
    overall_mastery: 58,
    created_at: new Date().toISOString(),
  },
  {
    id: "c3",
    title: "React - The Complete Guide",
    platform: "edX",
    thumbnail_url: null,
    completion_pct: 95,
    overall_mastery: 84,
    created_at: new Date().toISOString(),
  },
  {
    id: "c4",
    title: "System Design Interview Prep",
    platform: "Udemy",
    thumbnail_url: null,
    completion_pct: 45,
    overall_mastery: 35,
    created_at: new Date().toISOString(),
  }
];

export const MOCK_TOPICS: Topic[] = [
  {
    id: "t1",
    course_id: "c1",
    title: "Support Vector Machines",
    mastery_score: 41,
    quiz_perf_pct: 18,
    time_on_section_pct: 85,
    revisit_frequency_pct: 12,
    trend_delta: -5.4,
    minutes_on_section: 120,
    revisits: 8,
    last_updated: new Date().toISOString(),
  },
  {
    id: "t2",
    course_id: "c2",
    title: "Dynamic Programming",
    mastery_score: 24,
    quiz_perf_pct: 22,
    time_on_section_pct: 60,
    revisit_frequency_pct: 5,
    trend_delta: -2.1,
    minutes_on_section: 90,
    revisits: 2,
    last_updated: new Date().toISOString(),
  },
  {
    id: "t3",
    course_id: "c2",
    title: "Graph Traversal",
    mastery_score: 55,
    quiz_perf_pct: 60,
    time_on_section_pct: 45,
    revisit_frequency_pct: 80,
    trend_delta: 3.2,
    minutes_on_section: 60,
    revisits: 12,
    last_updated: new Date().toISOString(),
  },
  {
    id: "t4",
    course_id: "c3",
    title: "React Hooks",
    mastery_score: 88,
    quiz_perf_pct: 95,
    time_on_section_pct: 70,
    revisit_frequency_pct: 85,
    trend_delta: 1.5,
    minutes_on_section: 150,
    revisits: 20,
    last_updated: new Date().toISOString(),
  },
  {
    id: "t5",
    course_id: "c3",
    title: "Performance Optimization",
    mastery_score: 66,
    quiz_perf_pct: 50,
    time_on_section_pct: 80,
    revisit_frequency_pct: 30,
    trend_delta: -2.7,
    minutes_on_section: 80,
    revisits: 5,
    last_updated: new Date().toISOString(),
  },
  {
    id: "t6",
    course_id: "c4",
    title: "Database Sharding",
    mastery_score: 35,
    quiz_perf_pct: 40,
    time_on_section_pct: 35,
    revisit_frequency_pct: 20,
    trend_delta: 0.5,
    minutes_on_section: 45,
    revisits: 3,
    last_updated: new Date().toISOString(),
  }
];

export const MOCK_QUIZZES: Quiz[] = [
  {
    id: "q1",
    topic_id: "t1",
    course_id: "c1",
    question_type: "mcq",
    questions: [],
    score: 85,
    completed_at: new Date(Date.now() - 3600000).toISOString(),
  },
  {
    id: "q2",
    topic_id: "t4",
    course_id: "c3",
    question_type: "mcq",
    questions: [],
    score: 95,
    completed_at: new Date(Date.now() - 86400000).toISOString(),
  },
  {
    id: "q3",
    topic_id: "t2",
    course_id: "c2",
    question_type: "mcq",
    questions: [],
    score: 40,
    completed_at: new Date(Date.now() - 172800000).toISOString(),
  }
];

export const MOCK_STUDY_EVENTS: StudyEvent[] = [
  {
    id: "se1",
    topic_id: "t2",
    event_type: "review",
    scheduled_at: new Date(Date.now() + 3600000).toISOString(), // +1 hour
    status: "scheduled",
  },
  {
    id: "se2",
    topic_id: "t1",
    event_type: "quiz",
    scheduled_at: new Date(Date.now() + 86400000).toISOString(), // +1 day
    status: "scheduled",
  }
];

export const MOCK_RECOMMENDATIONS: Recommendation[] = [
  {
    id: "rec_01",
    topic_id: "t2", // Dynamic Programming
    type: "revisit_weak_topic",
    impact_score: 94,
    estimated_minutes: 35,
    reasoning: "Mastery is 24 with a -5.4 weekly trend. Quiz performance (18%) is the dominant drag and 8 revisits indicate passive rewatching without consolidation. A structured retrieval drill will recover retention.",
    created_at: new Date().toISOString(),
  },
  {
    id: "rec_02",
    topic_id: "t3", // Graph Traversal
    type: "revisit_weak_topic",
    impact_score: 88,
    estimated_minutes: 25,
    reasoning: "Graph traversal underpins Dynamic Programming on DAGs, which is scheduled next. Closing this 29-point mastery gap prevents downstream compounding failure.",
    created_at: new Date().toISOString(),
  },
  {
    id: "rec_03",
    topic_id: "t1", // SVM
    type: "revisit_weak_topic",
    impact_score: 81,
    estimated_minutes: 30,
    reasoning: "Largest completion-to-mastery gap in Machine Learning A-Z (78% watched vs 41% mastery). Retrieval practice on the kernel trick will recover over 30 points of mastery.",
    created_at: new Date().toISOString(),
  },
  {
    id: "rec_04",
    topic_id: "t5", // Performance Optimization
    type: "proceed_next_module",
    impact_score: 66,
    estimated_minutes: 20,
    reasoning: "Performance Optimization is trending down (-2.7). A short profiling exercise and hook review will stabilize it before moving to server components.",
    created_at: new Date().toISOString(),
  }
];

export const MOCK_ACTIVITY: ActivityEntry[] = [
  {
    id: "act1",
    course_id: "c1",
    event_type: "quiz_completed",
    metadata: { topic: "Support Vector Machines", score: 85, delta: 4.2 },
    created_at: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
  },
  {
    id: "act2",
    course_id: "c2",
    event_type: "topic_revisit",
    metadata: { topic: "Dynamic Programming", revisits: 8 },
    created_at: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
  },
  {
    id: "act3",
    course_id: "c3",
    event_type: "mastery_updated",
    metadata: { topic: "React Hooks", delta: 1.5 },
    created_at: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
  },
  {
    id: "act4",
    course_id: "c1",
    event_type: "transcript_captured",
    metadata: { topic: "Kernel Methods", chunks: 14 },
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
  }
];
