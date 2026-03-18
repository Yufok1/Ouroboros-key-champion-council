# Agent Compiler Modality Acclimation Report

Date: 2026-03-14
Created: 2026-03-14T13:00:13.1548634-04:00
Status: Research and audit complete. No edits made in this pass.
Primary workspace: `F:\End-Game\champion_councl`
Factory source: `F:\End-Game\ouroboros-key\agent_compiler.py`
Generated runtime inspected: `F:\End-Game\champion_councl\capsule\champion_gen8.py`
Primary intent: determine exactly what must change in `agent_compiler.py` to get ASR, TTS, and VLM working without breaking the existing facility work already present in the AGENT console, Environment shell, provider plug flows, or debug system.

## Purpose

This document is a compression-safe handoff and reacclimation artifact.

It captures:

- the rules that govern safe work in `agent_compiler.py`
- the architecture direction from the March 13 document set
- the live runtime behavior that was directly verified through MCP and the debug system
- the current gaps between source, generated runtime, provider contracts, and frontend facilities
- the exact edit boundaries that are safe
- the exact edit areas that still need work
- the recommended order of operations

This report is intended to prevent drift, repeated recon, and accidental regression while the modality work continues.

## Scope of This Audit

This pass was source-first and debug-backed.

It did not patch the compiler.

It did:

- re-read the governing documents from disk
- inspect the factory source and the generated runtime
- inspect the frontend facility surfaces already built in `champion_councl`
- use live MCP calls against the refreshed runtime
- use the debug feed as the operational proof layer
- probe the local HF router loopback directly
- verify local Whisper behavior with the actual downloaded model and test WAV
- consult official provider/task docs where the contract could not be trusted from memory alone

## Governing Documents Re-Read From Disk

These were explicitly re-read from disk after context compression risk became relevant:

- `F:\End-Game\ouroboros-key\data\claudeoctor.txt`
- `F:\End-Game\ouroboros-key\data\AGENT_COMPILER_INTEGRATION_SURFACES.md`

### What `claudeoctor.txt` requires

- `agent_compiler.py` is a 3-level quine system.
- Level 0 is ordinary compiler Python.
- Level 1 is generated runtime code inside template strings.
- Level 2 is nested generation.
- Brace depth is the main failure mode.
- Preserve unknown escaping until it is fully understood.
- Read surrounding context before editing.
- Keep diffs minimal and local.
- Validate in order:
  - `python -m py_compile agent_compiler.py`
  - regenerate target artifacts
  - verify behavior on the regenerated runtime

### What `AGENT_COMPILER_INTEGRATION_SURFACES.md` requires

- Runtime behavior changes center on `_generate_capsule_source(...)`.
- MCP-facing changes require checking:
  - `run_mcp_server(...)`
  - `FastMCP` setup sites
  - `_build_mcp_instructions()`
- Self-description surfaces require checking:
  - `get_help()`
  - `get_quickstart()`
  - `get_onboarding()`
  - `get_capabilities()`
  - README/doc generation
- Discovery/index surfaces require checking:
  - `_MONOLITH_INDEX`
- Export and mirror surfaces must stay aligned when emitted behavior changes.
- Direct runtime or direct MCP invocation is the proof surface.

## March 13 Architectural Spine Used For Orientation

The active facility direction was grounded in the following FelixBag docs:

- `docs/AGENT_FACTORY_FORMAL_MODALITY_FACILITY_MATRIX_2026-03-13.md`
- `docs/AGENT_FACTORY_FACILITY_BLUEPRINT_SCHEMA_2026-03-13.md`
- `docs/AGENT_FACTORY_PROVIDER_BINDING_SCHEMA_2026-03-13.md`
- `docs/AGENT_FACTORY_TYPED_SURFACE_SCHEMA_2026-03-13.md`
- `docs/AGENT_FACILITY_CONSOLE_ALIGNMENT_PLAN_2026-03-13.md`
- `docs/AGENT_REACCLIMATION_MEMO_MAR13_FOUNDATION_AND_VOICE_LANE_2026-03-14.md`

### Core architectural conclusions from those docs

