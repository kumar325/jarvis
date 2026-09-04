"""Evaluate Himavat against a fixed set of test queries using UpTrain's EvalLLM.

Test queries are split into categories that each isolate one personalization feature:
  - profile: correct answer depends on knowing the user is vegetarian / works night shifts
  - memory:  explicitly tests whether remembered facts surface in the response
  - style:   open-ended questions where style mirroring should change tone/length
  - web:     current-events questions with a profile-independent correct answer
  - general: tool-independent control queries (math, trivia)

For each (ablation config, query) pair we:
  1. call ask_jarvis() directly (no voice) and capture the reply,
  2. capture every tool call the agent made as "retrieved context",
  3. snapshot which personalization signals were active (system state) and whether
     any of them actually left a trace in the response (personalization_used),
  4. score the (question, context, response) triple with UpTrain on 4 general metrics,
     plus a 5th metric — ground_truth_adherence — for queries with a ground_truth_expectation,
  5. write one row per query per ablation per metric to a CSV, along with a
     delta_<metric> column (full_score - ablated_score) per query.

user_profile.json is backed up before the run and restored after, since the `remember`
tool used by the memory-recall queries writes to that file for real.

Usage:
    python eval/run_eval.py                       # run all ablations, all queries
    python eval/run_eval.py --ablations full,no_web_search
    python eval/run_eval.py --limit 2             # quick smoke test
    python eval/run_eval.py --model groq/llama-3.3-70b-versatile
"""
import argparse
import json
import sys
from datetime import datetime
from itertools import groupby
from pathlib import Path

# Corporate SSL certs break litellm's/httpx's default verification — same fix jarvis.py uses.
import truststore
truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so `import agent_loop`, `import system_prompt` etc. resolve

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import pandas as pd
from uptrain import EvalLLM, GuidelineAdherence, Settings, Evals

from agent_loop import ask_jarvis
from user_profile import PROFILE_FILE
from ablations import (
    ABLATION_PATCHES, apply_ablation, capture_tool_trace, check_personalization_used,
    preserve_file, reset_conversation, snapshot_system_state,
)

METRICS = {
    "context_relevance": Evals.CONTEXT_RELEVANCE,
    "response_relevance": Evals.RESPONSE_RELEVANCE,
    "response_completeness": Evals.RESPONSE_COMPLETENESS,
    "factual_accuracy": Evals.FACTUAL_ACCURACY,
}
# All metrics that get a delta_<name> column, including the ground-truth one scored separately.
ALL_METRIC_NAMES = list(METRICS.keys()) + ["ground_truth_adherence"]


def load_queries(path: Path, limit: int | None) -> list[dict]:
    queries = json.loads(path.read_text(encoding="utf-8"))
    return queries[:limit] if limit else queries


def run_query(query: str) -> dict:
    """Run one query through Himavat and collect response + retrieved context + system state."""
    reset_conversation()
    with capture_tool_trace() as trace:
        response = ask_jarvis(query)
    state = snapshot_system_state(query)
    personalization_used = check_personalization_used(
        response,
        state.pop("_facts"),
        state.pop("_profile_summary"),
        state.pop("_style_summary"),
        state.pop("_good_examples"),
        state.pop("_bad_examples"),
    )
    context = "\n\n".join(f"[{t['tool']}] {t['result']}" for t in trace)
    return {
        "response": response,
        "context": context or "(no tools were called for this query)",
        "num_tool_calls": len(trace),
        "tools_used": ",".join(sorted({t["tool"] for t in trace})) or "none",
        "personalization_used": personalization_used,
        **state,
    }


