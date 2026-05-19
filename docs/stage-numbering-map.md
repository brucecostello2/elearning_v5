# Stage Numbering: Spec vs Implementation

| Spec Stage | Spec Name | Implementation File | Impl Stage # |
|------------|-----------|---------------------|-------------|
| Stage 1 | Transcript Refinement | stage1_transcript.py | 1 |
| Stage 2 | Storyboard Generation | stage2_storyboard.py | 2 |
| Stage 3 | Media Generation | stage3_images.py | 3 |
| Stage 4 | Composition Manifest | (ManifestBuilder in Phase 7) | 4 |
| Stage 5 | Audio/TTS | stage4_voiceover.py | 4 (file) |
| Stage 6 | Talking Head | stage5_talking_head.py | 5 (file) |
| Stage 7 | Prototype Draft | stage7_prototype.py | 7 |
| Stage 8 | Final Render | stage8_final_render.py | 8 |

Note: Implementation files stage4/stage5 map to spec stages 5/6 respectively.
The `PipelineStage` enum and `STAGE_TRANSITION_MAP` handle the correct sequencing.
