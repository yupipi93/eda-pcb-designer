# assets/3dmodels — extra 3D models shipped into the toolchain images

Installed on top of `kicad-packages3d` at `/usr/share/kicad/3dmodels/`
(both Dockerfiles), so footprints can reference them via
`${KICAD9_3DMODEL_DIR}` in local and hosted renders alike.

| Model | Origin |
|---|---|
| `LED_THT.3dshapes/LED_D3.0mm_Orange.step` | copy of kicad-packages3d `LED_D3.0mm.step` (red) with the body `COLOUR_RGB` patched to orange — the library ships Green/Yellow/Blue/Clear variants but no orange |
