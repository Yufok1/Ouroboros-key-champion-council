const fs = require('fs');
const path = require('path');

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = String(argv[i] || '');
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (next === undefined || String(next).startsWith('--')) out[key] = true;
    else {
      out[key] = next;
      i += 1;
    }
  }
  return out;
}

function titleCase(value) {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function nounPhrase(value) {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function extractQuotedStrings(block) {
  const out = [];
  const regex = /'([^']+)'|"([^"]+)"/g;
  let match = regex.exec(block);
  while (match) {
    out.push(String(match[1] || match[2] || '').trim());
    match = regex.exec(block);
  }
  return out.filter(Boolean);
}

function extractFrozenset(text, symbolName) {
  const regex = new RegExp(`${symbolName}\\s*=\\s*frozenset\\(\\{([\\s\\S]*?)\\}\\)`, 'm');
  const match = text.match(regex);
  return match ? extractQuotedStrings(match[1]) : [];
}

function extractJsArray(text, propertyName, nextPropertyName) {
  const escapedProperty = propertyName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const escapedNext = nextPropertyName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`${escapedProperty}\\s*:\\s*\\[([\\s\\S]*?)\\]\\s*,\\s*${escapedNext}`, 'm');
  const match = text.match(regex);
  return match ? extractQuotedStrings(match[1]) : [];
}

function findCommandAnchors(text, filePath) {
  const anchors = new Map();
  const lines = text.split(/\r?\n/);
  const patterns = [
    { kind: 'handler', regex: /if\s*\(\s*command\s*===\s*'([^']+)'\s*\)/ },
    { kind: 'handler', regex: /if\s*\(\s*command\s*===\s*"([^"]+)"\s*\)/ },
    { kind: 'bridge', regex: /_envQueueControl\(\s*'([^']+)'/ },
    { kind: 'bridge', regex: /_envQueueControl\(\s*"([^"]+)"/ },
  ];
  lines.forEach((line, index) => {
    patterns.forEach((pattern) => {
      const match = line.match(pattern.regex);
      if (!match) return;
      const command = String(match[1] || '').trim();
      if (!command) return;
      if (!anchors.has(command)) anchors.set(command, []);
      const rows = anchors.get(command);
      if (rows.some((row) => row.line === index + 1 && row.kind === pattern.kind)) return;
      rows.push({
        file: filePath,
        line: index + 1,
        kind: pattern.kind,
      });
    });
  });
  return anchors;
}

function findActionAnchors(text, filePath) {
  const anchors = new Map();
  const lines = text.split(/\r?\n/);
  const patterns = [
    { kind: 'ui_action', regex: /if\s*\(\s*action\s*===\s*'([^']+)'\s*\)/ },
    { kind: 'ui_action', regex: /if\s*\(\s*action\s*===\s*"([^"]+)"\s*\)/ },
    { kind: 'ui_entrypoint', regex: /data-env-action="([^"]+)"/ },
    { kind: 'ui_entrypoint', regex: /data-env-action='([^']+)'/ },
  ];
  lines.forEach((line, index) => {
    patterns.forEach((pattern) => {
      const match = line.match(pattern.regex);
      if (!match) return;
      const action = String(match[1] || '').trim();
      if (!action) return;
      if (!anchors.has(action)) anchors.set(action, []);
      const rows = anchors.get(action);
      if (rows.some((row) => row.line === index + 1 && row.kind === pattern.kind)) return;
      rows.push({
        file: filePath,
        line: index + 1,
        kind: pattern.kind,
      });
    });
  });
  return anchors;
}

function mergeObjects(base, override) {
  if (override === undefined) return base;
  if (Array.isArray(base) || Array.isArray(override)) return override;
  if (!base || typeof base !== 'object' || !override || typeof override !== 'object') return override;
  const out = { ...base };
  Object.keys(override).forEach((key) => {
    out[key] = key in out ? mergeObjects(out[key], override[key]) : override[key];
  });
  return out;
}

function normalizeActionToCommand(action) {
  return String(action || '').trim().replace(/-/g, '_');
}

function dedupeList(values) {
  return Array.from(new Set((values || []).filter(Boolean).map((item) => String(item).trim()).filter(Boolean)));
}

function familyForCommand(command) {
  if (command.startsWith('camera_')) return 'camera_pose';
  if (command.startsWith('capture_')) return 'capture_observer';
  if (command.startsWith('surface_') || ['focus_surface', 'inspect_surface', 'open_surface', 'close_surface', 'close_inspector', 'open_doc_memory'].includes(command)) {
    return 'surface_bridge';
  }
  if (command.startsWith('character_') || ['spawn_inhabitant', 'despawn_inhabitant', 'focus_inhabitant', 'toggle_inhabitant_fov_debug'].includes(command)) {
    return 'character_runtime';
  }
  if (
    command === 'workbench_play_authored_clip'
    || command === 'workbench_compile_clip'
    || command === 'workbench_set_timeline_cursor'
    || command === 'workbench_preview_settle'
    || command === 'workbench_commit_settle'
    || command === 'workbench_assert_balance'
    || command === 'workbench_capture_pose'
    || command === 'workbench_delete_pose'
    || command === 'workbench_apply_pose'
  ) return 'builder_motion';
  if (command.startsWith('workbench_')) return 'builder_workbench';
  if (
    command.startsWith('focus_')
    || command.startsWith('replay_')
    || ['follow_failed', 'sample_now', 'toggle_stream', 'toggle_replay', 'branch_snapshot'].includes(command)
  ) return 'focus_navigation';
  if (['activate_profile', 'run_recipe', 'scan_docs', 'set_theater_mode', 'set_camera_mode', 'set_replay_mode'].includes(command)) {
    return 'theater_profile_recipe';
  }
  return 'environment_misc';
}

