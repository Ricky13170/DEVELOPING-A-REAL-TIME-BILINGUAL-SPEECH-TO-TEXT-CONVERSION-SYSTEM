# OneVoice AI Challenge — Project Context & Implementation Summary

> **Purpose of this file:** Give another AI enough context to immediately understand the project, the existing codebase, the competition requirements, the proposed product direction, and what should be built next.
>
> **Primary repo:** https://github.com/Senju14/Speech_to_text-realtime-for-lecture-hall
> **Competition:** OneVoice AI Challenge — Phase 2: Technical Submission
> **Technical Proposal deadline:** **21/08/2026**
> **Current strategy:** **Build a working MVP first → benchmark it → then write the Technical Proposal based on the real implementation.**

## Verified update — 19/08/2026

- The official template weights are: AI approach/design **35%**, hardware/device **25%**, business **15%**, problem/impact **15%**, and team/execution **10%**.
- The judged product is an **offline, on-device** translator. Modal T4 is used only for remote development smoke tests; it is not presented as Edge deployment evidence.
- Evaluation targets to design around: real-time factor **RTF < 1.0** and less than **2 seconds** from detected end-of-speech to the start of translated speech. These are competition targets, not measured project results yet.
- The current reference pipeline uses Faster-Whisper `medium` (T4 smoke profile; CPU INT8 fallback), adaptive energy VAD, and lazy OPUS-MT VI↔EN with beam size 1. `large-v3` remains an accuracy-oriented option. BARTpho, WhisperX/Pyannote, NLLB, repeated ASR retries, and second-pass translation are removed from the real-time path.
- WebRTC is an optional transport for local/LAN testing. Binary WebSocket remains the reliable fallback when direct ICE connectivity is unavailable.
- The current Helsinki-NLP OPUS-MT VI↔EN checkpoints are Apache-2.0. Their quality still needs clean/noisy operational-domain benchmarking before any product claim.

Official working links:

- Challenge brief: https://saigonaihub.com/OneVoiceAIChallenge
- Published evaluation details (RTF, latency, offline rule): https://luma.com/g1rwi7ag
- Technical Proposal template: https://docs.google.com/document/d/1M7nnGvdhpwYkhkMyCVHwKkOajexjNL3MvfPEFV0E_QM/edit
- Submission form: https://forms.gle/fhLAX767Z9hQMitZA
- Qualcomm AI Hub Whisper Small Quantized reference: https://aihub.qualcomm.com/models/whisper_small_quantized
- Faster-Whisper runtime reference: https://github.com/SYSTRAN/faster-whisper
- OPUS-MT VI→EN: https://huggingface.co/Helsinki-NLP/opus-mt-vi-en
- OPUS-MT EN→VI: https://huggingface.co/Helsinki-NLP/opus-mt-en-vi

Current implementation snapshot:

- Implemented: CPU local/Docker fallback, optional Modal T4 smoke runtime, Faster-Whisper Medium, lazy OPUS-MT VI↔EN beam 1, adaptive energy VAD, bounded serial audio worker, tail flush, measured ASR/NMT timing fields, local WebRTC with WebSocket fallback, industrial templates, transport badge, and offline-by-default Groq behavior.
- Removed from realtime runtime: BARTpho/PEFT, WhisperX, Pyannote, DeepFilterNet, NLLB, repeated ASR retries, second-pass NMT, CUDA auto-selection, and four dead backend modules.
- Still required before claiming a complete OneVoice prototype: offline TTS, deterministic safety alert UI, glossary enforcement, real clean/noisy benchmarks, power/RAM measurements, and an actual Qualcomm/QNN on-device port. Desktop or cloud-GPU results alone are not Edge deployment evidence.

---

# 1. Competition Context

The team has officially advanced to **Phase 2 — Technical Submission** of the OneVoice AI Challenge.

The submission should help judges understand:

1. The specific communication problem being solved.
2. The system architecture and technical approach.
3. How **Edge AI** is integrated.
4. Technical feasibility and expected effectiveness.
5. Real-world deployment potential.
6. Hardware/device concept.
7. Business differentiation.
8. Team execution plan.

Official proposal scoring emphasis:

