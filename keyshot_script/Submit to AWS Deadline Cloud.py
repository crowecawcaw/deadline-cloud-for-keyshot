# AUTHOR AWS
# VERSION 0.0.6
# Submit to AWS Deadline Cloud

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
import os
import subprocess
import json
import tempfile
import lux

job_template = """
specificationVersion: jobtemplate-2023-09
name: Keyframe-Robot-Scene Sharing Version.bip
parameterDefinitions:
- name: KeyShotFile
  type: PATH
  objectType: FILE
  dataFlow: IN
  userInterface:
    control: CHOOSE_INPUT_FILE
    label: KeyShot Package File
    groupLabel: KeyShot Settings
    fileFilters:
    - label: KeyShot Package files
      patterns:
      - '*.ksp'
      - '*.bip'
    - label: All Files
      patterns:
      - '*'
  description: The KeyShot package file to render.
- name: Frames
  type: STRING
  userInterface:
    control: LINE_EDIT
    label: Frames
    groupLabel: KeyShot Settings
  description: The frames to render. E.g. 1-3,8,11-15
  minLength: 1
- name: OutputFilePath
  type: PATH
  objectType: FILE
  dataFlow: OUT
  userInterface:
    control: CHOOSE_INPUT_FILE
    label: Output File Path
    groupLabel: KeyShot Settings
  description: The render output path.
- name: OutputFormat
  type: STRING
  description: The render output format
  allowedValues:
  - RENDER_OUTPUT_PNG
  - RENDER_OUTPUT_JPEG
  - RENDER_OUTPUT_EXR
  - RENDER_OUTPUT_TIFF8
  - RENDER_OUTPUT_TIFF32
  - RENDER_OUTPUT_PSD8
  - RENDER_OUTPUT_PSD16
  - RENDER_OUTPUT_PSD32
  default: RENDER_OUTPUT_PNG
  userInterface:
    control: DROPDOWN_LIST
    label: Output Format(Must match file extension)
    groupLabel: KeyShot Settings
steps:
- name: Render
  parameterSpace:
    taskParameterDefinitions:
    - name: Frame
      type: INT
      range: '{{Param.Frames}}'
  stepEnvironments:
  - name: KeyShot
    description: Runs KeyShot in the background.
    script:
      embeddedFiles:
      - name: initData
        filename: init-data.yaml
        type: TEXT
        data: |
          scene_file: '{{Param.KeyShotFile}}'
          output_file_path: '{{Param.OutputFilePath}}'
          output_format: '{{Param.OutputFormat}}'
      actions:
        onEnter:
          command: KeyShotAdaptor
          args:
          - daemon
          - start
          - --path-mapping-rules
          - file://{{Session.PathMappingRulesFile}}
          - --connection-file
          - '{{Session.WorkingDirectory}}/connection.json'
          - --init-data
          - file://{{Env.File.initData}}
          cancelation:
            mode: NOTIFY_THEN_TERMINATE
        onExit:
          command: KeyShotAdaptor
          args:
          - daemon
          - stop
          - --connection-file
          - '{{ Session.WorkingDirectory }}/connection.json'
          cancelation:
            mode: NOTIFY_THEN_TERMINATE
  script:
    embeddedFiles:
    - name: runData
      filename: run-data.yaml
      type: TEXT
      data: |
        frame: {{Task.Param.Frame}}
    actions:
      onRun:
        command: KeyShotAdaptor
        args:
        - daemon
        - run
        - --connection-file
        - '{{ Session.WorkingDirectory }}/connection.json'
        - --run-data
        - file://{{ Task.File.runData }}
        cancelation:
          mode: NOTIFY_THEN_TERMINATE
"""

# save scene information to json file for submitter module to load
scene_info = lux.getSceneInfo()
current_frame = lux.getAnimationFrame()
animation_info = lux.getAnimationInfo()
external_files = lux.getExternalFiles()

frame_range = f"1-{animation_info['frames']}" if animation_info.get("frames") else f"{current_frame}"
files_to_attach = sorted([*external_files, scene_info["file"]])

with tempfile.TemporaryDirectory() as temp_dir:
    with open(os.path.join(temp_dir, "template.yaml"), "w") as f:
        f.write(job_template)

    with open(os.path.join(temp_dir, "asset_references.json"), "w") as f:
        f.write(json.dumps({
            "assetReferences": {
                "inputs": {
                    "directories": [],
                    "filenames": files_to_attach
                },
                "outputs": {
                    "directories": [],
                },
                "referencedPaths": []
            }
        }))

    with open(os.path.join(temp_dir, "parameter_values.json"), "w") as f:
        f.write(json.dumps({
            "parameterValues": [
                {"name": "KeyShotFile", "value": "/Library/Application Support/KeyShot12/Scenes/Keyframe-Robot-Scene Sharing Version.bip"},
                {"name": "OutputFilePath", "value": "/Library/Application Support/KeyShot12/Scenes/Keyframe-Robot-Scene Sharing Version.bip.%d.png"},
                {"name": "OutputFormat", "value": "RENDER_OUTPUT_PNG"},
                {"name": "Frames", "value": frame_range},
            ]
        }))

    try:
        subprocess.run(
            ['deadline', 'bundle', 'gui-submit', temp_dir],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"AWS Deadline Cloud KeyShot submitter could not open: {e.stderr}")
