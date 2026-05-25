# Semantic Annotations, Evolution, & Validation State

This document outlines the temporal structures of Synapse, explaining how semantic annotations are extracted, how validation states are calculated, and how branch context merges are resolved.

---

## 1. Subsystem Architecture

### Ingestion & Structure Ingestion Pipeline
Extracts semantic observations from repository source files and Markdown documentation.

```mermaid
flowchart TD
    Scan[Repository Scan] --> Filters[Exclusion Filters]
    Filters --> Manifests[Manifest Discovery]
    Filters --> Markdown[Markdown Ingestion]
    Filters --> Parser[Tree-sitter AST Parser]
    
    Manifests --> Builder[Context Substrate Builder]
    Markdown --> Builder
    Parser --> Builder
    
    Builder --> SemObjects[Semantic Objects]
    Builder --> Nodes[Graph Nodes]
    Builder --> Edges[Graph Edges]
```

- **WHY**: Raw source text is too noisy for LLM context limits. We need a parser that extracts structured semantic nodes (definitions, decisions, assumptions) to create a bounded model.
- **HOW**: Markdown is parsed into headings and blocks, while code structure is parsed using tree-sitter AST nodes. These are transformed into content-addressed `SemanticObject` and graph representations.
- **TRADEOFFS**: Fine-grained AST parsing can be slower on massive source trees; addressed by scanning only modified files.

---

### Validation State & Drift Engine
Tracks fact validity, freshness decay, contradictions, and workspace divergence.

```mermaid
graph TD
    Evidence[Evidence Count] --> Score{Confidence Engine}
    Freshness[Freshness Decay] --> Score
    Trust[Provenance Trust] --> Score
    Contradict[Contradiction Count] --> Score
    Score --> FinalScore[Validation State]
    
    FinalScore --> Propagate[Propagate Upstream Trust]
    Propagate --> GitDiff[Compare Scan vs Git HEAD]
    GitDiff --> Drift[Drift Analysis Engine]
```

- **WHY**: Context deteriorates as code changes. If documentation asserts behavior that is no longer supported by code, drift accumulates and confidence should decay.
- **HOW**: `ConfidenceEngine` runs freshness decay based on a mathematical half-life. Contradictory facts apply penalty coefficients. `DriftDetector` computes git-diff lines to flag out-of-sync documents.
- **TRADEOFFS**: Constant decay calculations add complexity. The engine computes them on demand during queries or compaction checkpoints.

---

## 2. Pipeline & Workflow Diagrams

### Context Evolution & Semantic Diff
Analyzes modifications, additions, and invalidations between two context hashes.

```mermaid
sequenceDiagram
    participant API as API/CLI
    participant Diff as SemanticImpactEngine
    participant Store as SQLiteEventStore
    
    API->>Diff: analyze(left_hash, right_hash)
    Diff->>Store: Get context details & active objects
    Diff->>Diff: Align stable IDs
    Diff->>Diff: Check for changed summaries / attributes
    Diff->>Diff: Check for newly invalidated assumptions
    Diff-->>API: return SemanticDiff & ImpactReport
```

- **WHY**: Developers need to see how the system's architecture model evolved across branches or commits.
- **HOW**: The diff engine queries the reconstructed fact graphs at both context hashes and compares them key-by-key, cataloging additions, removals, and replacements.

---

### Assumption Invalidation Cascade
When code changes or incidents are logged, connected assumptions are invalidated.

```mermaid
flowchart TD
    Incident[New Incident Record] --> Anchor[Anchor to Git Commit]
    Anchor --> Extract[Identify Broken Assumed Nodes]
    Extract --> Invalidate[Set valid_to_context of Assumption]
    Invalidate --> Cascade[Reduce confidence of dependent modules]
    Cascade --> Alert[Flag Architectural Conflict]
```

- **WHY**: When a production incident occurs due to database session loss, the assumption "Database is always online" is proven invalid.
- **HOW**: The incident anchoring maps the time/commit of the incident, finds linked assumptions, and sets their validity intervals, immediately downgrading dependent modules' trust scores.

---

### Branch Context Merge Flow
Detects causal merge conflicts between diverging branches.

```mermaid
flowchart TD
    Left[Left Head Hash] --> LCA[Find Lowest Common Ancestor]
    Right[Right Head Hash] --> LCA
    
    LCA --> DiffLeft[Diff LCA to Left]
    LCA --> DiffRight[Diff LCA to Right]
    
    DiffLeft --> Detect[Detect Overlapping Semantic Mutations]
    DiffRight --> Detect
    
    Detect --> Overlap{Same stable_id modified on both?}
    Overlap -- Yes --> Conflict[Create Merge Conflict Record]
    Overlap -- No --> AutoMerge[Mark as Cleanly Auto-Mergeable]
```

- **WHY**: Like git conflicts, contextual understanding can diverge on different development branches (e.g. branch A assumes sqlite, branch B assumes postgres).
- **HOW**: Traverses parent edges in the context DAG to find the lowest common ancestor, compares left and right deltas, and identifies overlapping mutations.
