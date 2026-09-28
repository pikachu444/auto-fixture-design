"""Check the assembled bending fixture's intended interfaces and slot travel.

These are geometric checks only. They do not establish a load rating or a
machine-side attachment. Distances are in mm and volumes in mm^3.
"""
import cadquery as cq


def bending_interfaces(parts, result):
    shapes = {p['name']: p['shape'] for p in parts}
    base = shapes['printed_base']
    specimen = shapes['specimen']
    nose = shapes['metal_loading_nose']
    span = result['metrics']['span_mm']
    base_length = result['metrics']['base_length_mm']
    maximum_span = base_length - 60
    checks = []

    def check(code, passed, detail):
        checks.append({'code': code, 'status': 'PASS' if passed else 'FAIL', 'detail': detail})

    # A clearance probe must fit the entire thickness of each printed slot.
    # Probe radius 2.6 gives 0.1 mm radial clearance to the nominal M5 shaft.
    # Endpoints suffice here because the CAD's slot centerline is a straight
    # segment with constant width; we also inspect the installed position.
    for travel_span in (40, span, maximum_span):
        obstruction = 0.0
        for sign in (-1, 1):
            for dx in (-10, 10):
                for y in (-12, 12):
                    x = sign * travel_span / 2 + dx
                    probe = cq.Solid.makeCylinder(2.6, 12, cq.Vector(x, y, 0))
                    obstruction = max(obstruction, base.intersect(probe).Volume())
        check(f'bolt_slot_clearance_span_{travel_span:g}mm', obstruction < 1e-5,
              {'span_mm': travel_span, 'bolt_probe_diameter_mm': 5.2,
               'maximum_obstruction_mm3': obstruction})

    # The installed bolt must have clearance in the support through-hole and
    # counterbore; the head must sit below the roller cradle.
    for label in ('left', 'right'):
        support = shapes[f'printed_support_{label}']
        interference = max(support.intersect(p['shape']).Volume()
                           for p in parts if p['name'].startswith(f'metal_bolt_{label}_'))
        check(f'bolt_support_clearance_{label}', interference < 1e-5,
              {'maximum_interference_mm3': interference})
        roller = shapes[f'metal_roller_{label}']
        bb = roller.BoundingBox()
        center_x = (bb.xmin + bb.xmax) / 2
        half_span = span / 2
        check(f'roller_location_{label}',
              abs(abs(center_x) - half_span) < 1e-6 and bb.ylen >= result['input']['specimen']['width'] + 8,
              {'center_x_mm': center_x, 'required_abs_x_mm': half_span,
               'contact_width_mm': bb.ylen})
        contact_gap = specimen.BoundingBox().zmin - bb.zmax
        check(f'roller_specimen_contact_{label}', abs(contact_gap) < 1e-5,
              {'vertical_gap_mm': contact_gap})

    loading_gap = nose.BoundingBox().zmin - specimen.BoundingBox().zmax
    check('nose_specimen_contact', abs(loading_gap) < 1e-5 and abs(nose.Center().x) < 1e-6,
          {'vertical_gap_mm': loading_gap, 'nose_center_x_mm': nose.Center().x})
    left = shapes['printed_support_left'].BoundingBox()
    right = shapes['printed_support_right'].BoundingBox()
    support_gap = right.xmin - left.xmax
    check('support_clearance', support_gap >= -1e-6,
          {'support_gap_mm': support_gap})
    return checks
