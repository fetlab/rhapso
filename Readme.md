# Rhapso: Automatically Embedding Fiber Materials into 3D Prints for Enhanced Interactivity

This respository hosts the 3D design files and software for Rhapso, a system to automatically embed fiber materials like thread into 3D-printed objects while they are being printed. Rhapso is published at the The 37th Annual ACM Symposium on User Interface Software and Technology (UIST ’24) ([DOI](https://doi.org/10.1145/3654777.3676468)). If you use any of the code or models from this repository, please cite the paper as follows:

Daniel Ashbrook, Wei-Ju Lin, Nicholas Bentley, Diana Soponar, Valkyrie Savage, Zeyu Yan, Lung-Pan Cheng, Huaishu Peng, and Hyunyoung Kim.  2024. Rhapso: Automatically Embedding Fiber Materials into 3D Prints for Enhanced Interactivity. In The 37th Annual ACM Symposium on User Interface Software and Technology (UIST ’24), October 13–16, 2024, Pittsburgh, PA, USA.  ACM, New York, NY, USA, 20 pages. https://doi.org/10.1145/3654777.3676468

**Abstract:**
_We introduce Rhapso, a 3D printing system designed to embed a diverse range of continuous fiber materials within 3D objects during the printing process. This approach enables integrating properties like tensile strength, force storage and transmission, or aesthetic and tactile characteristics, directly into low-cost thermoplastic 3D prints. These functional objects can have intricate actuation, self-assembly, and sensing capabilities with little to no manual intervention. To achieve this, we modify a low-cost Fused Filament Fabrication (FFF) 3D printer, adding a stepper motor-controlled fiber spool mechanism on a gear ring above the print bed. In addition to hardware, we provide parsing software for precise fiber placement, which generates Gcode for printer operation. To illustrate the versatility of our system, we present applications that showcase its extensive design potential. Additionally, we offer comprehensive documentation and open designs, empowering others to replicate our system and explore its possibilities._

## Hardware

Rhapso is based on a modified Ender 3 Pro 3D printer. You can see and download the Autodesk Fusion model [here](https://a360.co/3THGoSW) (also in this repo as `Rhapso—Ender 3.f3z`). You need to print the objects that are part of the "Print these objects" selection set. In addition, you need a printer motherboard which can drive an extra motor (we used a BIGTREETECH SKR V1.4 Turbo), a NEMA-40 stepper motor, a 10-inch/25cm "Lazy Susan" turntable bearing ring and a variety of standard M5 and M3 hardware, all of which should be visible in the model.

### Firmware

Rhapso assumes a rotary axis for the ring. You can compile Marlin firmware with that support. See [https://github.com/fetlab/marlin-rhapso](fetlab/marlin-rhapso) for our changes. Note the `README-RHAPSO.md` file in that repository with quick compilation instructions.

## Software

Rhapso's thread router is built on Python, and like all research software, is semi-working and never-to-be-completed.

### Installing

The requirements are listed in `pyproject.toml` and can be installed via `pip install .` or `uv pip install -r pyproject.toml`. 

### Demo

See [basic test.ipynb](basic test.ipynb) for a demo of the router.

## How to…

### Set up Cura to slice for the thread printer
These instructions were tested on Cura 5.1.0.

Add a new **Creality Ender-3 Pro** printer in Cura. Change the following from the defaults:

* _X (Width):_ 79.0 mm
* _X min:_ 0 mm
* _X max:_ 0 mm

#### Slicing settings
The router needs to have enough infill to find places to attach the thread when it turns corners inside of an object. Therefore, we recommend using **50%** infill in the **grid** pattern.

### Design a model with thread

1. Design your model in Fusion 360. Make a copy of the `Print bed` design in the thread printer folder. This has a sketch outline of the print bed with boundaries. Designing with this as the base will prevent alignment issues later on.
2. Add a 3D sketch line to represent the thread. It must:
	* consist of only straight-line segments;
	* only move horizontally (in X/Y) or in the positive vertical direction; and
	* start on an exterior surface of an object.
3. Export the model as a `.3mf` file.
4. Load the `3mf` file into Cura and slice it. "Lines" infill is probably the best; using more-complex infills will massively slow down the routing process because they generate too many individual segments.
5. Save the Gcode file from Cura.
6. Go back to Fusion and select one of the segments of the thread sketch line.
7. Open the _Text Commands_ window (_View → Show Text Commands_). Ensure that the radio button at the bottom-right of this pane is set to **Py**.
8. Copy the contents of [thread_from_fusion.py](thread_from_fusion.py). Paste this into the command line (verbatim, including quotation marks!) and hit enter. It will select the entire connected path and output a list of the vertices. If you're running the code on Mac OS, it will copy the output to the clipboard for you. Otherwise you'll have to do it yourself.
9. Follow the pattern in the demo notebook to use the gcode file and copied thread path to route the model.