| Criterion | Weight |
|---|---:|
| AI Approach & Technical Design | **35%** |
| Hardware & Device Concept | **25%** |
| Business Solution | **15%** |
| Problem Definition & Impact | **15%** |
| Team & Execution Plan | **10%** |

An early prototype/demo can provide additional value, so the project should not be only a theoretical proposal.

---

# 2. Existing Project / Starting Point

Existing repository:

**Speech-to-Text Realtime for Lecture Hall**

Repo:
https://github.com/Senju14/Speech_to_text-realtime-for-lecture-hall

The existing system was originally designed for lecture-hall transcription/translation and contains useful reusable components such as:

- Real-time audio capture.
- Streaming speech recognition.
- Whisper / WhisperX based ASR.
- Vietnamese-English translation.
- Voice Activity Detection.
- Text normalization.
- Hallucination filtering.
- Streaming stabilization / Local Agreement ideas.
- FastAPI / WebSocket based realtime pipeline.
- GPU/cloud inference support.
- Context / summary related components.

However, the existing thesis architecture is **too heavy and too cloud/GPU-oriented** for the OneVoice Edge AI goal.

Examples of components that should NOT simply be copied into the final Edge MVP:

- Whisper Large-v3 running on A100 as the default runtime.
- NLLB 3.3B.
- Cloud GPU dependency in the judged runtime.
- Groq/API-dependent runtime features.
- Large diarization pipeline if it is not needed.
- Automatic lecture summarization.
- Heavy multi-speaker meeting features.

The OneVoice project should reuse the engineering knowledge and useful modules, but **simplify the product significantly**.

---

# 3. Proposed Product Direction

## Working product name

# **TheDuo Edge Interpreter**

A portable, offline, real-time speech translation system designed for frontline communication.

Primary target environments:

- Factories.
- Warehouses / logistics.
- Technical maintenance.
- Construction.
- Field operations.
- Other noisy / low-connectivity workplaces.

Initial target users:

- Vietnamese workers communicating with foreign supervisors.
- Foreign technical supervisors communicating with Vietnamese operators.
- Technical trainers.
- Maintenance teams.
- Factory / warehouse staff.

---

# 4. Core Product Idea

TheDuo should NOT be positioned as:

> “Another translation app.”

Instead, it should be positioned as:

> **An offline operational communication device focused on noisy workplaces, technical vocabulary, safety-critical speech, privacy, and low-latency Edge AI.**

The MVP should focus on:

# **Vietnamese ↔ English**

The architecture should later be extensible to other language packs such as:

- Vietnamese ↔ Mandarin.
- Vietnamese ↔ Korean.

But the first working prototype should prioritize one language pair and actually work.

---

# 5. Main MVP User Flow

Example:

```text
User presses: VI → EN

Vietnamese speech:
"Hãy kiểm tra nhiệt độ của động cơ."

        ↓

ASR:
"Hãy kiểm tra nhiệt độ của động cơ."

        ↓

Translation:
"Please check the engine temperature."

        ↓

TTS:
Speaker says:
"Please check the engine temperature."
```

Reverse direction:

```text
User presses: EN → VI

English speech
    ↓
ASR
    ↓
Translation
    ↓
Vietnamese text
    ↓
Vietnamese TTS
```

The runtime should eventually require **zero cloud API calls**.

---

# 6. Recommended AI Architecture

Use a **cascaded speech translation pipeline**, not a giant end-to-end Speech-to-Speech foundation model.

```text
┌──────────────────────┐
│     Push To Talk     │
└──────────┬───────────┘
           ↓
     Microphone 16 kHz
           ↓
   Audio Preprocessing
 Noise Reduction / AGC
           ↓
    VAD / Endpointing
           ↓
          ASR
   Quantized Whisper
           ↓
 Transcript Normalizer
           ↓
┌──────────────────────┐
│ Domain Glossary      │
│ Safety Detection     │
└──────────┬───────────┘
           ↓
          NMT
       VI ↔ EN
           ↓
   Confidence / Safety
          Gate
           ↓
          TTS
           ↓
 Speaker + Translated Text
```

Why use this architecture:

- Easier to debug.
- Easier to benchmark.
- Easier to replace individual models.
- Easier to quantize.
- Easier to explain to judges.
- Easier to run on Edge hardware.
- Easier to measure latency per module.

