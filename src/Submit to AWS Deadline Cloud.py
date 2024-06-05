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
                "control": "CHOOSE_INPUT_FILE",
                "label": "KeyShot Package File",
                "groupLabel": "KeyShot Settings",
                "fileFilters": [
                    {"label": "KeyShot Package files", "patterns": ["*.ksp", "*.bip"]},
                    {"label": "All Files", "patterns": ["*"]},
                ],
            },
            "description": "The KeyShot package file to render.",
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
                "label": "Output Format (must match file extension)",
                "groupLabel": "KeyShot Settings",
            },
        },
    ],
    "steps": [
        {
            "name": "RenderCommand",
            "parameterSpace": {
                "taskParameterDefinitions": [
                    {"name": "Frame", "type": "INT", "range": "{{Param.Frames}}"}
                ]
            },
            "stepEnvironments": [{"name": "KeyShot", "variables": {"OUTPUT_PATH": ""}}],
            "script": {
                "actions": {
                    "onRun": {"command": "powershell", "args": ["-File", "{{Task.File.Run}}"]}
                },
                "embeddedFiles": [
                    {
                        "name": "headlessScript",
                        "filename": "headlessScript.py",
                        "type": "TEXT",
                        "data": (
                            "opts = lux.getRenderOptions()\n"
                            "opts.setAddToQueue(False)\n"
                            'frame = int("{{Task.Param.Frame}}")\n'
                            "lux.setAnimationFrame(frame)\n"
                            'output_path = r"{{Param.OutputFilePath}}"\n'
                            'output_path = output_path.replace("%d", str(frame))\n'
                            "output_format_code = lux.RENDER_OUTPUT_{{Param.OutputFormat}}\n"
                            'print("Output Path: %s" % output_path)\n'
                            'print("Output Format: %s" % output_format_code)\n'
                            "lux.renderImage(path=output_path, opts=opts, format=output_format_code)\n"
                            "exit()\n"
                        ),
                    },
                    {
                        "name": "Run",
                        "runnable": True,
                        "filename": "run.ps1",
                        "type": "TEXT",
                        "data": (
                            "# Licensing should be configured using a floating license server specified\n"
                            "# by setting the environment variable LUXION_LICENSE_FILE=<PORT>:<ADDRESS>\n"
                            "keyshot_headless -progress -floating_feature keyshot2 '{{Param.KeyShotFile}}' -script '{{Task.File.headlessScript}}'\n"
                        ),
                    },
                ],
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

    with open(os.path.join(temp_dir, "asset_references.yaml"), "w") as f:
        f.write(json.dumps(asset_references))

    with open(os.path.join(temp_dir, "parameter_values.yaml"), "w") as f:
        f.write(json.dumps(parameter_values))

    # For sticky settings, find the most recent matching bundle and if it exists, reuse its settings.
    # Naming logic copied from the Deadline library. TODO make this less brittle by importing the naming
    # logic as a function or by avoiding searching for files by a naming convension in the first place.
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

            # Tradeoff: Choosing not to copy asset references over so newly added textures get auto-attached on later submissions,
            # but a the cost of not including manually attached files in later submissions.
            shutil.copyfile(
                os.path.join(latest_bundle_folder, "parameter_values.yaml"),
                os.path.join(temp_dir, "parameter_values.yaml"),
            )
        except Exception as e:
            print(
                f"Found a recent bundle at {latest_bundle_folder} but failed to copy over its parameter values: {e}"
            )

    try:
        # Execute the gui-submitter using bash since it's more likely to have
        shell_executable = os.environ.get("SHELL", "/bin/bash")
        subprocess.run(
            [shell_executable, "-i", "-c", f"deadline bundle gui-submit {temp_dir}"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"AWS Deadline Cloud KeyShot submitter could not open: {e.stderr}")