const FAMILY_DEFAULTS = {
  focus_navigation: {
    title: 'Focus And Navigation',
    description: 'Focus changes, replay/sample navigation, and shell steering commands.',
    when_to_use: [
      'Use these when the theater focus, replay cursor, or live sample stream is pointed at the wrong thing.',
      'These are the safest navigation controls when you want state changes without manual UI guessing.',
    ],
    mode_notes: [
      'Most focus targets only work when matching items exist in the current ledger, replay state, or scene context.',
      'Expect shared_state focus keys and side panels to move together after a successful navigation change.',
    ],
    verification: ['env_read(query=\'shared_state\')', 'capture_supercam', 'feed(n=20)'],
  },
  camera_pose: {
    title: 'Camera And Pose',
    description: 'Camera framing, orbit, pan, tilt, dolly, and pose controls for the theater view.',
    when_to_use: [
      'Use these before capture when you need repeatable framing instead of mouse navigation.',
      'They are also the cleanest recovery path after focus or scene-shell changes leave the camera in a bad state.',
    ],
    mode_notes: [
      'Camera commands change viewer state, not embodiment or workbench data.',
      'Framing commands depend on there being a meaningful focus, replay target, or overview context.',
    ],
    verification: ['capture_supercam', 'capture_probe', 'env_read(query=\'shared_state\')'],
  },
  capture_observer: {
    title: 'Capture And Observer',
    description: 'Observer capture commands used to corroborate scene, subject, and motion truth.',
    when_to_use: [
      'Use these when viewport impression is not enough and you need saved evidence.',
      'Capture commands are the main corroboration path for scale, floor truth, motion, and scene layout.',
    ],
    mode_notes: [
      'A dispatched capture is not proven complete until the file exists or shared_state reports the latest capture.',
      'Different capture modes emphasize different truths: local detail, overview context, or motion across time.',
    ],
    verification: ['static/captures/', 'env_read(query=\'shared_state\')', 'probe_compare'],
  },
  surface_bridge: {
    title: 'Surface Bridge',
    description: 'Owned-surface inspection and input commands for browser-side panels and surfaces.',
    when_to_use: [
      'Use these when you need to drive a browser-owned panel without relying on a pointer.',
      'They are especially useful for opening, focusing, and inspecting surfaces across agent sessions.',
    ],
    mode_notes: [
      'Surface bridge commands usually need a valid owned surface id first.',
      'Success is easiest to confirm from visible browser behavior plus feed/shared_state.',
    ],
    verification: ['env_read(query=\'shared_state\')', 'feed(n=20)', 'visible browser surface behavior'],
  },
  theater_profile_recipe: {
    title: 'Theater / Profile / Recipe',
    description: 'Theater mode, profile, recipe, and environment-shell steering commands.',
    when_to_use: [
      'Use these when you are changing the shell itself rather than moving a single camera, subject, or panel.',
      'These are the top-level steering controls for how the theater is organized right now.',
    ],
    mode_notes: [
      'A mode or profile change can invalidate assumptions about focus, camera, and visible inspectors.',
      'These commands often affect multiple panels or shell affordances at once.',
    ],
    verification: ['env_read(query=\'shared_state\')', 'capture_supercam', 'feed(n=20)'],
  },
  character_runtime: {
    title: 'Character Runtime',
    description: 'Mounted runtime commands for character presence, model, movement, and playback.',
    when_to_use: [
      'Use these to operate the mounted asset/runtime embodiment rather than the builder skeleton.',
      'These are the commands for imported asset inspection, runtime animation, and inhabitant presence.',
    ],
    mode_notes: [
      'Some commands assume a mounted subject already exists.',
      'Builder-subject mode and mounted-asset inspection can share the theater, but they are not the same runtime state.',
    ],
    verification: ['capture_probe', 'capture_supercam', 'env_read(query=\'shared_state\')'],
  },
  builder_workbench: {
    title: 'Builder Workbench',
    description: 'Builder subject, pose, selection, display, and workbench control commands.',
    when_to_use: [
      'Use these when editing or inspecting the builder subject instead of the mounted imported asset.',
      'This is the main family for scaffold truth, selection, pose editing, and blueprint state.',
    ],
    mode_notes: [
      'Most builder workbench commands assume builder_subject mode is active.',
      'If builder mode is not active, expect partial responses or no visible effect until a builder subject is created.',
    ],
    verification: ['capture_probe', 'env_read(query=\'shared_state\')', 'workbench_get_blueprint'],
  },
  builder_motion: {
    title: 'Builder Motion',
    description: 'Timeline, preset, authored clip, and scrub commands for builder-side motion work.',
    when_to_use: [
      'Use these for staged motion inspection, authored clip work, or pose sequencing on the builder subject.',
      'They are the core path for motion validation before live runtime playback is trustworthy.',
    ],
    mode_notes: [
      'Builder motion commands assume a builder subject and an active timeline or pose store.',
      'Preset apply does not imply autoplay; staged motion and live playback are different surfaces.',
    ],
    verification: ['capture_time_strip', 'capture_probe', 'env_read(query=\'shared_state\')'],
  },
  environment_misc: {
    title: 'Environment Misc',
    description: 'Remaining environment commands that do not fit the main families.',
    when_to_use: [
      'Use these for shell helpers, profile kits, world profile changes, and scene-side toggles that cut across families.',
      'This family usually holds useful edge operations rather than the main command lanes.',
    ],
    mode_notes: [
      'Misc commands often affect shell state more than a single subject.',
      'Read the individual entry carefully because the name alone is not always enough to infer scope.',
    ],
    verification: ['env_read(query=\'shared_state\')', 'feed(n=20)'],
  },
  observation_query: {
    title: 'Observation Queries',
    description: 'Read-only environment query surfaces that return live browser state or derived observation views.',
    when_to_use: [
      'Use these when you need fast readback from the live theater without dispatching a new control command.',
      'These are the observation-bus surfaces for shared state, text theater, captures, and similar diagnostics.',
    ],
    mode_notes: [
      'Observation queries do not mutate runtime state by themselves.',
      'Freshness still matters: mirror lag or stale browser state can make a read truthful about old state rather than current intent.',
    ],
    verification: ['env_read(query=\'shared_state\')', 'env_read(query=\'text_theater_embodiment\')'],
  },
};

const STANDALONE_UI_ACTIONS = new Set([
  'workbench-play-clip',
  'workbench-toggle-pause',
  'workbench-set-speed',
  'workbench-toggle-loop',
  'workbench-set-locomotion',
  'workbench-shot-preset',
  'workbench-toggle-skeleton',
  'workbench-toggle-attachments',
  'workbench-toggle-turntable',
  'workbench-toggle-scaffold',
  'workbench-toggle-load-field',
  'toggle-overlay-panel',
  'restore-overlay-panel',
  'reset-overlay-panel',
  'set-label-mode',
  'toggle-kind-panel',
  'toggle-kind',
  'kind-show-all',
  'kind-hide-all',
  'reset-camera',
  'toggle-inhabitant',
]);

const UI_ACTION_BRIDGES = {
  'workbench-play-clip': ['character_play_clip'],
  'workbench-set-speed': ['character_set_speed'],
  'workbench-toggle-loop': ['character_set_loop'],
  'workbench-toggle-scaffold': ['workbench_set_scaffold'],
  'workbench-toggle-load-field': ['workbench_set_load_field'],
  'reset-camera': ['camera_reset_pose'],
  'toggle-inhabitant': ['character_mount', 'character_unmount'],
};