---

# 7. Push-to-Talk First

The existing lecture system may need continuous streaming and complicated speaker handling.

TheDuo should initially use:

# **Push-to-Talk (PTT)**

Advantages:

- Clear speech boundary.
- Easier VAD.
- Lower compute usage.
- Lower false detection.
- Lower latency.
- Easier noisy-environment UX.
- Natural for factory / radio-like communication.
- Can eventually map to physical hardware buttons.

Suggested UI:

```text
┌──────────────────────────────────┐
│             TheDuo               │
│       OFFLINE ● Battery 84%      │
│                                  │
│      Vietnamese ⇄ English        │
│                                  │
│          🎤 VI → EN              │
│                                  │
│          🎤 EN → VI              │
│                                  │
│ Heard:                           │
│ "Kiểm tra van số ba."            │
│                                  │
│ Translation:                     │
│ "Check valve number three."      │
│                                  │
│                    🔊 Replay     │
└──────────────────────────────────┘
```

Do NOT prioritize:

- Login.
- Accounts.
- Cloud dashboards.
- Complex settings.
- Databases.
- Chat history.
- Social features.

---

# 8. Model Strategy

Model choices are still subject to benchmarking.

The guiding principle is:

# **Deployability > benchmark prestige**

## 8.1 ASR

Current reference candidate:

```text
Whisper Medium
```

Accuracy-oriented cloud comparison:

```text
Whisper Large-v3
```

Potential optimization path:

```text
Original model
   ↓
FP16
   ↓
INT8 / quantized
   ↓
ONNX / Edge runtime
   ↓
Qualcomm-specific optimization
```

Do NOT default to Whisper Large-v3 for the final Edge device.

---

## 8.2 Translation

Initial candidate:

```text
OPUS-MT VI↔EN / smaller quantized NMT
```

Do NOT use the existing heavy NLLB 3.3B in the final Edge runtime unless benchmarking proves it practical.

Important evaluation criteria:

- Vietnamese-English translation quality.
- Model size.
- RAM usage.
- Latency.
- Quantization compatibility.
- ONNX / mobile / Edge runtime support.

---

## 8.3 TTS

Requirements:

- Fully offline.
- Small enough for Edge hardware.
- Understandable speech.
- Vietnamese + English support.
- Low latency.

Voice cloning is NOT required.

The product only needs:

```text
Translated text
      ↓
Clear offline speech
```

---

# 9. Reuse from Existing Repository

Do NOT rewrite everything.

Reuse engineering ideas / components where practical.

## Keep / Adapt

### Audio capture

Keep the 16 kHz realtime audio approach.

### Streaming stabilization / Local Agreement

Useful if partial ASR is shown while the user speaks.

Example:

```text
"Hãy kiểm..."
"Hãy kiểm tra..."
"Hãy kiểm tra nhiệt độ..."
```

A stabilization mechanism can reduce text flickering.

### Hallucination filtering

Adapt this into a more general confidence gate.

```text
ASR result
   ↓
High confidence
   → translate

Low confidence
   → ask user to repeat

Very low confidence / silence
   → discard
```

### Text normalization

Adapt from lecture vocabulary into industrial terminology.

Examples:

```text
PLC
van thủy lực
băng chuyền
điện áp
cầu dao
motor
sensor
valve
pressure
```

---

# 10. Remove / Deprioritize from Existing Repository

For the OneVoice MVP, remove or postpone:

- Lecture summarization.
- Groq-based runtime functionality.
- Cloud LLM context generation.
- Cloud GPU/A100 dependency in the final product.
- Heavy speaker diarization.
- Large NLLB models.
- Large Whisper models if not Edge-feasible.
- Multi-user cloud architecture.
- Database infrastructure.
- Redis.
- Complex microservices.
- Anything not directly required for offline speech translation.

Target architecture should initially be:

# **One local process, one clear pipeline.**

---

# 11. Key Differentiator: Safety Mode

A major product differentiator should be **Safety-Aware Translation**.

Examples of critical concepts:

```text
STOP
EMERGENCY
DANGER
FIRE
HIGH VOLTAGE
SHUT DOWN
DO NOT ENTER
```

