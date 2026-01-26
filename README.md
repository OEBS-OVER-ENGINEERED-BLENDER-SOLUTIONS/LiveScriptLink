# Live Script Link

Blender addon that allows you to link internal text blocks to external files. The addon monitors the external files for changes and automatically reloads (and optionally executes) the script in Blender when the file is saved externally.

## Features
- **Auto-Update**: Check for and install the latest versions directly from GitHub within Blender.
- **Multi-link management**: Link multiple files to multiple text blocks simultaneously.
- **Auto-execution**: Automatically run the script after each reload.
- **Visual Feedback**: A customizable green border indicator in the Text Editor when Live Link is active.
- **Configurable Timer**: Choose between constant polling or a delay timer.

## Release Notes

### v1.4
- **Integrated Auto-Updater**: Check for and install updates directly from Blender’s Preferences (powered by CGCookie's library).
- **Structural Overhaul**: Restructured the addon into a professional folder-based package.
- **Improved UI**: Added a collapsible "Dev Settings" section in the Text Editor sidebar.
- **Extended Visual Feedback**: Customizable green outline indicator for active links.
- **Enhanced Reliability**: Improved modal timer logic and fixed registration NameError issues.
- **Branding**: Updated author metadata to "OEBS, Erisol3D".

## Installation
1. Download the [Latest Release](https://github.com/OEBS-OVER-ENGINEERED-BLENDER-SOLUTIONS/LiveScriptLink/releases) (ZIP).
2. Open Blender.
3. Go to `Edit > Preferences > Add-ons`.
4. Click `Install...` and select the ZIP file.
5. Enable `Live Script Link`.

## Author
OEBS, Erisol3D

---

### About OEBS (Over-Engineered Blender Solutions)
OEBS is a specialized brand founded by **Erisol3D**, dedicated to sharing a collection of powerful tools and advanced utilities developed and refined over **7 years** of professional Blender workflow. These solutions are born from real-world production needs, designed to bridge gaps and optimize complex pipelines with precision and reliability.