- Do not build a second agent UI.
- The Council `AGENT` console is already the primary per-slot operator surface.
- The Environment should stay the control plane.
- The object substrate is canonical.
- The existing HTML/panel path is already real and should be formalized, not replaced.
- Provider/model work should be treated as reusable role fulfillment inside facilities, not as raw URL juggling.
- The active ASR/TTS work belongs in the March 13 voice/audio lane.
- The voice lane is not just "make a loader work"; it belongs inside:
  - a voice facility blueprint
  - ASR/TTS provider bindings
  - typed voice surfaces
  - object/state semantics
  - packaging alignment

### Most important "do not trample" conclusion

The existing facility work is protected.

That means the first-pass fixes should not bulldoze:

- the AGENT facility rail
- the current voice and vision facility staging flows
- the Environment shell truth model
- the existing remote text-provider lane
- the debug telemetry substrate

The safest path is to patch the runtime adapter layer under those facilities first.

## Sources Inspected In Code

### Factory source

File:

- `F:\End-Game\ouroboros-key\agent_compiler.py`

Key areas inspected:

- `_detect_model_type_runtime(...)`
- `_load_model_smart(...)`
- `_load_as_asr(...)`
- `_load_as_tts(...)`
- `RemoteProviderProxy`
- `plug_model(...)`
- `invoke_slot(...)`
- `slot_info(...)`
- `hub_tasks(...)`
- `get_capabilities(...)`
- `get_onboarding(...)`
- `get_quickstart(...)`
- `get_help(...)`
- `_MONOLITH_INDEX`

### Generated runtime

File:

- `F:\End-Game\champion_councl\capsule\champion_gen8.py`

Key areas inspected:

- `RemoteProviderProxy`
- `_load_model_smart(...)`
- `_load_as_asr(...)`
- `_load_as_tts(...)`
- `ModelType`
- `_detect_model_type_runtime(...)`
- `invoke_slot(...)`
- `slot_info(...)`

### Frontend and server surfaces

Files:

- `F:\End-Game\champion_councl\static\main.js`
- `F:\End-Game\champion_councl\server.py`

Key areas inspected:

- slot/provider capability inference
- provider URL construction for HF router loopback
- AGENT facility rail
- vision staging flow
- voice staging flow
- inline audio packaging
- debug mirror and `feed` substrate
- HF router loopback proxy

## Operational Method Used

The live audit treated the debug system as the real proof surface.

That means the recurring workflow was:

1. make a real tool call
2. read `slot_info`, `list_slots`, or `get_status`
3. read `feed`
4. inspect source code
5. interpret the failure only after the runtime and debug evidence agreed

### MCP tools used during this audit

- `get_status`
- `list_slots`
- `slot_info`
- `invoke_slot`
- `feed`
- `get_cached`
- `symbiotic_interpret`
- `bag_search_docs`
- `bag_read_doc`
- `env_read`
- `hub_info`
- `get_help`
- `get_capabilities`
- `get_onboarding`

### Local shell probes used during this audit

- direct file/line inspection of source and generated runtime
- direct local loopback `curl.exe` requests against `/hf-router/...`
- direct local Python probes using the downloaded Whisper model and WAV test file

## Live Runtime State Verified

The refreshed runtime was not treated as "probably correct." It was checked directly.

### Runtime identity at time of audit

- generation: `8`
- brain type: `ouroboros`
- quine hash observed from runtime: `bf3d977966b5ff32a9bf67ca4e89f656`
- council slots total: `32`

### Slots plugged during live audit

- slot 0: local Whisper tiny
  - source: `D:\temp\hf_models\openai__whisper_tiny`
- slot 1: remote Qwen2.5-VL via HF router loopback with Together provider
  - source: `http://127.0.0.1:7866/hf-router/together?model=Qwen/Qwen2.5-VL-7B-Instruct`
- slot 2: remote Bark via HF router loopback
  - source: `http://127.0.0.1:7866/hf-router?model=suno/bark`
- slot 3: remote text-only control model via HF router loopback with Together provider
  - source: `http://127.0.0.1:7866/hf-router/together?model=Qwen/Qwen2.5-7B-Instruct`

## Live Debug Findings

The debug feed proved the following end-to-end.

### ASR

Observed behavior:

- local Whisper plugged successfully
- `slot_info(0)` reported:
  - `model_class = GenericWrapper`
  - `model_type = HF`