function summaryForCommand(command, family) {
  if (command === 'workbench_set_timeline_cursor') return 'Scrub the active builder timeline to a given normalized, time, or index position and apply that staged pose.';
  if (command === 'workbench_preview_settle') return 'Generate a visible settle micro-timeline from current balance truth and stage it for scrubbed preview.';
  if (command === 'workbench_commit_settle') return 'Commit the staged settle preview into the builder timeline or compile it as a clip.';
  if (command === 'character_set_model') return 'Swap the mounted runtime to a direct asset ref and leave builder-subject mode for mesh-asset inspection.';
  if (command === 'workbench_new_builder') return 'Instantiate a fresh builder subject, clear the mounted asset clone, and enter builder-subject mode.';
  if (command === 'workbench_get_blueprint') return 'Return the serialized builder blueprint describing the active builder subject.';
  if (command === 'workbench_get_part_surface') return 'Return the surface and slot metadata for a selected builder part.';
  if (command === 'workbench_frame_part') return 'Frame the camera around a selected builder part or supplied part id.';
  if (command === 'workbench_set_load_field') return 'Enable or disable the builder load-field mechanics lane used by scaffold-side diagnostics.';
  if (command === 'workbench_set_scaffold') return 'Enable or disable scaffold presentation for the current builder subject.';
  if (command === 'workbench_capture_pose') return 'Capture the current builder pose into the workbench pose store.';
  if (command === 'workbench_delete_pose') return 'Delete a stored builder pose from the workbench pose store.';
  if (command === 'workbench_apply_pose') return 'Apply a stored builder pose to the current builder subject.';
  if (command === 'workbench_compile_clip') return 'Compile the current builder pose and timeline data into an authored clip.';
  if (command === 'workbench_play_authored_clip') return 'Play the current authored builder clip through the workbench runtime.';
  if (command === 'workbench_save_blueprint') return 'Serialize and save the current builder blueprint.';
  if (command === 'workbench_load_blueprint') return 'Load a serialized builder blueprint into the active workbench session.';
  if (command === 'workbench_reset_angles') return 'Zero the current builder pose offsets back toward neutral angles.';
  if (command === 'workbench_clear_pose') return 'Clear the current staged builder pose offsets.';
  if (command === 'workbench_set_pose') return 'Apply or stage an explicit pose payload on the builder subject.';
  if (command === 'workbench_set_pose_batch') return 'Apply multiple pose changes in a single builder operation.';
  if (command === 'workbench_select_bone') return 'Replace the current builder selection with one named bone.';
  if (command === 'workbench_select_bones') return 'Replace the current builder selection with multiple named bones.';
  if (command === 'workbench_set_bone') return 'Apply an explicit bone transform payload to the builder subject.';
  if (command === 'workbench_set_display_scope') return 'Change how much of the builder subject the workbench displays.';
  if (command === 'workbench_set_editing_mode') return 'Change the current builder editing mode.';
  if (command === 'workbench_set_gizmo_mode') return 'Change the active workbench gizmo mode.';
  if (command === 'workbench_set_gizmo_space') return 'Change whether the gizmo works in local or world space.';
  if (command === 'workbench_isolate_chain') return 'Limit the builder display and edit scope to a selected chain or restore the full body.';
  if (command === 'capture_probe') return 'Capture the multi-angle local probe view for the focused subject or runtime target.';
  if (command === 'capture_supercam') return 'Capture the broader overview observer montage for scene-scale corroboration.';
  if (command === 'capture_time_strip') return 'Capture sampled frames across the current builder timeline so staged motion can be inspected without autoplay.';
  if (command === 'capture_focus') return 'Capture the current focus target with the observer pipeline.';
  if (command === 'capture_frame') return 'Capture a single observer frame from the current scene or subject context.';
  if (command === 'capture_frame_overview') return 'Capture a single observer frame using overview framing.';
  if (command === 'capture_strip') return 'Capture a strip of observer frames for quick comparative inspection.';
  if (command === 'character_mount') return 'Mount the runtime character surface so the theater has an active character subject.';
  if (command === 'character_unmount') return 'Unmount the current runtime character surface.';
  if (command === 'character_focus') return 'Move focus onto the mounted runtime character subject.';
  if (command === 'character_move_to') return 'Command the mounted runtime character toward a supplied world-space destination.';
  if (command === 'character_look_at') return 'Command the mounted runtime character to orient toward a supplied point.';
  if (command === 'character_play_clip') return 'Play a named animation clip on the mounted runtime subject.';
  if (command === 'character_queue_clips') return 'Queue one or more animation clips on the mounted runtime subject.';
  if (command === 'character_stop_clip') return 'Stop the currently forced or queued animation clip.';
  if (command === 'character_stop') return 'Stop the mounted runtime subject and clear immediate movement intent.';
  if (command === 'character_set_loop') return 'Set clip loop behavior for mounted runtime playback.';
  if (command === 'character_set_speed') return 'Set clip playback speed for the mounted runtime subject.';
  if (command === 'character_get_animation_state') return 'Read the mounted runtime animation state for the active subject.';
  if (command === 'character_play_reaction') return 'Trigger a named reaction or gesture on the mounted runtime subject.';
  if (command === 'spawn_inhabitant') return 'Spawn a fresh inhabitant/runtime subject into the current theater context.';
  if (command === 'despawn_inhabitant') return 'Remove the active inhabitant/runtime subject from the theater context.';
  if (command === 'focus_inhabitant') return 'Move theater focus onto the active inhabitant/runtime subject.';
  if (command === 'toggle_inhabitant_fov_debug') return 'Toggle the inhabitant field-of-view debug overlay.';
  if (command === 'branch_snapshot') return 'Create a replay/sample snapshot from the current branch context.';
  if (command === 'follow_failed') return 'Jump focus to the latest failed execution or failed branch target.';
  if (command === 'sample_now') return 'Force an immediate sample capture from the current focus context.';
  if (command === 'toggle_stream') return 'Toggle the live sample and activity stream used by the theater shell.';
  if (command === 'toggle_replay') return 'Toggle replay mode inside the theater shell.';
  if (command === 'replay_next') return 'Advance the replay cursor to the next replay entry.';
  if (command === 'replay_prev') return 'Move the replay cursor back to the previous replay entry.';
  if (command.startsWith('focus_')) return `Move theater focus to the current ${nounPhrase(command.replace(/^focus_/, ''))} target.`;
  if (command === 'open_surface') return 'Open an owned browser surface inside the theater shell.';
  if (command === 'close_surface') return 'Close an owned browser surface.';
  if (command === 'focus_surface') return 'Move shell focus onto a named owned surface.';
  if (command === 'inspect_surface') return 'Open the inspector for a named owned surface.';
  if (command === 'close_inspector') return 'Close the current inspector surface.';
  if (command === 'open_doc_memory') return 'Open the doc-memory surface from the theater shell.';
  if (command === 'surface_click') return 'Send a synthetic click to an owned browser surface.';
  if (command === 'surface_input') return 'Send text or value input to an owned browser surface.';
  if (command === 'surface_scroll') return 'Send a synthetic scroll event to an owned browser surface.';
  if (command === 'surface_submit') return 'Submit a form or action target inside an owned browser surface.';
  if (command === 'surface_tab') return 'Switch tabs inside an owned browser surface.';
  if (command === 'surface_action') return 'Dispatch a generic action payload to an owned browser surface.';
  if (command === 'activate_profile') return 'Activate a named theater/profile preset.';
  if (command === 'run_recipe') return 'Run a named recipe through the environment shell.';
  if (command === 'scan_docs') return 'Scan docs into the theater shell context.';
  if (command === 'set_camera_mode') return 'Switch the camera mode used by the theater shell.';
  if (command === 'set_replay_mode') return 'Switch the replay presentation mode used by the theater shell.';
  if (command === 'set_theater_mode') return 'Switch the theater shell between major presentation modes.';
  if (command === 'apply_profile_kit') return 'Apply a prepared profile-kit payload to the current shell state.';
  if (command === 'clear_profile_kit') return 'Clear the currently applied profile-kit payload.';
  if (command === 'set_camera_preset') return 'Apply a named camera preset to the theater shell.';
  if (command === 'set_world_profile') return 'Apply a named world-profile preset to the current scene shell.';
  if (command.startsWith('camera_frame_')) return `Frame the camera around the current ${nounPhrase(command.replace(/^camera_frame_/, ''))} context.`;
  if (command.startsWith('camera_dolly_')) return `Move the camera ${nounPhrase(command.replace(/^camera_dolly_/, ''))} along its current view axis.`;
  if (command.startsWith('camera_orbit_')) return `Orbit the camera ${nounPhrase(command.replace(/^camera_orbit_/, ''))} around the current focus anchor.`;
  if (command.startsWith('camera_pan_')) return `Pan the camera ${nounPhrase(command.replace(/^camera_pan_/, ''))} without changing focus.`;
  if (command.startsWith('camera_tilt_')) return `Tilt the camera ${nounPhrase(command.replace(/^camera_tilt_/, ''))} around its current pivot.`;
  if (command === 'camera_pose') return 'Apply or serialize a camera pose payload for the current theater view.';
  if (command === 'camera_reset_pose') return 'Reset the camera to the theater-mode default pose.';
  if (command.startsWith('camera_')) return `Adjust the theater camera using ${command}.`;
  return `Dispatch the environment command ${command}.`;
}