Vietnamese examples:

```text
dừng máy
khẩn cấp
nguy hiểm
cháy
điện cao áp
tắt máy
không được vào
```

Example UX:

```text
Vietnamese:
"Dừng máy ngay, có người ở phía trong!"

        ↓

Translation:
"Stop the machine immediately,
there is someone inside!"

        ↓

┌───────────────────────────────────┐
│ ⚠ CRITICAL SAFETY MESSAGE        │
│                                   │
│ DỪNG MÁY NGAY                     │
│                                   │
│ STOP THE MACHINE IMMEDIATELY      │
│                                   │
│       🔊 Replay    ✓ Confirm      │
└───────────────────────────────────┘
```

---

# 12. Safety Mode Should Be Simple and Deterministic

Do NOT start with an LLM agent.

Use:

```text
ASR
 ↓
Normalization
 ↓
Critical phrase matcher
 ↓
Translation
 ↓
Safety UI / Alert
```

Example:

```python
CRITICAL_TERMS = {
    "dừng máy": "STOP_MACHINE",
    "khẩn cấp": "EMERGENCY",
    "cháy": "FIRE",
    "nguy hiểm": "DANGER",
    "điện cao áp": "HIGH_VOLTAGE"
}
```

Possible improvements later:

- Fuzzy matching.
- Synonym dictionary.
- Domain-specific patterns.
- Confidence threshold.
- Confirm / replay interaction.

Advantages:

- Fast.
- Offline.
- Deterministic.
- Explainable.
- Easy to test.
- Good product story.
- Low implementation risk.

---

# 13. Domain Glossary

TheDuo should support downloadable / configurable terminology packs.

Example domains:

```text
Factory
Logistics
Construction
Automotive
Maintenance
Electrical
```

Example glossary:

```json
{
  "PLC": "PLC",
  "van thủy lực": "hydraulic valve",
  "băng chuyền": "conveyor belt",
  "điện áp": "voltage",
  "cầu dao": "circuit breaker"
}
```

The glossary can help:

- Normalize ASR.
- Preserve important terminology.
- Improve translation consistency.
- Differentiate the product from general consumer translation.

---

# 14. Confidence Gate

The system should avoid confidently speaking obviously poor translations.

Concept:

```text
Audio quality / ASR confidence
          ↓

GOOD
→ translate normally

UNCERTAIN
→ show warning
→ allow replay / repeat

BAD
→ "Please repeat"
```

Possible signals:

- VAD duration.
- ASR confidence proxy.
- Compression / no-speech probability.
- Repetition / hallucination patterns.
- Too-short output.
- Abnormal text.

The exact confidence formula should be developed empirically.

---

# 15. Current Codebase Structure

Use the existing repository with a deliberately small feature-based backend:

```text
backend/
├── config.py
├── translation.py
├── groq_service.py
├── web_app.py
├── speech/       # audio, VAD, segmentation, ASR, stabilization
└── realtime/     # session orchestration and WebRTC transport

frontend/         # browser UI
tests/            # fast smoke tests without model downloads
main.py           # single local/Docker/Modal entrypoint
```

Do not add repository/service/controller/DTO layers until the project actually
needs them. Add a new feature folder only when it contains at least two cohesive
modules. See `../docs/architecture.md` for exact file ownership and dependency
direction.

---

# 16. Development Plan

## Version 0 — Functional Desktop Prototype

First goal:

# Make the complete speech-to-speech loop work locally on a PC.

Required pipeline:

```text
Mic
 ↓
ASR
 ↓
Translation
 ↓
TTS
```

Requirements:

- VI → EN.
- EN → VI.
- No cloud needed during inference if possible.
- Basic push-to-talk UI.
- Display source text.
- Display translated text.
- Replay TTS.

DO NOT optimize for Qualcomm hardware before this pipeline works.

---

# 17. Version 1 — Product Differentiation

After V0 works:

Add:

1. Domain glossary.
2. Safety mode.
3. Confidence gate.
4. Noise robustness.
5. Latency logging.
6. Better UI.

---

# 18. Version 2 — Edge Optimization

Only after the desktop prototype is stable:

```text
Desktop prototype
        ↓
Profile models
        ↓
Quantize
        ↓
Export to ONNX / target runtime
        ↓
Benchmark
        ↓
Qualcomm / Snapdragon integration
```

Potential topics:

- INT8 quantization.
- FP16.
- ONNX.
- Qualcomm QNN.
- NPU execution.
- Lazy model loading.
- Memory reuse.
- Streaming inference.
- Model caching.
- Phrase cache.

---

# 19. Hardware Strategy

Do NOT design a custom PCB immediately.

## Prototype hardware

Preferred practical direction:

```text
Snapdragon Android device / development hardware
```

Why:

- Existing microphone.
- Existing speaker.
- Existing battery.
- Existing display.
- Snapdragon compute.
- NPU already available.
- Faster path to a real demo.

## Future dedicated product concept

```text
┌─────────────────────────────┐
│ Qualcomm Edge SoC           │
│                             │
│ 2× MEMS microphones         │
│ speaker                     │
│ physical PTT buttons        │
│ small display               │
│ local storage               │
│ rechargeable battery        │
└─────────────────────────────┘
```

Possible form factors:

- Handheld translator.
- Lanyard.
- Radio-like device.

Do NOT claim a dedicated hardware product has already been built if only a phone / dev board prototype exists.

---

# 20. Offline-First Principles

Target final runtime architecture:

1. All models stored locally.
2. No external API calls during normal translation.
3. Audio remains on device.
4. Transcripts remain on device.
5. Language packs can be installed before deployment.
6. Domain glossary stored locally.
7. Repeated phrases may be cached locally.
8. TTS is local.
9. Failure should degrade gracefully.

Example:

```text
Internet unavailable
        ↓
System still works
```

---

# 21. Benchmarking Is Mandatory

Benchmark during development, not after.

For every request, record:

```text
audio_duration
vad_latency
asr_latency
translation_latency
tts_latency
total_latency
peak_ram
model_size
```

Example report format:

```text
Audio duration:        4.20 s

VAD:                    18 ms
ASR:                   742 ms
Translation:           311 ms
TTS:                   486 ms

Total processing:    1.557 s
Peak RAM:              2.71 GB
```

The numbers above are FORMAT EXAMPLES only.

Do NOT use them as actual project results unless measured.

---

# 22. Recommended Evaluation

## ASR

Metrics:

- WER.
- CER.

Test conditions:

- Clean speech.
- Workplace noise.
- Multiple Vietnamese accents if possible.
- English speech from Vietnamese speakers.
- Technical terminology.

---

## Translation

Metrics:

- BLEU.
- chrF++.
- Human evaluation for short operational commands.

Test sets:

- General dialogue.
- Factory terminology.
- Maintenance instructions.
- Safety messages.

---

## Latency

Measure separately:

```text
VAD
ASR
NMT
TTS
Total
```

Prefer reporting:

```text
p50
p95
```

---

## Resource usage

Measure:

- Model size.
- RAM.
- CPU/GPU/NPU utilization if available.
- Startup time.
- Storage.
- Battery drain later.

---

## Safety

Create a dedicated test set:

```text
10–50 safety-critical sentences
```

Measure:

- Critical phrase recall.
- False alerts.
- Correct translated meaning.
- Alert latency.

---

# 23. Engineering Targets

These are **targets**, NOT measured claims.

Possible initial goals:

| Metric | Target |
|---|---:|
| Runtime internet requirement | 0 |
| End-of-speech → translated speech starts | < 2 s p95 |
| Real-time factor | < 1.0 |
| ASR first useful result | ~1 s class target |
| Audio | 16 kHz mono |
| Peak RAM | ideally < 4 GB |
| Languages in MVP | VI ↔ EN |
| Interaction | Push-to-talk |
| Runtime privacy | on-device |
| Product environment | noisy frontline workplace |

All targets must later be replaced or supported by benchmark results.

---

# 24. Technical Proposal Strategy

Do NOT write a speculative proposal first.

Preferred workflow:

```text
Product idea
   ↓
Working MVP
   ↓
Real benchmarks
   ↓
Edge feasibility experiment
   ↓
Architecture diagram
   ↓
Technical Proposal
```

The proposal should describe what the system actually does or what is clearly planned and technically justified.

