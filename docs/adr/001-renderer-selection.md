# ADR-001: Spine 3.6 renderer selection

- Status: Accepted for the public release
- Date: 2026-09-04
- Candidates: Qt WebEngine with Spine WebGL 3.6; `spine-c` 3.6 native bridge

## Decision

Use Qt WebEngine plus the externally supplied Spine WebGL 3.6 runtime for the initial functional
MVP. The initial MVP was limited to at most two simultaneous pets and renderer access remains behind `PetRenderer`.
Do not treat WebEngine as the final production choice: the native `spine-c` candidate remains the
preferred optimization path when a C/CMake toolchain is available.

The runtime, character fixture, and generated screenshots/packages remain outside the GPL-covered
repository and release allowlist. The project owner confirmed this distribution boundary and marked
the pre-implementation runtime/asset licensing gates passed.

## Evidence collected

- The official 3.6 checkout documents that both `spine-ts` and `spine-c` accept Spine 3.6.xx data.
- Qt WebEngine loaded the 3.6.53 fixture using only localhost/offline resources.
- All 60 animations evaluated without exceptions. Mesh, clipping, deform, draw-order, IK, transform
  constraints, event timelines, and animation mixing are present in the fixture and parsed by the
  official runtime. Evaluated event names were `lip`, `loop_start`, and `relay`.
- Straight alpha is required for this project's assets, so Spine renderer PMA remains disabled.
  Transparent WebEngine composition separately requires context PMA enabled and separate framebuffer
  alpha blending (`ONE / ONE_MINUS_SRC_ALPHA`). The project owner visually approved this combination
  on transparent, checkerboard, white, and gray backgrounds. Disabling context PMA caused dark seams;
  enabling renderer PMA *without premultiplying texture uploads* caused washout. This was the
  original baseline and is superseded by the 2026-09-17 amendment below.
- Transparent screenshot corners had alpha 0, while the character center had alpha 255.
- Native Qt input reached Chromium's `QQuickWidget`, generated a canvas click, crossed QWebChannel,
  and returned alpha 255 at the same logical coordinate.
- 100%, 125%, and 150% scale runs reported device pixel ratios 1.0, 1.25, and 1.5 and produced the
  same successful center hit.
- A Python 3.10 cx_Freeze build was 447.44 MiB and passed offline load/render/exit smoke testing.
- The reproducible Windows measurements are maintained in the separate `ShinyColorsPetDev`
  repository with the remaining QA evidence.

## Resource decision

WebEngine scales almost linearly in memory: about 417 MiB for one pet, 1,250 MiB for three, and
2,080 MiB for five. FPS stayed near 59, but this memory cost disqualifies unrestricted multi-pet use.
The initial WebEngine MVP was therefore capped at two pets pending native results.

## Deferred evidence

- GPU memory is unavailable through psutil under the current Windows/WDDM setup.
- macOS, Linux X11, and Wayland were not available on this host.
- No C compiler, CMake, Ninja, or MSBuild is installed, so the `spine-c` ABI could not be compiled and
  P0.6–P0.7 remain deferred. No custom Python Spine evaluator will be created.

## Consequences

Implementation may proceed using the WebEngine adapter. Controllers and manifests must remain renderer-neutral
so the native adapter can replace it without changing application semantics. The public application
ships only the used `spine-webgl.js` plus its LICENSE and spine-ts README as separately licensed
material; the rest of the runtime repository and all non-public character models remain excluded.

## Public-release amendment — 2026-09-08

The product owner removed the initial two-pet cap for the public release. The supervisor no longer rejects a
new desktop character based on the number already running. Process isolation, heartbeat checks,
graceful shutdown, and orphan-worker cleanup remain unchanged. Concurrent capacity is therefore
determined by the user's machine rather than an application-enforced limit.

## Rendering amendment — 2026-09-17

Keep the Spine WebGL runtime at 3.6, but use premultiplied alpha throughout the rendering path for
all models. The WebGL context enables `UNPACK_PREMULTIPLY_ALPHA_WEBGL` before the atlas textures load,
and `SkeletonRenderer.premultipliedAlpha` is enabled. The existing separate framebuffer alpha blending
remains in place. Testing in `ShinyColorsPetDev` confirmed this combination fixes the white face
artifacts in `1940100010` `stand` and `stand_costume`, and the fine lines at joints, while preserving
multiply slot effects. The previous renderer-only PMA test did not premultiply texture uploads and
therefore is not evidence against the complete configuration.

New manifests identify PMA as the default. Older manifests with `premultiplied_alpha: false` remain
readable but no longer override the renderer; users do not need to clear AppData manifests. This
change does not claim visual verification of every model, particularly assets already stored with
premultiplied pixels.

## Standard-model animation policy — 2026-09-17

Standard rigs now play full-body gestures exclusively on the base track, replacing idle with zero
mix time. This prevents the idle track from clearing raised-hand attachments. Dev testing first
isolated the issue to idols 01 and 13; the project owner then checked that applying the same policy
to the other characters had no visible adverse effect. Chibi models keep their manifest policy.
The default `main.py` profile is `all`; `--standard-animation-policy targeted` remains available for
regression comparison with the original 01/13-only scope. The runtime choice overrides old AppData
standard-model manifests, so clearing or reimporting those manifests is unnecessary. Newly generated
standard-model manifests also record the exclusive policy.

