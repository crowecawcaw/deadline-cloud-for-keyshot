# AUTHOR AWS
# VERSION 0.0.6
# Submit to AWS Deadline Cloud

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
import os
import shutil
import glob
import subprocess
import json
import tempfile
import lux
import platform
import shlex

scene_file = lux.getSceneInfo()["file"]
external_files = lux.getExternalFiles()
current_frame = lux.getAnimationFrame()
frame_count = lux.getAnimationInfo().get("frames")

frame_range = f"1-{frame_count}" if frame_count else f"{current_frame}"
files_to_attach = sorted([*external_files, scene_file])
output_directory = str(os.path.dirname(scene_file))

_, filename = os.path.split(scene_file)

job_template = {
    "specificationVersion": "jobtemplate-2023-09",
    "name": filename,
    "parameterDefinitions": [
        {
            "name": "KeyShotFile",
            "type": "PATH",
            "objectType": "FILE",
            "dataFlow": "IN",
            "userInterface": {
                "control": "HIDDEN",
                "label": "KeyShot Package File",
                "groupLabel": "KeyShot Settings",
            },
            "description": "The KeyShot package file to render.",
            "default": "",  # Workaround for https://github.com/aws-deadline/deadline-cloud/issues/343
        },
        {
            "name": "Frames",
            "type": "STRING",
            "userInterface": {
                "control": "LINE_EDIT",
                "label": "Frames",
                "groupLabel": "KeyShot Settings",
            },
            "description": "The frames to render. E.g. 1-3,8,11-15",
            "minLength": 1,
        },
        {
            "name": "OutputFilePath",
            "type": "PATH",
            "objectType": "FILE",
            "dataFlow": "OUT",
            "userInterface": {
                "control": "CHOOSE_INPUT_FILE",
                "label": "Output File Path",
                "groupLabel": "KeyShot Settings",
            },
            "description": "The render output path.",
        },
        {
            "name": "OutputFormat",
            "type": "STRING",
            "description": "The render output format",
            "allowedValues": ["PNG", "JPEG", "EXR", "TIFF8", "TIFF32", "PSD8", "PSD16", "PSD32"],
            "default": "PNG",
            "userInterface": {
                "control": "DROPDOWN_LIST",
                "label": "Output Format(Must match file extension)",
                "groupLabel": "KeyShot Settings",
            },
        },
    ],
    "steps": [
        {
            "name": "Render",
            "parameterSpace": {
                "taskParameterDefinitions": [
                    {"name": "Frame", "type": "INT", "range": "{{Param.Frames}}"}
                ]
            },
            "stepEnvironments": [
                {
                    "name": "KeyShot",
                    "description": "Runs KeyShot in the background.",
                    "script": {
                        "embeddedFiles": [
                            {
                                "name": "initData",
                                "filename": "init-data.yaml",
                                "type": "TEXT",
                                "data": (
                                    "scene_file: '{{Param.KeyShotFile}}'\n"
                                    "output_file_path: '{{Param.OutputFilePath}}'\n"
                                    "output_format: 'RENDER_OUTPUT_{{Param.OutputFormat}}'\n"
                                    ""
                                ),
                            }
                        ],
                        "actions": {
                            "onEnter": {
                                "command": "KeyShotAdaptor",
                                "args": [
                                    "daemon",
                                    "start",
                                    "--path-mapping-rules",
                                    "file://{{Session.PathMappingRulesFile}}",
                                    "--connection-file",
                                    "{{Session.WorkingDirectory}}/connection.json",
                                    "--init-data",
                                    "file://{{Env.File.initData}}",
                                ],
                                "cancelation": {"mode": "NOTIFY_THEN_TERMINATE"},
                            },
                            "onExit": {
                                "command": "KeyShotAdaptor",
                                "args": [
                                    "daemon",
                                    "stop",
                                    "--connection-file",
                                    "{{ Session.WorkingDirectory }}/connection.json",
                                ],
                                "cancelation": {"mode": "NOTIFY_THEN_TERMINATE"},
                            },
                        },
                    },
                }
            ],
            "script": {
                "embeddedFiles": [
                    {
                        "name": "runData",
                        "filename": "run-data.yaml",
                        "type": "TEXT",
                        "data": "frame: {{Task.Param.Frame}}",
                    }
                ],
                "actions": {
                    "onRun": {
                        "command": "KeyShotAdaptor",
                        "args": [
                            "daemon",
                            "run",
                            "--connection-file",
                            "{{ Session.WorkingDirectory }}/connection.json",
                            "--run-data",
                            "file://{{ Task.File.runData }}",
                        ],
                        "cancelation": {"mode": "NOTIFY_THEN_TERMINATE"},
                    }
                },
            },
        }
    ],
}