- `invoke_slot(slot=0, mode="transcribe", text="D:\\temp\\hf_models\\whisper_test.wav")`
  returned:
  - `Model does not support transcribe mode`

Debug conclusion:

- the new ASR surface is advertised
- the actual local loader path still did not produce an ASR-capable wrapper

### TTS

Observed behavior:

- remote Bark plugged successfully
- `slot_info(2)` reported:
  - `model_class = RemoteProviderProxy`
  - `model_type = LLM`
- `invoke_slot(slot=2, mode="synthesize", text="Hello world...")`
  returned:
  - `Model does not support synthesize mode`

Debug conclusion:

- the runtime has no remote TTS method path yet
- the proxy is still effectively text-chat oriented

### VLM

Observed behavior:

- remote Qwen2.5-VL plugged successfully
- `slot_info(1)` reported:
  - `model_class = RemoteProviderProxy`
  - `model_type = LLM`
- multimodal `messages` with `image_url` were passed through and captured by debug feed
- `invoke_slot(...)` returned:
  - `[Remote provider error: HTTP Error 400: Bad Request]`

Control experiments:

- a text-only control model on the same `hf-router/together` provider path answered successfully
- the same VLM model returned `400` even for a plain text-only chat completion call through the loopback route

Raw upstream 400 body from direct loopback `curl.exe`:

```json
{"error":{"message":"The requested model 'Qwen/Qwen2.5-VL-7B-Instruct' is not supported by any provider you have enabled.","type":"invalid_request_error","param":"model","code":"model_not_supported"}}
```

Debug conclusion:

- the generic remote bridge itself is not broken
- the specific VLM provider binding is invalid on the live route being used

## Direct Loopback Contract Probes

These probes matter because they separate compiler defects from provider-route limits.

### Remote text control probe

This succeeded through the same loopback/provider class:

- plugged `Qwen/Qwen2.5-7B-Instruct`
- invoked `generate`
- output: `Four.`

Conclusion:

- the text chat provider bridge is healthy

### VLM direct loopback probe

Direct request:

- `POST /hf-router/together/v1/chat/completions?model=Qwen/Qwen2.5-VL-7B-Instruct`

Result:

- `model_not_supported`

Conclusion:

- the chosen model/provider combination is not currently valid

### Remote speech route probes

Direct requests:

- `POST /hf-router/v1/audio/speech?model=suno/bark`
- `POST /hf-router/v1/audio/transcriptions?model=openai/whisper-large-v3`

Both results:

- `Not Found`

Conclusion:

- the current HF router loopback on this stack does not expose remote speech endpoints in the needed shape
- remote speech support is therefore not just a missing method on `RemoteProviderProxy`

## Source Findings In Detail

### 1. Local ASR route exists but is bypassed

In generated runtime:

- ASR/TTS detection exists
- route branches to `_load_as_asr(...)` and `_load_as_tts(...)` exist

However:

- config refinement still says:
  - if architecture contains `forseq2seqlm` or `forconditionalgeneration`
  - set `detected_type = 'SEQ2SEQ'`

That logic catches Whisper and overrides the earlier ASR detection.

Result:

- Whisper never reaches the ASR loader
- it falls into generic/other text loader behavior

### 2. `_load_as_asr()` exists but is not robust enough yet

The emitted ASR loader currently:

- hardcodes `torch.float16`
- does not align input features to model device/dtype
- uses `max_new_tokens=448`

Direct local verification showed:

- on this CPU host, the current flow fails on dtype mismatch
- after dtype alignment, it still fails because `448` is too high for the target length budget on Whisper tiny
- with:
  - CPU using `float32`
  - device/dtype-aligned input features
  - `max_new_tokens=128`
  the transcription succeeds and returns:

`This is a test of me recording my voice.`

### 3. `RemoteProviderProxy` is still fundamentally text-chat oriented

It currently implements:

- `generate()`
- `encode()`

It does not implement:

- `transcribe()`
- `synthesize()`

So even though it sets `_model_type_hint` based on model-name keywords, that hint does not create actual audio behavior.

### 4. Runtime type detection is not aligned to the new hints

`_detect_model_type_runtime(...)` still maps:

- `LLM`
- `EMBEDDING`
- `RERANKER`
- `CLASSIFIER`
- `SEQ2SEQ`
- `VISION`
- `VLM`
- `GENERIC`

It does not intentionally map:

- `ASR`
- `TTS`

Then, later capability probing says:

- if a model has `transcribe()`, it is `AUDIO_LLM`
- if a model has `synthesize()`, it is `TTS`

That is not aligned with the new hint system and can create reporting drift.

### 5. Slot reporting is still stale

`slot_info(...)` reports `c._model_type`.

That means:

- local Whisper still reports `HF`
- remote VLM and remote Bark still report `LLM`

even when the runtime is carrying more specific modality hints.

### 6. Help mirrors are ahead of the actual runtime

`get_help()` already advertises:

- `invoke_slot(mode=transcribe)`
- `invoke_slot(mode=synthesize)`

But:

- `get_capabilities()` does not surface modality-specific capabilities
- `get_onboarding()` still frames remote providers as generic OpenAI-compatible slots without clarifying audio/vision caveats

## Frontend Facility Findings

The frontend facility work is not the main defect.

It is mostly doing what the March 13 docs intended.

### AGENT console facility alignment is real

The existing AGENT console already has:

- shared slot/facility contract inference
- facility rail
- vision view
- voice view
- memory view
- direct invoke/tool panels

This matches the March 13 alignment memo:

- build inside the existing AGENT console
- do not build a second agent UI

### The frontend already compensates for bad backend metadata

`static/main.js` derives capability profiles heuristically from:

- source
- model type
- slot name
- provider descriptor

That is why the voice and vision facility views already exist and remain useful even though the backend still reports `HF` and `LLM` too often.

### The voice facility is intentionally still transitional

Important current behavior:

- TTS staging still loads `invoke_slot.mode = 'generate'`
- ASR staging still loads `invoke_slot.mode = 'generate'` with hidden inline audio
- inline audio is converted into chat-shaped `messages[].content[].input_audio`

The console explicitly knows that remote ASR still needs a dedicated adapter.

This is an important safety signal:

- do not rewrite the voice facility first
- make the backend honor the facility contract more honestly first

## Environment Truth Findings

`env_read(...)` showed the Environment shell is alive and mirrored.

Important result:

- the Environment contract is real
- the AGENT/facility effort is not imaginary
- the shell is already consuming shared slot/facility truth

That supports the March 13 position:

- do not split work into a parallel runtime or second UI

## Official Documentation Consulted

These were checked because the provider contracts are temporally unstable and easy to misremember.

### Hugging Face

- chat completion:
  - https://huggingface.co/docs/inference-providers/tasks/chat-completion
- ASR task:
  - https://huggingface.co/docs/api-inference/tasks/automatic-speech-recognition
- TTS task:
  - https://huggingface.co/docs/inference-providers/tasks/text-to-speech

### Together

- chat overview:
  - https://docs.together.ai/docs/chat-overview
- vision model docs:
  - https://docs.together.ai/docs/vision-llms
- audio overview:
  - https://docs.together.ai/docs/audio-overview

### Why these mattered

They support the following practical conclusions:

- HF's OpenAI-compatible lane is centered on chat-style completions
- HF speech tasks are not the same contract as chat completions
- Together does support multimodal/vision-style chat
- provider support still depends on model availability and enabled providers

## What Must Change In `agent_compiler.py`

This section is the practical execution spine.

### A. Fix local ASR routing

Change area:

- `_load_model_smart(...)`

Required behavior:

- preserve `automatic-speech-recognition -> ASR`
- do not let generic `forconditionalgeneration` override Whisper into `SEQ2SEQ`

Goal:

- local Whisper should load as ASRWrapper, not GenericWrapper

### B. Make the ASR wrapper production-safe

Change area:

- `_load_as_asr(...)`

Required behavior:

- pick dtype by device
- use CPU-safe `float32` when no CUDA is available
- move input features to matching device/dtype
- reduce generation token limit to a safe default
- ideally expose optional `language` and `task` control later

Goal:

- the existing local Whisper tiny model should successfully transcribe the existing local test WAV via `invoke_slot(mode="transcribe")`

### C. Align runtime type detection

Change area:

- `_detect_model_type_runtime(...)`

