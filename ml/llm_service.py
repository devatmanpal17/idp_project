"""
Cognivue ML — LLM Service
Multi-provider LLM generation and evaluation engine supporting:
1. Google Gemini (1.5 / 2.0 Flash)
2. OpenAI (GPT-4o-mini)
3. Local Intelligent RAG Generator & Grader
"""

import os
import json
import random
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional

from .calibration import compute_mastery_update

# Question library for zero-key local generation fallback, grounded in RAG contexts
TOPIC_QUESTION_BANK: Dict[str, List[Dict[str, Any]]] = {
    "Support Vector Machines": [
        {
            "q": "In a soft-margin SVM, increasing the hyperparameter C causes the model to...",
            "choices": [
                "Tolerate more margin violations",
                "Penalize misclassifications and margin violations more heavily",
                "Increase the number of kernel dimensions",
                "Remove support vectors from the training set"
            ],
            "answer": "Penalize misclassifications and margin violations more heavily",
            "why": "C acts as an inverse regularization parameter. A larger C puts higher weight on penalizing slack variables xi, forcing smaller margins with fewer violations, which can increase risk of overfitting."
        },
        {
            "q": "Which statement precisely describes the role of support vectors?",
            "choices": [
                "Every single point in the training dataset is classified as a support vector",
                "Only data points lying on or inside the margin boundaries determine the decision hyperplane",
                "Support vectors are randomly sampled to reduce computational complexity",
                "Support vectors are pruned before optimization begins"
            ],
            "answer": "Only data points lying on or inside the margin boundaries determine the decision hyperplane",
            "why": "Removing any non-support vector leaves the optimal separating hyperplane completely unchanged — this sparsity is the defining mathematical property of Support Vector Machines."
        },
        {
            "q": "Why is the Radial Basis Function (RBF) kernel often chosen as a default non-linear kernel?",
            "choices": [
                "It restricts the feature space to exactly two dimensions",
                "It implicitly projects inputs into an infinite-dimensional Hilbert space with only gamma to tune",
                "It guarantees zero training and test error on any dataset",
                "It eliminates the need for calculating inner products"
            ],
            "answer": "It implicitly projects inputs into an infinite-dimensional Hilbert space with only gamma to tune",
            "why": "The RBF kernel computes similarity as exp(-gamma ||x - z||^2), corresponding to an infinite-dimensional space that can separate complex non-linear boundaries with minimal parameter tuning."
        },
        {
            "q": "What is the primary computational benefit of the Kernel Trick in SVMs?",
            "choices": [
                "It calculates inner products in high-dimensional feature spaces without explicitly computing transformed coordinates",
                "It speeds up database indexing by sorting training rows",
                "It transforms the objective function from convex to linear",
                "It replaces quadratic programming with ordinary least squares"
            ],
            "answer": "It calculates inner products in high-dimensional feature spaces without explicitly computing transformed coordinates",
            "why": "The kernel trick replaces phi(x) dot phi(z) with K(x, z), avoiding the astronomical or infinite memory cost of explicit high-dimensional feature representation."
        }
    ],
    "Linear Regression": [
        {
            "q": "What objective function does the Ordinary Least Squares (OLS) method minimize?",
            "choices": [
                "The sum of squared vertical residuals between actual and predicted values",
                "The maximum absolute residual across all training points",
                "The variance of the independent features",
                "The sum of absolute percentage errors"
            ],
            "answer": "The sum of squared vertical residuals between actual and predicted values",
            "why": "OLS computes parameter estimates beta by finding the hyperplane that minimizes the sum of squared differences between observed y and predicted y_hat."
        },
        {
            "q": "What does an R-squared value of 0.0 indicate about a linear regression model?",
            "choices": [
                "The model is overfitted to the training data",
                "The model explains none of the variance in the target variable beyond predicting the mean",
                "The model has achieved a zero residual error",
                "The regression line has an infinite slope"
            ],
            "answer": "The model explains none of the variance in the target variable beyond predicting the mean",
            "why": "R-squared measures the proportion of total variance explained by the regression. A value of 0.0 means the model performs no better than predicting the mean of y."
        }
    ],
    "React Hooks": [
        {
            "q": "When does a useEffect hook with an empty dependency array `[]` execute?",
            "choices": [
                "Before every DOM mutation",
                "Once after the initial render and mount",
                "Only when the component unmounts",
                "On every state update across the entire app"
            ],
            "answer": "Once after the initial render and mount",
            "why": "An empty dependency array informs React that the effect does not depend on any reactive props or state, so it runs once after mount and cleans up on unmount."
        },
        {
            "q": "What is the primary difference between useMemo and useCallback?",
            "choices": [
                "useMemo caches a computed return value; useCallback caches a function definition identity",
                "useCallback is for async operations; useMemo is strictly synchronous",
                "useMemo triggers re-renders; useCallback prevents DOM paints",
                "There is no difference; they are aliases in React 19"
            ],
            "answer": "useMemo caches a computed return value; useCallback caches a function definition identity",
            "why": "useMemo(() => compute(), [deps]) returns the memoized value, while useCallback(fn, [deps]) returns the memoized function reference itself."
        }
    ],
    "Graph Traversal": [
        {
            "q": "Which data structure is utilized by Breadth-First Search (BFS) to manage vertex visitation order?",
            "choices": [
                "A First-In First-Out (FIFO) Queue",
                "A Last-In First-Out (LIFO) Stack",
                "A Fibonacci Heap",
                "A Hash Set without ordering"
            ],
            "answer": "A First-In First-Out (FIFO) Queue",
            "why": "BFS visits vertices in order of their level/distance from the starting node, requiring a FIFO queue to process neighbors in arrival order."
        },
        {
            "q": "What is the standard time complexity of BFS on a graph with V vertices and E edges represented as an adjacency list?",
            "choices": [
                "O(V + E)",
                "O(V * E)",
                "O(V^2)",
                "O(E log V)"
            ],
            "answer": "O(V + E)",
            "why": "Every vertex is enqueued and dequeued at most once (O(V)), and every edge adjacency list is scanned once in directed or twice in undirected graphs (O(E))."
        }
    ],
    "Dynamic Programming": [
        {
            "q": "What two fundamental characteristics are required for Dynamic Programming to be applicable to a problem?",
            "choices": [
                "Optimal substructure and overlapping subproblems",
                "Greedy choice property and disjoint subgraphs",
                "Exponential state space and randomized pivots",
                "Linear constraints and sorting invariance"
            ],
            "answer": "Optimal substructure and overlapping subproblems",
            "why": "Optimal substructure ensures the global optimum is composed of subproblem optima, and overlapping subproblems ensures solving and caching subproblems avoids exponential recomputation."
        }
    ]
};