asset_references = {
    "assetReferences": {
        "inputs": {"directories": [], "filenames": files_to_attach},
        "outputs": {
            "directories": [output_directory],
        },
        "referencedPaths": [],
    }
}

parameter_values = {
    "parameterValues": [
        {"name": "KeyShotFile", "value": scene_file},
        {"name": "OutputFilePath", "value": f"{scene_file}.%d.png"},
        {"name": "OutputFormat", "value": "RENDER_OUTPUT_PNG"},
        {"name": "Frames", "value": frame_range},
    ]
}

with tempfile.TemporaryDirectory() as temp_dir:
    with open(os.path.join(temp_dir, "template.json"), "w") as f:
        f.write(json.dumps(job_template))

    with open(os.path.join(temp_dir, "asset_references.json"), "w") as f:
        f.write(json.dumps(asset_references))

    with open(os.path.join(temp_dir, "parameter_values.json"), "w") as f:
        f.write(json.dumps(parameter_values))

    # TODO make this less brittle
    # For sticky settings, find the most recent matching bundle and if it exists, reuse its parameter
    # values. Naming logic copied from the Deadline library.
    bundle_directory_name = "".join(char for char in filename if char.isalnum() or char in " -_")
    bundle_directory_name = bundle_directory_name[:128]
    matching_templates = glob.glob(
        os.path.expanduser(f"~/.deadline/job_history/**/**/*{bundle_directory_name}*/template.yaml")
    )
    latest_template = max(matching_templates, key=os.path.getctime) if matching_templates else None

    if latest_template:
        try:
            latest_bundle_folder, _ = os.path.split(latest_template)
            # Ideally, some settings would be sticky (e.g. frame range) and others would be reset every time (e.g. file path).
            # Bundle parameters and assets are only saved as yaml files, and Keyshot does not have a yaml parsing library
            # installed, so we can't parse and select which parameters or assets we want to save from a previous submission.

            # Considering the tradeoffs:
            # * We'll copy over parameter values from a previous submission. But if someone updates the frame range in the scene,
            #   they'll need to update the frame range in the submitter as well.
            # * We won't copy over asset references so that newly added textures get auto-attached on later submissions, but at
            #   the cost of not including manually attached files in later submissions.

            # Copy over the previous parameters yaml file and delete our json file.
            shutil.copyfile(
                os.path.join(latest_bundle_folder, "parameter_values.yaml"),
                os.path.join(temp_dir, "parameter_values.yaml"),
            )
            os.remove(os.path.join(temp_dir, "parameter_values.json"))
        except Exception as e:
            print(
                f"Found a recent bundle at {latest_bundle_folder} but failed to copy over its parameter values: {e}"
            )
            # Print the error and just use the newly generated parameter_values.json file instead.

    try:
        if platform.system() == "Darwin" or platform.system() == "Linux":
            # Execute the command using an bash in interactive mode so it loads loads the bash profile to set
            # the PATH correctly. Attempting to run `deadline` directly will probably fail since Keyshot's default
            # PATH likely doesn't include the Deadline client.
            shell_executable = os.environ.get("SHELL", "/bin/bash")
            subprocess.run(
                [
                    shell_executable,
                    "-i",
                    "-c",
                    f"deadline bundle gui-submit {shlex.quote(temp_dir)}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            subprocess.run(
                ["deadline", "bundle", "gui-submit", f"{temp_dir}"],
                check=True,
                capture_output=True,
                text=True,
            )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"AWS Deadline Cloud KeyShot submitter could not open: {e.stderr}")
