# Local model selection

Qwen/Qwen3-8B was selected as the single A10 pipeline-validation checkpoint.
It has approximately 8.2 billion parameters, BF16 weights, an Apache-2.0
license, native long-context support beyond the project's 8K cap, and a chat
template capable of tool calling. The 15.26 GiB weights leave enough A10 memory
for an 8K KV cache with one active sequence.

Alternatives larger than the card's comfortable BF16 capacity would require
quantization or CPU offload, adding confounds to an integration proof. Smaller
models offer less reliable tool use. This choice is an engineering compromise,
not a claim that Qwen3-8B is sufficiently capable for the behavioral question.

Primary references reviewed on 2026-07-24:

- Qwen3-8B model card and license: https://huggingface.co/Qwen/Qwen3-8B
- Qwen3 release description: https://qwenlm.github.io/blog/qwen3/
- vLLM tool-calling guide: https://docs.vllm.ai/en/stable/features/tool_calling/
- vLLM reasoning-output guide: https://docs.vllm.ai/en/stable/features/reasoning_outputs/
- vLLM 0.25.1 release: https://pypi.org/project/vllm/