function targetContractForCommand(command, family) {
  if (command === 'workbench_set_timeline_cursor') {
    return {
      shape: 'json',
      description: 'Timeline cursor payload using normalized, time, or index.',
      examples: ['{"normalized":0.5}', '{"time":0.8}', '{"index":2}'],
    };
  }
  if (command === 'character_set_model') {
    return {
      shape: 'string',
      description: 'Direct asset ref or URL for the mounted character model.',
      examples: ['/static/assets/packs/os3a-tomb-chaser/GhostArmature.glb'],
    };
  }
  if (command === 'workbench_new_builder') {
    return {
      shape: 'string_or_json',
      description: 'Builder family id or JSON payload describing family, subject mode, and anchor choices.',
      examples: ['humanoid_biped', '{"family":"humanoid_biped"}'],
    };
  }
  if (command === 'character_move_to' || command === 'character_look_at') {
    return {
      shape: 'json_or_string',
      description: 'World-space destination or look-target payload understood by the runtime handler.',
      examples: ['{"x":0,"y":0,"z":0}'],
    };
  }
  if (command === 'character_play_clip') {
    return {
      shape: 'string_or_json',
      description: 'Clip name or JSON payload controlling which clip to play and whether it overrides current playback.',
      examples: ['walk', '{"clip":"walk","override":true}'],
    };
  }
  if (command === 'character_queue_clips') {
    return {
      shape: 'json',
      description: 'Queue payload describing one or more clips and their sequencing metadata.',
      examples: ['{"clips":["walk","idle"]}'],
    };
  }
  if (command === 'character_set_loop') {
    return {
      shape: 'string',
      description: 'Loop mode name such as repeat or once.',
      examples: ['repeat', 'once'],
    };
  }
  if (command === 'character_set_speed') {
    return {
      shape: 'number_or_string',
      description: 'Positive playback speed multiplier.',
      examples: ['0.5', '1', '2'],
    };
  }
  if (command === 'workbench_select_bone') {
    return {
      shape: 'string_or_json',
      description: 'Single bone id or selection payload.',
      examples: ['hips', '{"bone":"hips"}'],
    };
  }
  if (command === 'workbench_select_bones') {
    return {
      shape: 'json',
      description: 'Bone selection payload containing multiple bone ids.',
      examples: ['{"bones":["hips","spine","head"]}'],
    };
  }
  if (command === 'workbench_set_bone' || command === 'workbench_set_pose' || command === 'workbench_set_pose_batch') {
    return {
      shape: 'json',
      description: 'Explicit builder transform or pose payload.',
      examples: ['{"bone":"hips","rotation":{"x":0,"y":0.1,"z":0}}'],
    };
  }
  if (command === 'workbench_capture_pose' || command === 'workbench_delete_pose' || command === 'workbench_apply_pose') {
    return {
      shape: 'string_or_json',
      description: 'Pose name or payload naming the stored pose entry.',
      examples: ['neutral_standing', '{"name":"neutral_standing"}'],
    };
  }
  if (command === 'workbench_set_editing_mode' || command === 'workbench_set_display_scope' || command === 'workbench_set_gizmo_mode' || command === 'workbench_set_gizmo_space') {
    return {
      shape: 'string',
      description: 'Workbench enum value understood by the builder UI/runtime handler.',
      examples: ['rotate', 'translate', 'local', 'world'],
    };
  }
  if (command === 'workbench_set_load_field' || command === 'workbench_set_scaffold') {
    return {
      shape: 'string_or_json',
      description: 'On/off/toggle style control or JSON payload carrying the target boolean.',
      examples: ['toggle', '{"enabled":true}'],
    };
  }
  if (command.startsWith('capture_')) {
    return {
      shape: 'string_optional',
      description: 'Optional target hint for the observer capture flow.',
      examples: ['character_runtime::mounted_primary'],
    };
  }
  if (family === 'surface_bridge') {
    return {
      shape: 'string_or_json',
      description: 'Surface id or structured payload describing which owned surface to act on.',
      examples: ['memory', '{"surface":"memory"}'],
    };
  }
  if (family === 'character_runtime' || family === 'builder_workbench' || family === 'builder_motion') {
    return {
      shape: 'string_or_json',
      description: 'Runtime or workbench payload interpreted by the active browser handler.',
      examples: [],
    };
  }
  return {
    shape: 'string_optional',
    description: 'Command-specific target id interpreted by the browser/runtime handler.',
    examples: [],
  };
}

