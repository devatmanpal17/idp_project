"""
ChaiGaram ML — Knowledge Base Corpus
Comprehensive MOOC lecture transcript corpus indexed by topic and course.
"""

from typing import List, Dict, Any

KNOWLEDGE_BASE: Dict[str, List[Dict[str, Any]]] = {
    "Support Vector Machines": [
        {
            "id": "chunk_0417",
            "topic": "Support Vector Machines",
            "course": "Machine Learning A-Z",
            "timestamp": "14:20",
            "text": "The kernel trick maps inputs implicitly into a higher-dimensional Hilbert feature space without calculating the explicit coordinate coordinates. By evaluating the kernel function K(x, z) = phi(x) dot phi(z), non-linear decision boundaries become linear hyperplanes in the transformed space.",
        },
        {
            "id": "chunk_0419",
            "topic": "Support Vector Machines",
            "course": "Machine Learning A-Z",
            "timestamp": "18:45",
            "text": "Support vectors are the critical data points lying exactly on or violating the margin boundaries (w dot x + b = +-1). Removing any non-support vector leaves the optimal separating hyperplane completely unchanged, yielding model sparsity.",
        },
        {
            "id": "chunk_0512",
            "topic": "Support Vector Machines",
            "course": "Machine Learning A-Z",
            "timestamp": "22:10",
            "text": "In soft-margin SVMs, the regularization hyperparameter C controls the trade-off between maximizing the margin width and penalizing margin slack violations xi_i. A large C heavily penalizes misclassifications, leading to narrower margins and potential overfitting.",
        },
        {
            "id": "chunk_0388",
            "topic": "Support Vector Machines",
            "course": "Machine Learning A-Z",
            "timestamp": "26:30",
            "text": "The Radial Basis Function (RBF) kernel K(x, z) = exp(-gamma ||x - z||^2) corresponds to an infinite-dimensional feature space. The gamma parameter sets the reach of individual training samples; high gamma implies high curvature and sensitive decision boundaries.",
        },
        {
            "id": "chunk_0520",
            "topic": "Support Vector Machines",
            "course": "Machine Learning A-Z",
            "timestamp": "31:15",
            "text": "The dual formulation of SVM maximizes sum(alpha_i) - 0.5 sum(alpha_i alpha_j y_i y_j K(x_i, x_j)) subject to 0 <= alpha_i <= C and sum(alpha_i y_i) = 0. Sequential Minimal Optimization (SMO) solves this quadratic programming problem analytically.",
        },
        {
            "id": "chunk_0531",
            "topic": "Support Vector Machines",
            "course": "Machine Learning A-Z",
            "timestamp": "36:00",
            "text": "Hinge loss L(y, f(x)) = max(0, 1 - y * f(x)) provides convexity and produces a sparse solution since samples with margin >= 1 have zero gradient and do not become support vectors.",
        }
    ],
    "Linear Regression": [
        {
            "id": "chunk_0101",
            "topic": "Linear Regression",
            "course": "Machine Learning A-Z",
            "timestamp": "04:15",
            "text": "Ordinary Least Squares (OLS) calculates parameters beta = (X^T X)^(-1) X^T y to minimize the sum of squared residuals. The Gauss-Markov theorem states OLS is BLUE (Best Linear Unbiased Estimator) under homoscedasticity.",
        },
        {
            "id": "chunk_0102",
            "topic": "Linear Regression",
            "course": "Machine Learning A-Z",
            "timestamp": "09:30",
            "text": "R-squared coefficient of determination measures the proportion of variance in the dependent variable predictable from independent variables: R^2 = 1 - (SS_res / SS_tot). An R^2 of 0 indicates the model predicts no better than the sample mean.",
        },
        {
            "id": "chunk_0103",
            "topic": "Linear Regression",
            "course": "Machine Learning A-Z",
            "timestamp": "15:40",
            "text": "Multicollinearity occurs when predictor variables are highly correlated, inflating parameter variance and standard errors. Variance Inflation Factor (VIF) greater than 5 or 10 diagnoses severe multicollinearity.",
        }
    ],
    "React Hooks": [
        {
            "id": "chunk_0201",
            "topic": "React Hooks",
            "course": "React - The Complete Guide",
            "timestamp": "12:10",
            "text": "useEffect runs after the browser paints. With an empty dependency array [], it executes exactly once after the initial mount, and its optional returned cleanup function runs on unmount.",
        },
        {
            "id": "chunk_0202",
            "topic": "React Hooks",
            "course": "React - The Complete Guide",
            "timestamp": "18:40",
            "text": "useMemo caches the result of an expensive calculation between renders based on dependency identity. useCallback caches the function definition itself to prevent unnecessary child re-renders when passing callback props.",
        },
        {
            "id": "chunk_0203",
            "topic": "React Hooks",
            "course": "React - The Complete Guide",
            "timestamp": "24:15",
            "text": "The Rules of Hooks state: only call Hooks at the top level of function components or custom hooks, never inside loops, conditions, or nested functions to preserve consistent hook call order in fiber nodes.",
        }
    ],
    "Graph Traversal": [
        {
            "id": "chunk_0301",
            "topic": "Graph Traversal",
            "course": "Data Structures & Algorithms",
            "timestamp": "06:10",
            "text": "Breadth-First Search (BFS) explores vertices level-by-level using a FIFO queue. For an adjacency list representation with V vertices and E edges, BFS has time complexity O(V + E) and finds the shortest path on unweighted graphs.",
        },
        {
            "id": "chunk_0302",
            "topic": "Graph Traversal",
            "course": "Data Structures & Algorithms",
            "timestamp": "14:25",
            "text": "Depth-First Search (DFS) traverses along a branch before backtracking using a LIFO stack or system recursion call stack. It is used for topological sorting, cycle detection, and finding strongly connected components (Kosaraju / Tarjan).",
        },
        {
            "id": "chunk_0303",
            "topic": "Graph Traversal",
            "course": "Data Structures & Algorithms",
            "timestamp": "21:50",
            "text": "Dijkstra's algorithm finds shortest paths in non-negative edge weighted graphs using a min-priority queue (binary heap) with time complexity O((V + E) log V).",
        }
    ],
    "Dynamic Programming": [
        {
            "id": "chunk_0351",
            "topic": "Dynamic Programming",
            "course": "Data Structures & Algorithms",
            "timestamp": "08:15",
            "text": "Dynamic Programming applies to optimization problems exhibiting optimal substructure (optimal solution contains optimal solutions to subproblems) and overlapping subproblems (repeated subproblem evaluations).",
        },
        {
            "id": "chunk_0352",
            "topic": "Dynamic Programming",
            "course": "Data Structures & Algorithms",
            "timestamp": "16:40",
            "text": "Top-down memoization caches recursive call results in a hash table or array, while bottom-up tabulation builds solutions iteratively starting from base cases, often enabling space optimization by maintaining only the last k states.",
        }
    ],
    "Neural Network Basics": [
        {
            "id": "chunk_0401",
            "topic": "Neural Network Basics",
            "course": "Deep Learning Specialization",
            "timestamp": "10:15",
            "text": "Rectified Linear Unit (ReLU) f(x) = max(0, x) solves the vanishing gradient problem in deep networks because its derivative is constant 1 for positive inputs, avoiding exponential decay through chain rule multiplication.",
        },
        {
            "id": "chunk_0402",
            "topic": "Neural Network Basics",
            "course": "Deep Learning Specialization",
            "timestamp": "19:30",
            "text": "Backpropagation computes the gradient of the loss function with respect to weights using the multivariate chain rule, propagating delta error terms backward from output layer to input layer.",
        }
    ],
    "Indexing & Query Plans": [
        {
            "id": "chunk_0501",
            "topic": "Indexing & Query Plans",
            "course": "Databases for Developers",
            "timestamp": "11:20",
            "text": "B-Tree indexes provide O(log N) lookup, range scans, and sorting. While indexes accelerate SELECT queries, they incur write amplification because every INSERT, UPDATE, and DELETE must maintain the index tree structures.",
        },
        {
            "id": "chunk_0502",
            "topic": "Indexing & Query Plans",
            "course": "Databases for Developers",
            "timestamp": "18:05",
            "text": "EXPLAIN ANALYZE shows the actual execution plan: Sequential Scan vs Index Scan vs Bitmap Index Scan. A high cost in the execution plan often reveals missing composite indexes or non-sargable WHERE predicates.",
        }
    ]
}

GENERIC_CHUNKS: List[Dict[str, Any]] = [
    {
        "id": "chunk_gen_01",
        "topic": "General Concept",
        "course": "Core Curriculum",
        "timestamp": "05:00",
        "text": "Foundational definitions and core theoretical assumptions establishing problem scope and invariant constraints.",
    },
    {
        "id": "chunk_gen_02",
        "topic": "General Concept",
        "course": "Core Curriculum",
        "timestamp": "12:30",
        "text": "Algorithmic mechanics, operational steps, state transformations, and complexity trade-offs.",
    },
    {
        "id": "chunk_gen_03",
        "topic": "General Concept",
        "course": "Core Curriculum",
        "timestamp": "21:15",
        "text": "Practical application, error modes, parameter tuning guidelines, and edge case mitigation.",
    }
]
