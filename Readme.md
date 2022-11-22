# Rhapso thread router

## Installing

Run `pip install -r requirements.txt` to get the required packages. See the demo notebook (below) for further instructions to visualize output in JupyterLab.

## Demo

See [Demo.ipynb](Demo.ipynb) for a demo of the router.

## How to…

### Set up Cura to slice for the thread printer
These instructions were tested on Cura 5.1.0.

Add a new **Creality Ender-3 Pro** printer in Cura. Change the following from the defaults:

* _X (Width):_ 79.0 mm
* _X min:_ 0 mm
* _X max:_ 0 mm

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
