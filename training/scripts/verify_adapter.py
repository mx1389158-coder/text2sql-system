from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a QLoRA adapter and verify JSON/SQL generation")
    parser.add_argument("adapter", type=Path)
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-1.5B-Instruct")
    parser.add_argument(
        "--sample",
        type=Path,
        default=ROOT / "training/datasets/llamafactory/text2sql_dev_v1.json",
    )
    args = parser.parse_args()

    import torch
    from peft import PeftModel
    from sqlglot import parse_one
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not (args.adapter / "adapter_config.json").exists():
        raise FileNotFoundError(f"adapter_config.json not found in {args.adapter}")
    sample = json.loads(args.sample.read_text(encoding="utf-8"))[0]
    messages = [
        {"role": "system", "content": "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."},
        {"role": "user", "content": f"{sample['instruction']}\n{sample['input']}"},
    ]
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        local_files_only=True,
        device_map="auto",
        quantization_config=quantization,
        dtype=torch.bfloat16,
    )
    model = PeftModel.from_pretrained(model, args.adapter, is_trainable=False)
    inputs = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
    ).to(model.device)
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=256,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    generated = tokenizer.decode(output[0, inputs["input_ids"].shape[1] :], skip_special_tokens=True)
    start = generated.find("{")
    end = generated.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"adapter did not generate a JSON object: {generated[:300]}")
    payload = json.loads(generated[start : end + 1])
    if payload.get("intent") != "QUERY" or not payload.get("sql"):
        raise ValueError(f"invalid Text2SQL payload: {payload}")
    parse_one(payload["sql"], read="postgres")
    report = {
        "adapter": str(args.adapter.as_posix()),
        "sample": args.sample.name,
        "json_valid": True,
        "sql_parse_valid": True,
        "intent": payload["intent"],
        "used_tables": payload.get("used_tables", []),
        "sql": payload["sql"],
        "cuda_peak_mb": round(torch.cuda.max_memory_allocated() / 1048576, 2),
    }
    output_path = args.adapter / "verification.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
