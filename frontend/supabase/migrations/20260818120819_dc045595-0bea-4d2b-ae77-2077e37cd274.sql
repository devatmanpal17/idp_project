
CREATE TABLE public.courses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  platform text NOT NULL,
  thumbnail_url text,
  completion_pct numeric NOT NULL DEFAULT 0,
  overall_mastery numeric NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.topics (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id uuid NOT NULL REFERENCES public.courses(id) ON DELETE CASCADE,
  title text NOT NULL,
  mastery_score numeric NOT NULL DEFAULT 0,
  quiz_perf_pct numeric NOT NULL DEFAULT 0,
  time_on_section_pct numeric NOT NULL DEFAULT 0,
  revisit_frequency_pct numeric NOT NULL DEFAULT 0,
  trend_delta numeric NOT NULL DEFAULT 0,
  minutes_on_section integer NOT NULL DEFAULT 0,
  revisits integer NOT NULL DEFAULT 0,
  last_updated timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.quizzes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id uuid REFERENCES public.topics(id) ON DELETE CASCADE,
  course_id uuid REFERENCES public.courses(id) ON DELETE CASCADE,
  question_type text NOT NULL,
  questions jsonb NOT NULL DEFAULT '[]'::jsonb,
  score numeric NOT NULL DEFAULT 0,
  completed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.study_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id uuid REFERENCES public.topics(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  scheduled_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'scheduled',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.recommendations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id uuid REFERENCES public.topics(id) ON DELETE CASCADE,
  type text NOT NULL,
  impact_score numeric NOT NULL DEFAULT 0,
  estimated_minutes integer NOT NULL DEFAULT 0,
  reasoning text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.activity_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id uuid REFERENCES public.courses(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT ON public.courses, public.topics, public.quizzes, public.study_events, public.recommendations, public.activity_log TO anon, authenticated;
GRANT ALL ON public.courses, public.topics, public.quizzes, public.study_events, public.recommendations, public.activity_log TO service_role;

ALTER TABLE public.courses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.quizzes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.study_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public demo read" ON public.courses FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Public demo read" ON public.topics FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Public demo read" ON public.quizzes FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Public demo read" ON public.study_events FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Public demo read" ON public.recommendations FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Public demo read" ON public.activity_log FOR SELECT TO anon, authenticated USING (true);

INSERT INTO public.courses (id, title, platform, thumbnail_url, completion_pct, overall_mastery, created_at) VALUES
('c0000000-0000-4000-8000-000000000001','Machine Learning A-Z','Udemy',null,78,61,now() - interval '120 days'),
('c0000000-0000-4000-8000-000000000002','React - The Complete Guide','Udemy',null,92,74,now() - interval '90 days'),
('c0000000-0000-4000-8000-000000000003','Data Structures & Algorithms','Coursera',null,45,38,now() - interval '60 days'),
('c0000000-0000-4000-8000-000000000004','Deep Learning Specialization','Coursera',null,63,71,now() - interval '45 days'),
('c0000000-0000-4000-8000-000000000005','Databases for Developers','edX',null,34,55,now() - interval '20 days');

INSERT INTO public.topics (id, course_id, title, mastery_score, quiz_perf_pct, time_on_section_pct, revisit_frequency_pct, trend_delta, minutes_on_section, revisits, last_updated) VALUES
('70000000-0000-4000-8000-000000000001','c0000000-0000-4000-8000-000000000001','Linear Regression',82,88,80,72,4.2,146,3,now() - interval '2 days'),
('70000000-0000-4000-8000-000000000002','c0000000-0000-4000-8000-000000000001','Logistic Regression',67,71,66,60,1.8,112,4,now() - interval '3 days'),
('70000000-0000-4000-8000-000000000003','c0000000-0000-4000-8000-000000000001','Support Vector Machines',41,36,48,40,-3.1,64,6,now() - interval '1 day'),
('70000000-0000-4000-8000-000000000004','c0000000-0000-4000-8000-000000000001','Decision Trees & Random Forests',58,55,64,54,2.4,98,2,now() - interval '5 days'),
('70000000-0000-4000-8000-000000000005','c0000000-0000-4000-8000-000000000001','K-Means Clustering',54,49,60,55,-1.2,77,5,now() - interval '4 days'),
('70000000-0000-4000-8000-000000000006','c0000000-0000-4000-8000-000000000002','React Hooks',86,92,84,76,5.6,210,2,now() - interval '1 day'),
('70000000-0000-4000-8000-000000000007','c0000000-0000-4000-8000-000000000002','Context & Redux',63,58,70,64,0.9,155,5,now() - interval '3 days'),
('70000000-0000-4000-8000-000000000008','c0000000-0000-4000-8000-000000000002','React Router',79,82,78,72,2.1,88,1,now() - interval '6 days'),
('70000000-0000-4000-8000-000000000009','c0000000-0000-4000-8000-000000000002','Performance Optimization',52,44,60,56,-2.7,71,4,now() - interval '2 days'),
('70000000-0000-4000-8000-00000000000a','c0000000-0000-4000-8000-000000000003','Arrays & Hashing',61,64,60,56,3.3,94,3,now() - interval '4 days'),
('70000000-0000-4000-8000-00000000000b','c0000000-0000-4000-8000-000000000003','Linked Lists',44,38,50,46,-1.5,58,4,now() - interval '7 days'),
('70000000-0000-4000-8000-00000000000c','c0000000-0000-4000-8000-000000000003','Graph Traversal',29,22,34,32,-4.8,41,7,now() - interval '2 days'),
('70000000-0000-4000-8000-00000000000d','c0000000-0000-4000-8000-000000000003','Dynamic Programming',24,18,28,30,-5.4,36,8,now() - interval '1 day'),
('70000000-0000-4000-8000-00000000000e','c0000000-0000-4000-8000-000000000004','Neural Network Basics',84,89,82,76,4.9,168,2,now() - interval '3 days'),
('70000000-0000-4000-8000-00000000000f','c0000000-0000-4000-8000-000000000004','Backpropagation',66,62,72,64,1.4,121,4,now() - interval '5 days'),
('70000000-0000-4000-8000-000000000010','c0000000-0000-4000-8000-000000000004','Convolutional Networks',72,76,70,66,2.8,139,3,now() - interval '2 days'),
('70000000-0000-4000-8000-000000000011','c0000000-0000-4000-8000-000000000004','Sequence Models',48,42,54,50,-2.2,63,5,now() - interval '6 days'),
('70000000-0000-4000-8000-000000000012','c0000000-0000-4000-8000-000000000005','Relational Modeling',68,70,68,64,2.6,84,2,now() - interval '4 days'),
('70000000-0000-4000-8000-000000000013','c0000000-0000-4000-8000-000000000005','Indexing & Query Plans',43,36,50,46,-1.9,52,5,now() - interval '3 days'),
('70000000-0000-4000-8000-000000000014','c0000000-0000-4000-8000-000000000005','Transactions & Isolation',51,48,54,52,0.6,60,3,now() - interval '8 days');

INSERT INTO public.quizzes (id, topic_id, course_id, question_type, questions, score, completed_at) VALUES
('90000000-0000-4000-8000-000000000001','70000000-0000-4000-8000-000000000001','c0000000-0000-4000-8000-000000000001','mcq','[{"q":"What does the least-squares method minimise?","choices":["Sum of absolute residuals","Sum of squared residuals","Maximum residual","Variance of the predictors"],"answer":"Sum of squared residuals","given":"Sum of squared residuals","correct":true,"explanation":"Ordinary least squares fits the line that minimises the sum of squared vertical distances between observed and predicted values."},{"q":"R-squared of 0.0 means the model...","choices":["Fits perfectly","Explains none of the variance","Is overfit","Has no intercept"],"answer":"Explains none of the variance","given":"Is overfit","correct":false,"explanation":"R-squared measures explained variance. 0.0 means the model does no better than predicting the mean; overfitting is unrelated."}]'::jsonb,88,now() - interval '2 days'),
('90000000-0000-4000-8000-000000000002','70000000-0000-4000-8000-000000000003','c0000000-0000-4000-8000-000000000001','mixed','[{"q":"What is the role of the kernel trick in SVMs?","choices":["Reduces dataset size","Computes inner products in a higher-dimensional space implicitly","Normalises features","Prunes support vectors"],"answer":"Computes inner products in a higher-dimensional space implicitly","given":"Normalises features","correct":false,"explanation":"The kernel trick lets an SVM operate in a high-dimensional feature space without ever computing the transformed coordinates."},{"q":"Explain what a support vector is.","answer":"A training point lying on or inside the margin that defines the decision boundary.","given":"Any point in the training set.","correct":false,"explanation":"Only points on or violating the margin influence the boundary; removing all other points leaves the model unchanged."}]'::jsonb,36,now() - interval '1 day'),
('90000000-0000-4000-8000-000000000003','70000000-0000-4000-8000-000000000006','c0000000-0000-4000-8000-000000000002','mcq','[{"q":"When does useEffect with an empty dependency array run?","choices":["On every render","Once after the first render","Only on unmount","Never"],"answer":"Once after the first render","given":"Once after the first render","correct":true,"explanation":"An empty dependency array means the effect has no reactive dependencies, so it runs once after mount."},{"q":"useMemo primarily helps with...","choices":["Avoiding re-renders of children","Caching expensive computations between renders","Replacing state","Fetching data"],"answer":"Caching expensive computations between renders","given":"Caching expensive computations between renders","correct":true,"explanation":"useMemo memoises a computed value and recomputes only when its dependencies change."}]'::jsonb,92,now() - interval '1 day'),
('90000000-0000-4000-8000-000000000004','70000000-0000-4000-8000-000000000009','c0000000-0000-4000-8000-000000000002','short','[{"q":"Why can wrapping a component in React.memo fail to prevent re-renders?","answer":"Because props such as inline objects or callbacks get a new identity each render.","given":"Because memo only works for class components.","correct":false,"explanation":"React.memo does a shallow prop comparison; inline object/function props change identity every render, defeating it."}]'::jsonb,44,now() - interval '2 days'),
('90000000-0000-4000-8000-000000000005','70000000-0000-4000-8000-00000000000c','c0000000-0000-4000-8000-000000000003','mcq','[{"q":"Which traversal uses a queue?","choices":["DFS","BFS","Topological sort","Binary search"],"answer":"BFS","given":"DFS","correct":false,"explanation":"BFS explores level by level using a FIFO queue; DFS uses a stack (or recursion)."},{"q":"Time complexity of BFS on an adjacency list?","choices":["O(V)","O(E)","O(V+E)","O(V*E)"],"answer":"O(V+E)","given":"O(V+E)","correct":true,"explanation":"Every vertex is enqueued once and every edge inspected once."}]'::jsonb,50,now() - interval '3 days'),
('90000000-0000-4000-8000-000000000006','70000000-0000-4000-8000-00000000000d','c0000000-0000-4000-8000-000000000003','mixed','[{"q":"What two properties must a problem have for DP to apply?","answer":"Optimal substructure and overlapping subproblems.","given":"Recursion and memoisation.","correct":false,"explanation":"Memoisation is the technique; the problem properties are optimal substructure and overlapping subproblems."}]'::jsonb,18,now() - interval '1 day'),
('90000000-0000-4000-8000-000000000007','70000000-0000-4000-8000-00000000000e','c0000000-0000-4000-8000-000000000004','mcq','[{"q":"ReLU is preferred over sigmoid mainly because it...","choices":["Is bounded","Mitigates vanishing gradients","Is probabilistic","Is smooth everywhere"],"answer":"Mitigates vanishing gradients","given":"Mitigates vanishing gradients","correct":true,"explanation":"ReLU has a constant gradient of 1 for positive inputs, so gradients do not shrink through deep stacks."}]'::jsonb,89,now() - interval '3 days'),
('90000000-0000-4000-8000-000000000008','70000000-0000-4000-8000-000000000011','c0000000-0000-4000-8000-000000000004','mcq','[{"q":"An LSTM forget gate controls...","choices":["Which inputs are embedded","How much of the previous cell state is retained","The learning rate","Dropout probability"],"answer":"How much of the previous cell state is retained","given":"The learning rate","correct":false,"explanation":"The forget gate outputs a 0-1 mask multiplied into the previous cell state, deciding what is carried forward."}]'::jsonb,42,now() - interval '6 days'),
('90000000-0000-4000-8000-000000000009','70000000-0000-4000-8000-000000000013','c0000000-0000-4000-8000-000000000005','short','[{"q":"Why can adding an index slow down a workload?","answer":"Indexes must be maintained on every insert, update and delete.","given":"Indexes make reads slower.","correct":false,"explanation":"Indexes speed up reads but add write amplification and storage cost."}]'::jsonb,36,now() - interval '3 days'),
('90000000-0000-4000-8000-00000000000a','70000000-0000-4000-8000-000000000007','c0000000-0000-4000-8000-000000000002','mcq','[{"q":"Context re-renders every consumer when...","choices":["Any parent renders","The provider value identity changes","A child calls setState","Never"],"answer":"The provider value identity changes","given":"The provider value identity changes","correct":true,"explanation":"Consumers subscribe to the context value by identity, so a new object each render re-renders all of them."}]'::jsonb,58,now() - interval '4 days');

INSERT INTO public.study_events (topic_id, event_type, scheduled_at, status) VALUES
('70000000-0000-4000-8000-000000000003','review', date_trunc('day', now()) + interval '9 hours', 'scheduled'),
('70000000-0000-4000-8000-00000000000d','quiz', date_trunc('day', now()) + interval '18 hours', 'scheduled'),
('70000000-0000-4000-8000-00000000000c','study_block', date_trunc('day', now()) + interval '1 day 10 hours', 'scheduled'),
('70000000-0000-4000-8000-000000000009','review', date_trunc('day', now()) + interval '1 day 20 hours', 'scheduled'),
('70000000-0000-4000-8000-000000000011','quiz', date_trunc('day', now()) + interval '2 days 9 hours', 'scheduled'),
('70000000-0000-4000-8000-000000000013','review', date_trunc('day', now()) + interval '3 days 8 hours', 'scheduled'),
('70000000-0000-4000-8000-000000000005','study_block', date_trunc('day', now()) + interval '3 days 19 hours', 'scheduled'),
('70000000-0000-4000-8000-000000000002','review', date_trunc('day', now()) + interval '4 days 9 hours', 'scheduled'),
('70000000-0000-4000-8000-00000000000b','quiz', date_trunc('day', now()) + interval '5 days 17 hours', 'scheduled'),
('70000000-0000-4000-8000-000000000007','review', date_trunc('day', now()) + interval '6 days 9 hours', 'scheduled'),
('70000000-0000-4000-8000-000000000010','study_block', date_trunc('day', now()) + interval '8 days 11 hours', 'scheduled'),
('70000000-0000-4000-8000-000000000014','review', date_trunc('day', now()) + interval '10 days 9 hours', 'scheduled'),
('70000000-0000-4000-8000-000000000004','quiz', date_trunc('day', now()) + interval '12 days 16 hours', 'scheduled'),
('70000000-0000-4000-8000-000000000001','review', date_trunc('day', now()) - interval '2 days' + interval '9 hours', 'completed'),
('70000000-0000-4000-8000-000000000006','quiz', date_trunc('day', now()) - interval '1 day' + interval '15 hours', 'completed');

INSERT INTO public.recommendations (topic_id, type, impact_score, estimated_minutes, reasoning) VALUES
('70000000-0000-4000-8000-00000000000d','revisit_weak_topic',94,35,'Mastery is 24 with a -5.4 weekly trend. Quiz performance (18%) is the dominant drag and 8 revisits suggest re-watching without consolidation. A worked-example drill converts passive rewatching into retrieval practice.'),
('70000000-0000-4000-8000-00000000000c','revisit_weak_topic',88,25,'Graph traversal underpins Dynamic Programming on graphs, which is scheduled next. Closing this 29-point mastery gap first prevents compounding failure downstream.'),
('70000000-0000-4000-8000-000000000003','revisit_weak_topic',81,30,'Largest completion-to-mastery gap in Machine Learning A-Z: 78% watched but only 41 mastery. Retrieval on the kernel trick and margin definition should recover most of the gap.'),
('70000000-0000-4000-8000-000000000009','proceed_next_module',66,20,'Performance Optimization is trending down (-2.7). A short profiling exercise plus one quiz will stabilise it before you move on to server components.'),
('70000000-0000-4000-8000-000000000011','start_related_skill',59,45,'Sequence Models mastery (48) is below the specialization average. Attention mechanisms build directly on it, so studying them now yields transfer to two later modules.'),
('70000000-0000-4000-8000-000000000013','revisit_weak_topic',54,20,'Indexing & Query Plans has high revisit frequency but low time-on-section, a classic skim pattern. One EXPLAIN-reading exercise is enough to shift it.');

INSERT INTO public.activity_log (course_id, event_type, metadata, created_at) VALUES
('c0000000-0000-4000-8000-000000000003','quiz_completed','{"topic":"Dynamic Programming","score":18}'::jsonb, now() - interval '3 hours'),
('c0000000-0000-4000-8000-000000000001','topic_revisit','{"topic":"Support Vector Machines","revisits":6}'::jsonb, now() - interval '7 hours'),
('c0000000-0000-4000-8000-000000000002','mastery_updated','{"topic":"React Hooks","delta":5.6}'::jsonb, now() - interval '11 hours'),
('c0000000-0000-4000-8000-000000000004','calendar_event_created','{"topic":"Sequence Models","event":"quiz"}'::jsonb, now() - interval '1 day'),
('c0000000-0000-4000-8000-000000000002','quiz_completed','{"topic":"React Hooks","score":92}'::jsonb, now() - interval '1 day 4 hours'),
('c0000000-0000-4000-8000-000000000005','transcript_captured','{"topic":"Indexing & Query Plans","minutes":18}'::jsonb, now() - interval '2 days'),
('c0000000-0000-4000-8000-000000000001','quiz_completed','{"topic":"Support Vector Machines","score":36}'::jsonb, now() - interval '2 days 2 hours'),
('c0000000-0000-4000-8000-000000000003','topic_revisit','{"topic":"Graph Traversal","revisits":7}'::jsonb, now() - interval '2 days 9 hours'),
('c0000000-0000-4000-8000-000000000004','quiz_completed','{"topic":"Neural Network Basics","score":89}'::jsonb, now() - interval '3 days'),
('c0000000-0000-4000-8000-000000000002','calendar_event_created','{"topic":"Context & Redux","event":"review"}'::jsonb, now() - interval '4 days');