Avoid fake claims such as:

- “Latency is 300 ms” without measurement.
- “Runs entirely on NPU” before testing.
- “8-hour battery life” without a power model.
- “95% accuracy” without evaluation.
- “Industrial-grade” without relevant validation.

Use wording like:

```text
Engineering target
Preliminary benchmark
Prototype result
Planned optimization
To be validated
```

---

# 25. Proposal Sections That Must Eventually Be Filled

Official template structure:

## 1. Executive Summary

Include:

- Communication problem.
- Proposed solution.
- Target users.
- Business case.
- Technical differentiator.

---

## 2. Problem Definition & Target Users

Include:

- Problem statement.
- Impact analysis.
- Target user segments.
- Use cases.
- Design constraints.

Important constraints:

- Offline runtime.
- Latency.
- Noise.
- Privacy.
- Hardware limits.
- Language pair.

---

## 3. Business Solution & Innovation

Compare against existing approaches.

Dimensions may include:

- Connectivity.
- Latency.
- Domain vocabulary.
- Privacy.
- Workplace UX.
- Safety.
- Noise.
- Hardware interaction.
- Repeat commands.

Important:

Do NOT say only:

> “We are faster and more accurate.”

Quantify later with real measurements.

---

## 4. AI Approach & Technical Design

This is the largest scoring section.

Need:

- End-to-end pipeline.
- Model choices.
- Model size.
- Latency target / result.
- Optimization technique.
- Quantization.
- Memory management.
- Noise robustness.
- Accent handling.
- Code-switching.
- Silence handling.
- OOV terminology.

---

## 5. Hardware & Device Concept

Need:

- Compare compute platforms.
- Justify selected hardware.
- SoC / NPU.
- RAM / storage.
- AI SDK/toolchain.
- Form factor.
- Microphone.
- Speaker.
- Battery.
- Power estimate.
- Estimated bill of materials and form-factor dimensions.
- A clear distinction between measured prototype data and target-device estimates.

---

## 6. System Architecture & Integration

Need:

- Software stack.
- Architecture diagram.
- How AI runtime talks to audio/app layer.
- Offline-first behavior.

---

## 7. Team Profile & Timeline

Need:

- Member names.
- Roles.
- Expertise.
- Contribution area.
- Milestones.
- Dates.

---

# 26. Development Timeline Before Submission

Deadline:

# **21/08/2026**

Suggested aggressive schedule:

## 10–11/08
Architecture freeze.

Finalize:

- Problem.
- Users.
- Product.
- MVP.
- Pipeline.
- Candidate models.

## 11–13/08
Build V0:

```text
Mic → ASR → NMT → TTS
```

## 14/08
Push-to-talk UI.

## 15/08
Add:

- Glossary.
- Safety mode.
- Confidence gate.

## 16/08
Benchmark:

- Clean audio.
- Noisy audio.
- Domain terminology.
- Safety sentences.
- Latency.
- RAM/model size.

## 17/08
Edge feasibility:

- Quantization.
- ONNX.
- Mobile/Qualcomm path.
- Resource profiling.

## 18–20/08
Write Technical Proposal using actual implementation and measurements.

## 21/08
Final review:

- Proposal.
- Architecture diagrams.
- Hardware table.
- Demo video.
- Links.
- Export PDF.
- Submission.

---

# 27. Definition of Done Before Proposal Writing

The MVP should ideally satisfy:

- [ ] Record speech from microphone.
- [ ] Vietnamese → English works.
- [ ] English → Vietnamese works.
- [ ] ASR runs locally.
- [ ] Translation runs locally.
- [ ] TTS runs locally.
- [ ] Push-to-talk UI exists.
- [ ] Source transcript shown.
- [ ] Translation shown.
- [ ] Replay works.
- [ ] Safety mode works.
- [ ] Domain glossary exists.
- [ ] Confidence handling exists.
- [ ] Latency logger exists.
- [ ] Model sizes are known.
- [ ] Peak RAM is measured.
- [ ] At least one benchmark table exists.
- [ ] Architecture diagram matches real code.
- [ ] 30–60 second demo can be recorded.

---

# 28. Non-Goals Before 21/08

Do NOT spend significant time on:

