"""Evaluate Jarvis against a fixed set of test queries using UpTrain's EvalLLM.

For each (ablation config, query) pair we:
  1. call ask_jarvis() directly (no voice) and capture the reply,
  2. capture every tool call the agent made as "retrieved context",
  3. snapshot which personalization signals were active (system state),
  4. score the (question, context, response) triple with UpTrain,
  5. write one row per query per ablation per metric to a CSV.

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
from pathlib import Path

# Corporate SSL certs break litellm's/httpx's default verification — same fix jarvis.py uses.
import truststore
truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so `import agent_loop`, `import system_prompt` etc. resolve

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import pandas as pd
from uptrain import EvalLLM, Settings, Evals

from agent_loop import ask_jarvis
from ablations import ABLATION_PATCHES, apply_ablation, capture_tool_trace, reset_conversation, snapshot_system_state

METRICS = {
    "context_relevance": Evals.CONTEXT_RELEVANCE,
    "response_relevance": Evals.RESPONSE_RELEVANCE,
    "response_completeness": Evals.RESPONSE_COMPLETENESS,
    "factual_accuracy": Evals.FACTUAL_ACCURACY,
}


def load_queries(path: Path, limit: int | None) -> list[dict]:
    queries = json.loads(path.read_text(encoding="utf-8"))
    return queries[:limit] if limit else queries


def run_query(query: str) -> dict:
    """Run one query through Jarvis and collect response + retrieved context + system state."""
    reset_conversation()
    with capture_tool_trace() as trace:
        response = ask_jarvis(query)
    state = snapshot_system_state(query)
    context = "\n\n".join(f"[{t['tool']}] {t['result']}" for t in trace)
    return {
        "response": response,
        "context": context or "(no tools were called for this query)",
        "num_tool_calls": len(trace),
        "tools_used": ",".join(sorted({t["tool"] for t in trace})) or "none",
        **state,
    }


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
          f"{len(queries) * len(ablation_names)} Jarvis calls...")

    rows = []
    for ablation in ablation_names:
        print(f"\n=== ablation: {ablation} ===")
        with apply_ablation(ablation):
            for q in queries:
                print(f"  -> {q['id']}: {q['query']}")
                result = run_query(q["query"])
                rows.append({
                    "ablation": ablation,
                    "query_id": q["id"],
                    "question": q["query"],
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
    out_path = Path(args.out) if args.out else ROOT / "eval" / "results" / f"eval_scores_{datetime.now():%Y%m%d_%H%M%S}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"\nSaved {len(df)} rows to {out_path}")

    score_cols = [f"score_{m}" for m in METRICS]
    print("\nMean score per ablation config:")
    print(df.groupby("ablation")[score_cols].mean().round(3))


if __name__ == "__main__":
    main()