function availabilityForCommand(command, family) {
  const base = {
    theater_modes: [],
    visual_modes: [],
    requires_focus_kind: [],
    requires_builder_subject: false,
  };
  if (family === 'character_runtime' || family === 'builder_workbench' || family === 'builder_motion') {
    base.theater_modes = ['character'];
    base.requires_focus_kind = ['character_runtime'];
  }
  if (family === 'builder_workbench' || family === 'builder_motion') {
    base.visual_modes = ['builder_subject'];
    base.requires_builder_subject = true;
  } else if (family === 'character_runtime') {
    base.visual_modes = ['mesh_asset', 'builder_subject'];
  }
  if (family === 'camera_pose' || family === 'capture_observer' || family === 'focus_navigation' || family === 'theater_profile_recipe') {
    base.theater_modes = ['scene', 'character'];
  }
  if (command === 'character_set_model') {
    base.visual_modes = ['mesh_asset', 'builder_subject'];
    base.requires_builder_subject = false;
  }
  if (command === 'workbench_new_builder') {
    base.visual_modes = ['mesh_asset', 'builder_subject'];
    base.requires_builder_subject = false;
  }
  return base;
}

function familyForUiAction(action) {
  if (action.startsWith('workbench-')) {
    if ([
      'workbench-play-clip',
      'workbench-toggle-pause',
      'workbench-set-speed',
      'workbench-toggle-loop',
      'workbench-set-locomotion',
    ].includes(action)) return 'builder_motion';
    return 'builder_workbench';
  }
  if (action === 'reset-camera') return 'camera_pose';
  if (action === 'toggle-inhabitant') return 'character_runtime';
  if (['toggle-overlay-panel', 'restore-overlay-panel', 'reset-overlay-panel'].includes(action)) return 'surface_bridge';
  return 'environment_misc';
}

function summaryForUiAction(action) {
  if (action === 'workbench-play-clip') return 'Play a named loaded clip from the local workbench clip strip.';
  if (action === 'workbench-toggle-pause') return 'Pause or resume the current local preview action without changing staged builder timeline data.';
  if (action === 'workbench-set-speed') return 'Set local playback speed from the helper chips and forward that value through the runtime speed command.';
  if (action === 'workbench-toggle-loop') return 'Toggle loop mode from the helper chips and forward that loop choice through the runtime loop command.';
  if (action === 'workbench-set-locomotion') return 'Set the browser-side locomotion preview lane for the current workbench clip and refresh the animation UI.';
  if (action === 'workbench-shot-preset') return 'Apply a browser-local workbench camera shot preset such as front, side, or face.';
  if (action === 'workbench-toggle-skeleton') return 'Toggle the browser-local skeleton helper for the current workbench subject.';
  if (action === 'workbench-toggle-attachments') return 'Toggle browser-local attachment gizmos for the current workbench subject.';
  if (action === 'workbench-toggle-turntable') return 'Flip the browser-local workbench turntable on or off for the current builder view.';
  if (action === 'workbench-toggle-scaffold') return 'Flip scaffold visibility from the local helper strip and then dispatch the persistent scaffold command.';
  if (action === 'workbench-toggle-load-field') return 'Flip the helper-strip load toggle immediately in the browser and then dispatch the persistent load-field command.';
  if (action === 'toggle-overlay-panel') return 'Minimize or restore an overlay panel without leaving the current theater view.';
  if (action === 'restore-overlay-panel') return 'Restore a minimized overlay panel to its visible state.';
  if (action === 'reset-overlay-panel') return 'Restore an overlay panel and clear its staged local position.';
  if (action === 'set-label-mode') return 'Change the browser-local label rendering mode for scene annotations.';
  if (action === 'toggle-kind-panel') return 'Open or close the local kind-filter panel.';
  if (action === 'toggle-kind') return 'Toggle visibility for one object-kind filter in the current scene view.';
  if (action === 'kind-show-all') return 'Show all currently filterable scene kinds.';
  if (action === 'kind-hide-all') return 'Hide all currently filterable scene kinds.';
  if (action === 'reset-camera') return 'Use the local shell control to reset the camera through the standard camera-reset command.';
  if (action === 'toggle-inhabitant') return 'Use the local shell toggle to mount or unmount the inhabitant runtime.';
  return `Trigger the local browser action ${action}.`;
}

function targetContractForUiAction(action) {
  if (action === 'workbench-shot-preset') {
    return {
      shape: 'ui_chip',
      description: 'Triggered by the local shot-preset chips; not directly callable through env_control.',
      examples: ['front', 'three_q', 'side'],
    };
  }
  if (action === 'workbench-set-speed') {
    return {
      shape: 'ui_chip',
      description: 'Triggered by speed chips carrying a numeric speed multiplier.',
      examples: ['0.25', '0.5', '1', '2'],
    };
  }
  if (action === 'workbench-set-locomotion') {
    return {
      shape: 'ui_chip',
      description: 'Triggered by local locomotion chips such as auto, idle, walk, or run.',
      examples: ['auto', 'idle', 'walk', 'run'],
    };
  }
  if (['toggle-overlay-panel', 'restore-overlay-panel', 'reset-overlay-panel'].includes(action)) {
    return {
      shape: 'ui_payload',
      description: 'Triggered by an overlay panel control carrying an overlay id.',
      examples: ['overlay:inspector'],
    };
  }
  if (action === 'toggle-kind') {
    return {
      shape: 'ui_payload',
      description: 'Triggered by a kind-filter chip carrying the scene-kind name.',
      examples: ['lights', 'characters'],
    };
  }
  return {
    shape: 'ui_local',
    description: 'Browser-local control; use the named UI affordance rather than env_control.',
    examples: [],
  };
}

function whenToUseForEntry(command, family, entryKind) {
  const base = (FAMILY_DEFAULTS[family] && FAMILY_DEFAULTS[family].when_to_use) || [];
  const extra = [];
  if (command === 'workbench_set_timeline_cursor') extra.push('Use this when a preset or authored clip is loaded and you need a specific moment without autoplay.');
  if (command === 'workbench_preview_settle') extra.push('Use this after a destabilizing pose edit or authored timeline change when you want the system to generate a corrective reaction instead of guessing by hand.');
  if (command === 'workbench_commit_settle') extra.push('Use this only after reviewing a staged settle preview that you want to keep as authored motion.');
  if (command === 'character_set_model') extra.push('Use this when validating a mounted imported asset or leaving builder-subject mode on purpose.');
  if (command === 'workbench_get_blueprint') extra.push('Use this when you need the exact serialized builder truth instead of relying on the viewport alone.');
  if (command === 'workbench_set_load_field') extra.push('Use this when testing scaffold-side load mechanics or verifying helper-strip synchronization.');
  if (command === 'capture_probe') extra.push('Use this for close-range corroboration of scale, scaffold state, support planting, and local pose truth.');
  if (entryKind === 'ui_action' && command === 'workbench-toggle-turntable') extra.push('Use this when you need the builder subject to rotate continuously for local visual inspection.');
  return dedupeList([...base, ...extra]);
}

