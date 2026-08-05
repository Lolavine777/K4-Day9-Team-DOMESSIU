import json
import os
import time
from src.repository import DataRepository
from src.llm_client import GroqLLMClient
from src.agents.coordinator import CoordinatorAgent
from src.trace import TraceLogger


def main():
    print("=" * 60)
    print("STARTING MULTI-AGENT E-COMMERCE DISPUTE RESOLUTION PIPELINE")
    print("=" * 60)

    start_time = time.time()

    input_dir = "input"
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    # Initialize shared repository and LLM client
    print("[Pipeline] Loading Olist CSV dataset into DataRepository...")
    repo = DataRepository(data_dir="data")
    print("[Pipeline] Initializing GroqLLMClient (llama-3.1-8b-instant)...")
    llm_client = GroqLLMClient()

    # Initialize CoordinatorAgent
    coordinator = CoordinatorAgent(repo, llm_client)
    trace_logger = TraceLogger(filepath="trace.jsonl")
    trace_logger.clear()

    # Find input files EC_001.json to EC_050.json
    input_files = [f"EC_{i:03d}.json" for i in range(1, 51)]

    print(f"[Pipeline] Processing {len(input_files)} cases...")

    processed_count = 0
    for fname in input_files:
        fpath = os.path.join(input_dir, fname)
        if not os.path.exists(fpath):
            print(f"[Pipeline Warning] Input file missing: {fpath}")
            continue

        with open(fpath, "r", encoding="utf-8") as f:
            case_input = json.load(f)

        case_id = case_input.get("case_id", fname.replace(".json", ""))

        # Run multi-agent pipeline for case
        final_output, trace_entries = coordinator.process_case(case_input)

        # Write output JSON file to output/EC_XXX.json
        out_path = os.path.join(output_dir, f"{case_id}.json")
        with open(out_path, "w", encoding="utf-8") as out_f:
            json.dumps(final_output)  # check serializable
            out_f.write(json.dumps(final_output, indent=2, ensure_ascii=False) + "\n")

        # Log trace
        trace_logger.log_case_trace(case_id, trace_entries)
        processed_count += 1

        if processed_count % 10 == 0 or processed_count == 50:
            print(f"[Pipeline] Processed {processed_count}/50 cases...")

    # Flush trace logger
    trace_logger.flush()

    elapsed = round(time.time() - start_time, 2)
    print(f"[Pipeline] Successfully processed {processed_count} cases in {elapsed}s.")
    print(f"[Pipeline] Outputs written to '{output_dir}/', trace written to 'trace.jsonl'.")
    print("=" * 60)


if __name__ == "__main__":
    main()