class LLMService:
    def __init__(self):
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        self.preferred_provider = os.environ.get("AI_PROVIDER", "auto")

    def configure(self, provider: str, api_key: str):
        """Update API configuration at runtime."""
        self.preferred_provider = provider
        if provider == "gemini":
            self.gemini_api_key = api_key
        elif provider == "openai":
            self.openai_api_key = api_key

    def generate_quiz_with_rag(
        self,
        topic: str,
        context_chunks: List[Dict[str, Any]],
        mastery_score: float,
        difficulty: float,
        count: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Generate structured quiz questions grounded in retrieved RAG context chunks.
        """
        # Try Gemini API if key is available
        if (self.preferred_provider in ["auto", "gemini"]) and self.gemini_api_key:
            try:
                gemini_res = self._call_gemini_rag(topic, context_chunks, difficulty, count)
                if gemini_res:
                    return gemini_res
            except Exception as e:
                print(f"[LLMService] Gemini error: {e}, falling back to local engine")

        # Try OpenAI API if key is available
        if (self.preferred_provider in ["auto", "openai"]) and self.openai_api_key:
            try:
                openai_res = self._call_openai_rag(topic, context_chunks, difficulty, count)
                if openai_res:
                    return openai_res
            except Exception as e:
                print(f"[LLMService] OpenAI error: {e}, falling back to local engine")

        # Fallback to local intelligent generative engine
        return self._generate_local_rag(topic, context_chunks, difficulty, count)

    def _call_gemini_rag(
        self,
        topic: str,
        chunks: List[Dict[str, Any]],
        difficulty: float,
        count: int
    ) -> Optional[List[Dict[str, Any]]]:
        """Direct HTTP call to Google Gemini API (gemini-1.5-flash / gemini-2.0-flash)."""
        context_text = "\n\n".join([f"[{c.get('chunk_id', 'chunk')}] {c.get('snippet', '')}" for c in chunks])
        prompt = f"""You are Cognivue's AI learning tutor. Using the retrieved lecture context below, generate {count} high-quality assessment questions for the topic '{topic}'.
Target difficulty level: {difficulty:.2f} (0.0=easy, 1.0=advanced).

Context chunks:
{context_text}

Return strictly a JSON array of question objects adhering to this schema:
[
  {{
    "q": "Question prompt text",
    "choices": ["Option A", "Option B", "Option C", "Option D"],
    "answer": "Option B",
    "why": "Detailed pedagogical explanation citing why the answer is correct based on the context."
  }}
]
Do not include markdown code block ticks, only valid JSON.
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.4
            }
        }

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=12) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            questions = json.loads(raw_text)
            if isinstance(questions, list) and len(questions) > 0:
                return questions
        return None

    def _call_openai_rag(
        self,
        topic: str,
        chunks: List[Dict[str, Any]],
        difficulty: float,
        count: int
    ) -> Optional[List[Dict[str, Any]]]:
        """Direct HTTP call to OpenAI API (gpt-4o-mini)."""
        context_text = "\n\n".join([f"[{c.get('chunk_id', 'chunk')}] {c.get('snippet', '')}" for c in chunks])
        system_prompt = "You are Cognivue's AI learning companion. You generate rigorous assessment questions grounded strictly in provided lecture transcripts. Output valid JSON only."
        user_prompt = f"""Generate {count} multiple choice questions for '{topic}' with difficulty {difficulty:.2f}.
Context:
{context_text}

JSON Schema:
[
  {{
    "q": "Question",
    "choices": ["Choice 1", "Choice 2", "Choice 3", "Choice 4"],
    "answer": "Choice 1",
    "why": "Explanation"
  }}
]
"""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_api_key}"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3
        }

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=12) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            content = res_data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict) and "questions" in parsed:
                return parsed["questions"]
        return None

    def _generate_local_rag(
        self,
        topic: str,
        chunks: List[Dict[str, Any]],
        difficulty: float,
        count: int
    ) -> List[Dict[str, Any]]:
        """
        Intelligent local RAG generator synthesizing grounded questions from domain chunks.
        """
        # Match from known bank if available
        matched_bank = []
        for bank_topic, q_list in TOPIC_QUESTION_BANK.items():
            if bank_topic.lower() in topic.lower() or topic.lower() in bank_topic.lower():
                matched_bank = list(q_list)
                break

        if matched_bank:
            random.shuffle(matched_bank)
            selected = matched_bank[:count]
            if len(selected) < count and chunks:
                for c in chunks:
                    if len(selected) >= count:
                        break
                    snippet = c.get("snippet", "")
                    selected.append({
                        "q": f"Based on the transcript section at {c.get('timestamp', '00:00')}, what principle is established regarding {topic}?",
                        "choices": [
                            f"Core operational rule: {snippet[:75]}...",
                            "The parameter values must be randomized uniformly",
                            "Data normalization is bypassed in all stages",
                            "The computational cost scales exponentially with constant factor"
                        ],
                        "answer": f"Core operational rule: {snippet[:75]}...",
                        "why": f"Cited directly from {c.get('chunk_id', 'chunk')}: '{snippet}'."
                    })
            return selected[:count]

        # Dynamic synthesis from retrieved RAG chunks
        synthesized: List[Dict[str, Any]] = []
        for i, c in enumerate(chunks[:count]):
            snippet = c.get("snippet", "")
            synthesized.append({
                "q": f"According to the lecture transcript on {topic}, which principle applies?",
                "choices": [
                    f"Verified principle: {snippet[:80]}...",
                    "The model assumes infinite variance across all training splits",
                    "Feature values are discarded prior to boundary determination",
                    "Optimization converges in negative iterations"
                ],
                "answer": f"Verified principle: {snippet[:80]}...",
                "why": f"Derived from {c.get('chunk_id', 'context chunk')} ({c.get('course', 'Course')}): '{snippet}'."
            })

        if not synthesized:
            synthesized.append({
                "q": f"What is the foundational requirement for mastering {topic}?",
                "choices": [
                    "Synthesizing theoretical foundations with empirical application",
                    "Memorizing isolated terminology without context",
                    "Disregarding prerequisite mathematical assumptions",
                    "Restricting model evaluation to the training set only"
                ],
                "answer": "Synthesizing theoretical foundations with empirical application",
                "why": "Retention and comprehension require deep retrieval practice and structured mental models."
            })

        return synthesized

    def evaluate_quiz(
        self,
        questions: List[Dict[str, Any]],
        given_answers: List[str],
        current_mastery: float
    ) -> Dict[str, Any]:
        """
        Evaluates student responses, produces detailed feedback, and computes mastery score update.
        """
        results = []
        correct_count = 0

        for q, given in zip(questions, given_answers):
            expected = q.get("answer", "")
            is_correct = (
                given.strip().lower() == expected.strip().lower() or
                (len(given) > 10 and (given.lower() in expected.lower() or expected.lower() in given.lower()))
            )
            if is_correct:
                correct_count += 1

            results.append({
                "question": q.get("q", ""),
                "given_answer": given,
                "expected_answer": expected,
                "is_correct": is_correct,
                "explanation": q.get("why", "")
            })

        total = len(questions) or 1
        score_pct = round((correct_count / total) * 100, 1)

        # Update mastery
        mastery_info = compute_mastery_update(score_pct, current_mastery)

        return {
            "score": score_pct,
            "correct_count": correct_count,
            "total_questions": total,
            "evaluations": results,
            "previous_mastery": current_mastery,
            "new_mastery": mastery_info["new_mastery"],
            "mastery_delta": mastery_info["mastery_delta"],
            "feedback_summary": (
                "Outstanding comprehension! Concepts solidified."
                if score_pct >= 80
                else "Good effort. Review the specific explanations on miss-identified concepts."
                if score_pct >= 50
                else "Needs reinforcement. Recommendation added to your study plan to review transcript chunks."
            )
        }


# Global Singleton LLM Service
llm_service = LLMService()