function whatItChangesForEntry(command, family, entryKind) {
  const out = [];
  if (family === 'camera_pose') out.push('Camera transform, framing, or stored camera pose state.');
  if (family === 'capture_observer') out.push('Writes new capture output and updates latest capture context.');
  if (family === 'focus_navigation') out.push('Current focus, replay cursor, or sample-stream state.');
  if (family === 'surface_bridge') out.push('Owned browser surfaces, their focus, or input state.');
  if (family === 'theater_profile_recipe') out.push('Scene-shell mode, profile, recipe, or replay/camera presentation state.');
  if (family === 'character_runtime') out.push('Mounted runtime subject, animation state, playback, or inhabitant presence.');
  if (family === 'builder_workbench') out.push('Builder selection, scaffold state, workbench editing settings, or serialized blueprint data.');
  if (family === 'builder_motion') out.push('Builder pose store, staged timeline state, or authored motion data.');
  if (family === 'environment_misc') out.push('Cross-cutting shell state such as profile kits, world profile, or scene filters.');
  if (entryKind === 'ui_action') out.unshift('Browser-local UI state that may or may not dispatch a persistent runtime command.');
  if (command === 'workbench_set_timeline_cursor') out.push('Repositions the staged builder timeline and updates the visible pose.');
  if (command === 'workbench_preview_settle') out.push('Stages a transient corrective settle timeline without mutating authored motion until commit.');
  if (command === 'workbench_commit_settle') out.push('Promotes the staged settle preview into authored timeline or clip state and clears the transient preview.');
  if (command === 'workbench-toggle-turntable') out.push('Local workbench turntable flag stored in the theater session.');
  return dedupeList(out);
}

function modeNotesForEntry(command, family, entryKind) {
  const base = (FAMILY_DEFAULTS[family] && FAMILY_DEFAULTS[family].mode_notes) || [];
  const extra = [];
  if (command === 'workbench_set_timeline_cursor') extra.push('Works only when a builder timeline is currently loaded.');
  if (command === 'workbench_preview_settle') extra.push('Preview settle forces pose-mode editing when needed because batch pose emission is pose-only.');
  if (command === 'workbench_commit_settle') extra.push('Commit settle depends on an active preview; it does not generate a new settle plan on its own.');
  if (command === 'character_set_model') extra.push('Mounted-asset inspection and builder-subject mode are separate visual regimes.');
  if (entryKind === 'ui_action') extra.push('UI-local actions are discovered from browser source and are not guaranteed to be callable through env_control.');
  return dedupeList([...base, ...extra]);
}

function gotchasForCommand(command, family, transports, bridgesTo, entryKind) {
  const out = [];
  if (entryKind === 'env_command' && transports && transports.env_control) {
    out.push('env_control results attach paired text_theater observation so agents can inspect current mirrored scene state without a separate env_read round-trip.');
    out.push('Attached payload shape is text_theater.current_compact, text_theater.snapshot, and text_theater.freshness; include_full=true also returns current_full with theater plus embodiment.');
    out.push('Check text_theater.freshness.cache_advanced_after_command and text_theater.freshness.matched_command_sync before trusting the attached frame as post-command truth; when false, you are looking at the newest mirrored state, but not a confirmed fresh sync for that command yet.');
    out.push('Use env_read(query=\'text_theater_view\') only when you need the richer consult renderer on demand; the hot path should prefer the attached browser-authored text_theater payload.');
  }
  if (command === 'workbench_set_timeline_cursor') {
    out.push('Builder-only; timeline scrub will fail when no builder subject is active.');
  }
  if (command === 'workbench_preview_settle') {
    out.push('Preview settle stages a transient micro-timeline but does not autoplay or mutate authored clips.');
    out.push('It will force pose mode if needed because settle output is emitted through batch pose transforms.');
  }
  if (command === 'workbench_commit_settle') {
    out.push('Commit settle needs an active preview generated first.');
  }
  if (command === 'character_set_model') {
    out.push('Uses direct asset refs/URLs, not manifest aliases.');
  }
  if (command.startsWith('capture_')) {
    out.push('Capture dispatch does not guarantee the browser completed the capture until corroborated via files or shared_state.');
  }
  if (!transports.env_control && transports.browser_surface) {
    out.push('Browser-visible, but not proxied through env_control.');
  }
  if (family === 'surface_bridge') {
    out.push('Surface commands often depend on an owned/browser surface being active first.');
  }
  if (family === 'builder_workbench' || family === 'builder_motion') {
    out.push('Most builder commands require builder_subject mode; mounted-asset inspection is not enough.');
  }
  if (entryKind === 'ui_action') {
    out.push('UI-local action; do not assume there is an equivalent direct env_control command.');
  }
  if (entryKind === 'ui_action' && command === 'workbench-toggle-turntable') {
    out.push('Turntable is session-local browser behavior; remote env_control callers cannot flip it directly.');
  }
  if (entryKind === 'ui_action' && command === 'workbench-toggle-pause') {
    out.push('Pause acts on the local preview action object; it is not the same surface as builder preset staging.');
  }
  if (entryKind === 'ui_action' && command === 'workbench-set-locomotion') {
    out.push('Locomotion preview is a browser-side preview lane; it can clear clip overrides in some cases.');
  }
  if (bridgesTo.length) {
    out.push(`This UI action bridges into ${bridgesTo.join(', ')} after local browser-side work.`);
  }
  return out;
}

function failureModesForEntry(command, family, entryKind, bridgesTo) {
  const out = [];
  if (family === 'builder_workbench' || family === 'builder_motion') out.push('No builder subject active.');
  if (family === 'character_runtime') out.push('No mounted runtime character is active.');
  if (family === 'surface_bridge') out.push('Owned surface id or selector is missing or stale.');
  if (family === 'focus_navigation') out.push('Requested target is not present in the current ledger, replay state, or scene context.');
  if (family === 'capture_observer') out.push('Browser capture was queued but no saved output appeared yet.');
  if (entryKind === 'ui_action') out.push('The expected browser panel, helper strip, or workbench context is not currently visible.');
  if (command === 'workbench_set_timeline_cursor') out.push('No active timeline is loaded, so scrub has nothing to apply.');
  if (command === 'workbench_preview_settle') out.push('Current balance diagnostics did not produce a recoverable settle reaction.');
  if (command === 'workbench_commit_settle') out.push('No active settle preview exists to merge or compile.');
  if (command === 'character_set_model') out.push('The asset ref could not be loaded or produced an empty mounted runtime.');
  if (bridgesTo.includes('workbench_set_load_field')) out.push('Local helper chip flipped but persistent load-field readback stayed stale until sync completed.');
  return dedupeList(out);
}