def score_ground_truth_adherence(client: EvalLLM, rows: list[dict]) -> pd.DataFrame:
    """Score rows that carry a ground_truth_expectation with UpTrain's GuidelineAdherence.
    The guideline text is fixed per judge call, so rows are grouped by identical
    expectation text (shared across ablations for the same query) to minimize judge calls.
    Returns a DataFrame with just the join keys + the new score/explanation columns."""
    gt_rows = [r for r in rows if r.get("ground_truth_expectation")]
    if not gt_rows:
        return pd.DataFrame(columns=["ablation", "query_id", "score_ground_truth_adherence",
                                      "explanation_ground_truth_adherence"])

    scored_rows = []
    gt_rows_sorted = sorted(gt_rows, key=lambda r: r["ground_truth_expectation"])
    for expectation, group in groupby(gt_rows_sorted, key=lambda r: r["ground_truth_expectation"]):
        group = list(group)
        check = GuidelineAdherence(guideline=expectation, guideline_name="ground_truth")
        scored_rows.extend(client.evaluate(data=group, checks=[check], project_name="jarvis-eval"))

    return pd.DataFrame(scored_rows)[["ablation", "query_id", "score_ground_truth_adherence",
                                       "explanation_ground_truth_adherence"]]


def add_delta_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add delta_<metric> = full_score - ablated_score, per query, for every metric.
    This is the number that quantifies each feature's contribution."""
    score_cols = [f"score_{m}" for m in ALL_METRIC_NAMES]
    if "full" not in df["ablation"].unique():
        print("\nWARNING: no 'full' ablation in this run — delta_* columns will be empty "
              "(nothing to compare against).")
    full_scores = df[df["ablation"] == "full"].drop_duplicates("query_id").set_index("query_id")
    for col in score_cols:
        delta_col = col.replace("score_", "delta_")
        if col in full_scores.columns:
            df[delta_col] = df["query_id"].map(full_scores[col]) - df[col]
        else:
            df[delta_col] = None
    return df


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--queries", default=str(ROOT / "eval" / "test_queries.json"))
    parser.add_argument("--ablations", default="all", help="comma-separated ablation names, or 'all'")
    parser.add_argument("--limit", type=int, default=None, help="only run the first N queries (smoke test)")
    parser.add_argument("--model", default="groq/llama-3.3-70b-versatile", help="judge LLM for UpTrain, litellm-style model id")
    parser.add_argument("--out", default=None, help="output CSV path")
    args = parser.parse_args()

    ablation_names = list(ABLATION_PATCHES.keys()) if args.ablations == "all" else args.ablations.split(",")
    queries = load_queries(Path(args.queries), args.limit)

    print(f"Running {len(queries)} queries x {len(ablation_names)} ablation configs = "
          f"{len(queries) * len(ablation_names)} Himavat calls...")

    rows = []
    with preserve_file(PROFILE_FILE):
        for ablation in ablation_names:
            print(f"\n=== ablation: {ablation} ===")
            with apply_ablation(ablation):
                for q in queries:
                    print(f"  -> {q['id']}: {q['query']}")
                    result = run_query(q["query"])
                    rows.append({
                        "ablation": ablation,
                        "query_id": q["id"],
                        "category": q.get("category", "general"),
                        "question": q["query"],
                        "ground_truth_expectation": q.get("ground_truth_expectation"),
                        **result,
                    })

    print(f"\nScoring {len(rows)} responses with UpTrain (judge model: {args.model})...")
    settings = Settings(model=args.model)
    client = EvalLLM(settings)
    scored = client.evaluate(
        data=rows,
        checks=list(METRICS.values()),
        project_name="jarvis-eval",
    )
    df = pd.DataFrame(scored)

    print("Scoring ground_truth_adherence for profile/memory/style queries...")
    gt_df = score_ground_truth_adherence(client, rows)
    df = df.merge(gt_df, on=["ablation", "query_id"], how="left")

    df = add_delta_columns(df)

    out_path = Path(args.out) if args.out else ROOT / "eval" / "results" / f"eval_scores_{datetime.now():%Y%m%d_%H%M%S}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\nSaved {len(df)} rows to {out_path}")

    score_cols = [f"score_{m}" for m in ALL_METRIC_NAMES]
    delta_cols = [c.replace("score_", "delta_") for c in score_cols]

    print("\nMean score per ablation config:")
    print(df.groupby("ablation")[score_cols].mean().round(3))

    print("\nMean delta (full - ablated) per ablation config — feature contribution:")
    print(df.groupby("ablation")[delta_cols].mean().round(3))

    print("\npersonalization_used rate by ablation x category:")
    print(df.groupby(["ablation", "category"])["personalization_used"].mean().round(3))


if __name__ == "__main__":
    main()