- Custom PCB.
- Beautiful enclosure.
- Multi-user backend.
- Cloud deployment.
- Authentication.
- Database.
- Full conversation history.
- LLM agents.
- Voice cloning.
- Advanced diarization.
- Lecture summarization.
- Training giant foundation models.
- All language pairs simultaneously.
- Perfect UI animation.

Priority:

# **A small product that actually works.**

---

# 29. Key Product Differentiators to Preserve

The final product story should revolve around:

### 1. Offline Edge AI

No Internet required during runtime.

### 2. Frontline UX

Push-to-talk instead of smartphone-style typing/navigation.

### 3. Domain Glossary

Technical terminology adapted to the workplace.

### 4. Safety-Aware Translation

Critical operational messages get special treatment.

### 5. Confidence-Aware Output

Avoid confidently speaking obviously unreliable results.

### 6. Privacy

Audio and transcripts stay local.

### 7. Modular Language Packs

Architecture can expand beyond VI ↔ EN.

---

# 30. Questions Still Open

The implementation AI should help investigate/benchmark these rather than assuming answers:

1. Which Whisper variant provides the best quality/latency tradeoff?
2. Which NMT model is small enough for the target Edge device?
3. Which offline TTS model is best for Vietnamese + English?
4. PyTorch vs ONNX vs Qualcomm QNN for each module?
5. Should VAD be Silero, WebRTC, or simple PTT endpointing?
6. How should confidence be computed reliably for Whisper?
7. How should glossary correction avoid corrupting valid speech?
8. How much accuracy is lost after INT8 quantization?
9. Can all models fit into the target RAM simultaneously?
10. Should models remain loaded or be lazy-loaded?
11. How much latency is introduced by TTS?
12. Which Snapdragon / Qualcomm development platform should be used?
13. Can a phone prototype demonstrate the Edge AI concept sufficiently?
14. Which noise datasets / real recordings should be used?
15. How should Vietnamese regional accents be evaluated?

---

# 31. Instructions for the Next AI

When assisting with this project:

## DO

- Read the existing GitHub repo before proposing large rewrites.
- Reuse useful components.
- Keep the pipeline modular.
- Prefer a working MVP over sophisticated research ideas.
- Make each technical recommendation deployable.
- Distinguish measured results from targets.
- Add benchmark instrumentation early.
- Explain why a model is selected.
- Consider model size, RAM, latency, runtime support, and quantization.
- Keep OneVoice scoring criteria in mind.
- Keep the deadline in mind.
- Make code changes incrementally.
- Propose concrete files/functions/commits.

## DO NOT

- Invent benchmark numbers.
- Assume NPU support without verifying it.
- Add LLMs unnecessarily.
- Turn the system into a cloud product.
- Over-engineer the backend.
- Rewrite the whole repo unless necessary.
- Optimize hardware before the speech pipeline works.
- Prioritize proposal wording over working code.
- Claim features that have not been implemented.

---

# 32. Recommended Next Immediate Task

The next AI should start by:

1. Inspecting the GitHub repository structure.
2. Identifying:
   - files to keep,
   - files to modify,
   - files to remove/deprioritize.
3. Designing an `onevoice-edge` branch or equivalent clean folder structure.
4. Selecting the first candidate:
   - ASR,
   - NMT,
   - TTS.
5. Building the smallest possible:

```text
record.wav
   ↓
ASR
   ↓
translation
   ↓
TTS.wav
```

6. Only after that works, connect it to microphone + push-to-talk UI.
7. Add profiling from the first working version.

---

# 33. One-Sentence Project North Star

> **Build an offline, push-to-talk Edge AI interpreter for Vietnamese frontline workers that translates operational speech quickly and privately, preserves technical terminology, and treats safety-critical messages differently from ordinary conversation.**

---

# 34. Success Criterion

The project is successful when a demo can show:

```text
User presses VI → EN

"Hãy dừng máy và kiểm tra van số ba."

        ↓
Processed entirely locally

        ↓
"Stop the machine and check valve number three."

        ↓
Safety warning appears

        ↓
English speech is played
```

while the system records real latency/resource measurements that can be used directly in the Technical Proposal.

---

# END OF CONTEXT