function verificationForEntry(command, family, entryKind) {
  const base = (FAMILY_DEFAULTS[family] && FAMILY_DEFAULTS[family].verification) || [];
  const extra = [];
  if (entryKind === 'env_command') extra.push('env_read(query=\'text_theater_view\')');
  if (command === 'character_get_animation_state') extra.push('character_get_animation_state');
  if (command === 'workbench_get_blueprint') extra.push('workbench_get_blueprint');
  if (command === 'workbench_set_timeline_cursor') extra.push('capture_time_strip');
  if (command === 'workbench_preview_settle') extra.push('capture_probe');
  if (command === 'workbench_commit_settle') extra.push('capture_time_strip');
  if (command === 'workbench_set_load_field' || command === 'workbench-toggle-load-field') extra.push('capture_probe');
  if (entryKind === 'ui_action') extra.push('visible browser surface behavior');
  return dedupeList([...base, ...extra]);
}

function relatedCommands(command, family, bridgesTo) {
  if (command === 'workbench_set_timeline_cursor') return ['workbench_compile_clip', 'capture_probe', 'capture_time_strip'];
  if (command === 'workbench_preview_settle') return ['workbench_commit_settle', 'workbench_set_timeline_cursor', 'capture_probe'];
  if (command === 'workbench_commit_settle') return ['workbench_preview_settle', 'workbench_compile_clip', 'capture_time_strip'];
  if (command === 'character_set_model') return ['workbench_new_builder', 'capture_probe', 'capture_supercam'];
  if (command === 'workbench_get_blueprint') return ['workbench_save_blueprint', 'workbench_load_blueprint', 'capture_probe'];
  if (command === 'workbench-toggle-turntable') return ['capture_probe', 'workbench-shot-preset'];
  if (bridgesTo.length) return dedupeList([...bridgesTo, 'capture_probe']);
  const familyCommands = {
    camera_pose: ['capture_supercam', 'capture_probe'],
    capture_observer: ['capture_probe', 'capture_supercam', 'capture_time_strip'],
    character_runtime: ['character_focus', 'character_set_model', 'capture_probe'],
    builder_workbench: ['workbench_get_blueprint', 'workbench_frame_part', 'capture_probe'],
    builder_motion: ['workbench_set_timeline_cursor', 'workbench_compile_clip', 'capture_time_strip'],
    focus_navigation: ['capture_supercam', 'sample_now', 'toggle_stream'],
    surface_bridge: ['open_surface', 'inspect_surface', 'focus_surface'],
    theater_profile_recipe: ['set_theater_mode', 'set_camera_mode', 'set_replay_mode'],
    environment_misc: ['set_world_profile', 'set_camera_preset'],
  };
  return familyCommands[family] || [];
}

function surfaceEntrypointsForCommand(command, actionAnchors, commandNames) {
  const aliases = [];
  actionAnchors.forEach((_rows, action) => {
    if (STANDALONE_UI_ACTIONS.has(action)) return;
    if (normalizeActionToCommand(action) === command && commandNames.includes(command)) aliases.push(action);
  });
  return aliases.sort((a, b) => a.localeCompare(b));
}

function commandSourceAnchors(command, serverLines, mainAnchors, actionAnchors, surfaceEntrypoints) {
  const anchors = [];
  const serverNeedle = `"${command}"`;
  const lineIndex = serverLines.findIndex((line) => line.includes(serverNeedle));
  if (lineIndex >= 0) {
    anchors.push({
      file: 'server.py',
      line: lineIndex + 1,
      kind: 'proxy_list',
    });
  }
  const rows = mainAnchors.get(command) || [];
  rows.slice(0, 4).forEach((row) => anchors.push(row));
  (surfaceEntrypoints || []).forEach((action) => {
    const actionRows = actionAnchors.get(action) || [];
    actionRows.slice(0, 2).forEach((row) => anchors.push(row));
  });
  return anchors;
}

const args = parseArgs(process.argv.slice(2));
const cwd = process.cwd();
const serverPath = path.resolve(cwd, 'server.py');
const mainPath = path.resolve(cwd, 'static', 'main.js');
const outputPath = path.resolve(cwd, String(args.output || path.join('static', 'data', 'help', 'environment_command_registry.json')));
const overridesPath = path.resolve(cwd, String(args.overrides || path.join('static', 'data', 'help', 'environment_command_overrides.json')));

const serverText = fs.readFileSync(serverPath, 'utf8');
const mainText = fs.readFileSync(mainPath, 'utf8');
const serverLines = serverText.split(/\r?\n/);
const mainAnchors = findCommandAnchors(mainText, 'static/main.js');
const actionAnchors = findActionAnchors(mainText, 'static/main.js');

const proxyCommands = new Set(extractFrozenset(serverText, '_ENV_CONTROL_PROXY_COMMANDS'));
const hostCommands = new Set(extractJsArray(mainText, 'host_commands', 'legacy_host_commands'));
const implementedVerbs = new Set(extractJsArray(mainText, 'implemented_verbs', 'agent_bearing'));

const commandNames = Array.from(new Set([...proxyCommands, ...hostCommands])).sort((a, b) => a.localeCompare(b));

let overrides = {};
if (fs.existsSync(overridesPath)) {
  overrides = JSON.parse(fs.readFileSync(overridesPath, 'utf8'));
}
const commandOverrides = (overrides && overrides.commands && typeof overrides.commands === 'object') ? overrides.commands : {};
const familyOverrides = (overrides && overrides.families && typeof overrides.families === 'object') ? overrides.families : {};
const uiActionOverrides = (overrides && overrides.ui_actions && typeof overrides.ui_actions === 'object') ? overrides.ui_actions : {};
const queryOverrides = (overrides && overrides.queries && typeof overrides.queries === 'object') ? overrides.queries : {};
const playbooks = (overrides && overrides.playbooks && typeof overrides.playbooks === 'object') ? overrides.playbooks : {};

