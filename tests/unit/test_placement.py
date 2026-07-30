"""place_and_flip: 3D-model stripping only for tag-swap flips."""
from pcb_designer.placement import place_and_flip

_FP = '''(kicad_pcb
	(footprint "R_0805"
		(layer "{layer}")
		(at 100 100 0)
		(property "Reference" "R1"
			(at 0 0 0)
			(layer "{silk}")
			(effects
				(font
					(size 0.8 0.8)
				){justify}
			)
		)
		(model "${{KICAD9_3DMODEL_DIR}}/Resistor_SMD.3dshapes/R_0805.step"
			(offset (xyz 0 0 0))
		)
	)
)
'''


def test_natively_flipped_keeps_model():
    text = _FP.format(layer="B.Cu", silk="B.SilkS",
                      justify="\n\t\t\t\t(justify mirror)")
    out, updated, missing = place_and_flip(
        text, {"R1": (100.0, 100.0, 90, "B.Cu")})
    assert updated == 1 and not missing
    assert "(model " in out


def test_tag_swap_flip_strips_model():
    text = _FP.format(layer="F.Cu", silk="F.SilkS", justify="")
    out, updated, missing = place_and_flip(
        text, {"R1": (100.0, 100.0, 90, "B.Cu")})
    assert updated == 1 and not missing
    assert "(model " not in out
    assert '(layer "B.Cu")' in out