Required behavior:

- map `ASR`
- map `TTS`
- decide whether `AUDIO_LLM` remains a separate class or is folded into ASR semantics for facility use

Goal:

- runtime type reporting and downstream dispatch should match the new loader hints

### D. Fix slot metadata and reporting

Change areas:

- `plug_model(...)`
- `list_slots(...)`
- `slot_info(...)`

Required behavior:

- stored `_model_type` should reflect actual modality, not just `LLM` or generic `HF`
- reporting should expose enough truth for facilities and debugging

Goal:

- AGENT facility rail and operator truth become simpler and less heuristic-dependent

### E. Split remote-provider behavior by modality

Change area:

- `RemoteProviderProxy`

Required behavior:

- keep text chat working exactly as it does now
- keep embeddings working exactly as they do now
- support VLM when the provider/model pair is valid
- do not advertise remote speech support unless the route really exists

Goal:

- preserve working remote text behavior while making modality handling honest and explicit

### F. Preserve compatibility with the current voice facility contract

Change area:

- backend invocation path, not the frontend facility rail first

Required behavior:

- do not force the frontend to immediately abandon its current chat-shaped inline-audio staging
- keep `transcribe` and `synthesize` as explicit first-class modes
- but also respect the already-shipped AGENT console facility behavior

Goal:

- no facility regression while the backend catches up

### G. Finish the mirror surfaces after runtime truth is real

Change areas:

- `get_help()`
- `get_capabilities()`
- `get_onboarding()`
- `get_quickstart()`
- `_MONOLITH_INDEX`

Goal:

- help surfaces stop promising unsupported runtime behavior

## What Is Probably Outside `agent_compiler.py`

### 1. Remote speech via HF router

The current loopback route does not expose the needed speech endpoints.

That means remote speech support is likely not solvable solely inside the compiler unless:

- the proxy layer in `server.py` is extended
- or a different remote provider path is chosen

### 2. The current VLM provider binding

The chosen model/provider pair was rejected upstream.

That means one required next step is:

- choose a VLM model/provider pair that the live route actually supports

before blaming the compiler for the entire failure.

### 3. Frontend facility refinement

The AGENT console may still need later cleanup once the backend is real.

But it should be treated as follow-up alignment work, not first-pass repair.

## Protected Surfaces

These should be treated as protected in the first implementation pass:

- AGENT facility rail
- current voice facility staging
- current vision facility staging
- existing Environment shell contracts
- current debug mirror and `feed` substrate
- working remote text-provider path through HF router/Together

## Verification Protocol Once Edits Begin

This should be treated as mandatory, not optional.

1. `python -m py_compile agent_compiler.py`
2. regenerate the target champion artifact
3. replug local Whisper
4. run `invoke_slot(mode="transcribe")` on the local test WAV
5. read:
   - `slot_info`
   - `list_slots`
   - `feed`
6. verify remote text control model still works
7. verify a supported VLM provider/model pair through the same debug path
8. if remote speech is attempted:
   - probe loopback route directly first
   - then use `invoke_slot`
   - then verify with `feed`
9. verify AGENT console facility behavior did not regress

## Recommended Implementation Order

This is the lowest-regression-risk order identified by the audit.

1. local ASR route fix
2. ASR wrapper robustness fix
3. runtime type detection and slot reporting alignment
4. preserve remote text-provider behavior while splitting modality-aware remote logic
5. choose and validate a supported VLM provider/model pair
6. decide explicitly whether remote speech is in scope now or deferred to a provider/proxy extension
7. only then finish help/onboarding/index mirrors

## Bottom Line

The main problem is not "the facilities are wrong."

The main problem is:

- the compiler/runtime adapter layer only partially caught up to the new modality ambitions
- the live remote-provider contracts are not uniform across text, vision, and speech
- the help surface got ahead of the actual runtime

The frontend facilities are already useful and should be preserved.

The safest path is:

- fix the runtime truth under them
- preserve the current facility contract
- use the debug feed as the proof surface after every meaningful change

## Resume Prompt

Use the companion file:

- `F:\End-Game\champion_councl\docs\RESUME_PROMPT_AGENT_COMPILER_MODALITIES_2026-03-14.md`

It is meant to be pasted back to the agent after compression.