const commands = {};
const queries = {};
const familyBuckets = new Map();
commandNames.forEach((command) => {
  const family = familyForCommand(command);
  if (!familyBuckets.has(family)) familyBuckets.set(family, []);
  familyBuckets.get(family).push(command);
  const surfaceEntrypoints = surfaceEntrypointsForCommand(command, actionAnchors, commandNames);
  const bridgesTo = [];
  const transports = {
    env_control: proxyCommands.has(command),
    browser_surface: hostCommands.has(command) || (mainAnchors.get(command) || []).length > 0 || surfaceEntrypoints.length > 0,
    ui_local_only: false,
    implemented_verb: implementedVerbs.has(command.replace(/^workbench_/, '').replace(/^character_/, '').replace(/^focus_/, 'focus')),
  };
  const baseEntry = {
    command,
    entry_kind: 'env_command',
    title: titleCase(command),
    category: family,
    status: 'live',
    transport: transports,
    availability: availabilityForCommand(command, family),
    target_contract: targetContractForCommand(command, family),
    summary: summaryForCommand(command, family),
    when_to_use: whenToUseForEntry(command, family, 'env_command'),
    what_it_changes: whatItChangesForEntry(command, family, 'env_command'),
    mode_notes: modeNotesForEntry(command, family, 'env_command'),
    verification: verificationForEntry(command, family, 'env_command'),
    gotchas: gotchasForCommand(command, family, transports, bridgesTo, 'env_command'),
    failure_modes: failureModesForEntry(command, family, 'env_command', bridgesTo),
    aliases: surfaceEntrypoints,
    surface_entrypoints: surfaceEntrypoints,
    bridges_to: bridgesTo,
    related_commands: relatedCommands(command, family, bridgesTo),
    source_anchors: commandSourceAnchors(command, serverLines, mainAnchors, actionAnchors, surfaceEntrypoints),
  };
  commands[command] = mergeObjects(baseEntry, commandOverrides[command] || {});
});

Array.from(STANDALONE_UI_ACTIONS).sort((a, b) => a.localeCompare(b)).forEach((action) => {
  if (!actionAnchors.has(action)) return;
  const family = familyForUiAction(action);
  if (!familyBuckets.has(family)) familyBuckets.set(family, []);
  familyBuckets.get(family).push(action);
  const bridgesTo = dedupeList(UI_ACTION_BRIDGES[action] || []);
  const transports = {
    env_control: false,
    browser_surface: true,
    ui_local_only: true,
    implemented_verb: false,
  };
  const baseEntry = {
    command: action,
    entry_kind: 'ui_action',
    title: titleCase(action),
    category: family,
    status: 'live',
    transport: transports,
    availability: availabilityForCommand(action, family),
    target_contract: targetContractForUiAction(action),
    summary: summaryForUiAction(action),
    when_to_use: whenToUseForEntry(action, family, 'ui_action'),
    what_it_changes: whatItChangesForEntry(action, family, 'ui_action'),
    mode_notes: modeNotesForEntry(action, family, 'ui_action'),
    verification: verificationForEntry(action, family, 'ui_action'),
    gotchas: gotchasForCommand(action, family, transports, bridgesTo, 'ui_action'),
    failure_modes: failureModesForEntry(action, family, 'ui_action', bridgesTo),
    aliases: [],
    surface_entrypoints: [action],
    bridges_to: bridgesTo,
    related_commands: relatedCommands(action, family, bridgesTo),
    source_anchors: (actionAnchors.get(action) || []).slice(0, 4),
  };
  commands[action] = mergeObjects(baseEntry, uiActionOverrides[action] || {});
});

Object.keys(queryOverrides).sort((a, b) => a.localeCompare(b)).forEach((query) => {
  const override = queryOverrides[query] || {};
  const family = String(override.category || override.family || 'observation_query');
  if (!familyBuckets.has(family)) familyBuckets.set(family, []);
  familyBuckets.get(family).push(query);
  const baseEntry = {
    query,
    entry_kind: 'env_read_query',
    title: titleCase(query),
    category: family,
    status: 'live',
    transport: {
      env_read: true,
      env_control: false,
      browser_surface: false,
      ui_local_only: false,
      implemented_verb: false,
    },
    summary: `Read ${query} from the live environment/browser state.`,
    when_to_use: whenToUseForEntry(query, family, 'env_read_query'),
    what_it_changes: [],
    mode_notes: modeNotesForEntry(query, family, 'env_read_query'),
    verification: verificationForEntry(query, family, 'env_read_query'),
    gotchas: gotchasForCommand(query, family, { env_control: false, browser_surface: false, ui_local_only: false, implemented_verb: false }, [], 'env_read_query'),
    failure_modes: failureModesForEntry(query, family, 'env_read_query', []),
    aliases: [],
    related_commands: [],
    source_anchors: [],
  };
  queries[query] = mergeObjects(baseEntry, override);
});

const families = {};
Array.from(familyBuckets.keys()).sort((a, b) => a.localeCompare(b)).forEach((family) => {
  const base = {
    category: family,
    title: FAMILY_DEFAULTS[family].title,
    description: FAMILY_DEFAULTS[family].description,
    count: familyBuckets.get(family).length,
    commands: familyBuckets.get(family).slice().sort((a, b) => a.localeCompare(b)),
    when_to_use: FAMILY_DEFAULTS[family].when_to_use,
    mode_notes: FAMILY_DEFAULTS[family].mode_notes,
    verification: FAMILY_DEFAULTS[family].verification,
  };
  families[family] = mergeObjects(base, familyOverrides[family] || {});
});

const commandEntryCount = Object.keys(commands).length;
const queryCount = Object.keys(queries).length;
const entryCount = commandEntryCount + queryCount;
const uiActionCount = Object.values(commands).filter((entry) => entry && entry.entry_kind === 'ui_action').length;
const envCommandCount = commandEntryCount - uiActionCount;

const registry = {
  meta: {
    generated_at: new Date().toISOString(),
    generated_by: 'scripts/generate-env-help-registry.js',
    update_commands: [
      'node scripts/generate-env-help-registry.js',
      'npm run build:env-help',
    ],
    sources: [
      'server.py::_ENV_CONTROL_PROXY_COMMANDS',
      'static/main.js::command_surface.host_commands',
      'static/main.js::command handlers and _envQueueControl callsites',
      'static/main.js::ui action handlers and data-env-action entrypoints',
      'static/data/help/environment_command_overrides.json',
    ],
    counts: {
      entries: entryCount,
      env_commands: envCommandCount,
      ui_actions: uiActionCount,
      queries: queryCount,
      proxied_commands: proxyCommands.size,
      host_commands: hostCommands.size,
      families: Object.keys(families).length,
      playbooks: Object.keys(playbooks).length,
    },
  },
  families,
  commands,
  queries,
  playbooks,
};

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(registry, null, 2)}\n`, 'utf8');

console.log(`Wrote ${outputPath}`);
console.log(`Entries: ${entryCount}`);
console.log(`Env commands: ${envCommandCount}`);
console.log(`UI actions: ${uiActionCount}`);
console.log(`Queries: ${queryCount}`);
console.log(`Families: ${Object.keys(families).length}`);
console.log(`Playbooks: ${Object.keys(playbooks).length}`);
