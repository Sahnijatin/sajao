# Import stubs for Depth Anything 3

DA3's `api` module imports its export and pose-alignment code when it loads.
Those import evo and plyfile (GPL-3.0), moviepy and pycolmap. The worker only
calls `inference`, never export or pose alignment, so these stubs stand in for
the four packages: the import succeeds, and any use fails loudly. This keeps
GPL code out of the worker image.
