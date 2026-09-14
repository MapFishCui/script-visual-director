"""Small, strict schemas; keep source-of-truth beside the validating tools."""
from jsonschema import Draft202012Validator


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


def arr(items, minimum=0):
    return {"type": "array", "items": items, "minItems": minimum}


def enum(*values):
    return {"enum": list(values)}


TEXT = {"type": "string", "minLength": 1}
ID = {"type": "string", "pattern": r"^[A-Za-z][A-Za-z0-9_-]*$"}
NUMBER = {"type": "number"}
POSITIVE = {"type": "number", "exclusiveMinimum": 0}
VERSION = {"type": "integer", "minimum": 1}
VEC2 = {"type": "array", "items": NUMBER, "minItems": 2, "maxItems": 2}
VEC3 = {"type": "array", "items": NUMBER, "minItems": 3, "maxItems": 3}
SOURCE = obj({"basis": enum("explicit", "inferred", "proposed"), "text": TEXT})
REF = obj({"id": ID, "version": VERSION})
DEPENDENCY = obj({"kind": enum("asset", "layout"), "id": ID, "version": VERSION})
REVIEW = obj({"status": enum("pending", "passed", "needs_revision"), "note": {"type": "string"}})
APPROVAL = obj({"status": enum("not_required", "pending", "approved", "rejected"), "evidence": {"type": "string"}})
ASSET_VERSION = obj({
    "version": VERSION, "file": {"type": ["string", "null"]},
    "production": enum("planned", "prompt_ready", "generated", "failed"),
    "validity": enum("current", "stale", "superseded"), "review": REVIEW,
    "approval": APPROVAL, "prompt": {"type": "string"}, "tool": {"type": "string"},
    "dependencies": arr(DEPENDENCY), "gates": arr(ID), "note": {"type": "string"}
})
ASSET = obj({"id": ID, "type": enum("character", "scene", "prop"), "name": TEXT,
             "description": TEXT, "sources": arr(SOURCE, 1), "shots": arr(ID, 1),
             "current_version": VERSION, "versions": arr(ASSET_VERSION, 1)})
SHOT = obj({"id": ID, "beat": ID, "purpose": TEXT, "description": TEXT,
            "assets": arr(ID), "layout": {"anyOf": [REF, {"type": "null"}]},
            "camera": {"type": ["string", "null"]}, "continuity": TEXT})
LAYOUT_RECORD = obj({"id": ID, "version": VERSION, "path": TEXT, "outputs": arr(TEXT),
                     "review": REVIEW, "blockout_required": {"type": "boolean"},
                     "blockout_review": REVIEW})
MANIFEST = obj({
    "schema_version": {"const": 1}, "name": TEXT,
    "documents": arr(obj({"path": TEXT, "role": enum("source", "analysis", "visual-guide", "handoff")})),
    "shots": arr(SHOT), "assets": arr(ASSET), "layouts": arr(LAYOUT_RECORD),
    "gates": arr(obj({"id": ID, "refs": arr(REF, 1),
                      "status": enum("pending", "approved", "rejected"), "evidence": {"type": "string"}}))
})
BOX = obj({"id": ID, "label": TEXT, "kind": enum("wall", "furniture", "prop", "door", "window", "actor", "light"),
           "center": VEC3, "size": {"type": "array", "items": POSITIVE, "minItems": 3, "maxItems": 3},
           "rotation": NUMBER, "solid": {"type": "boolean"}, "source": SOURCE})
CAMERA = obj({"id": ID, "shot": ID, "position": VEC3, "target": VEC3,
              "yfov": {"type": "number", "exclusiveMinimum": 1, "exclusiveMaximum": 170},
              "aspect": POSITIVE, "path": arr(VEC3), "source": SOURCE})
PATH = obj({"id": ID, "actor": ID, "shot": ID, "points": arr(VEC3, 2),
            "clearance": {"type": "number", "minimum": 0}, "source": SOURCE})
LAYOUT = obj({"schema_version": {"const": 1}, "id": ID, "version": VERSION, "name": TEXT,
              "units": {"const": "m"}, "extent": {"type": "array", "items": POSITIVE, "minItems": 2, "maxItems": 2},
              "height": POSITIVE, "assumptions": arr(TEXT), "boxes": arr(BOX),
              "cameras": arr(CAMERA), "paths": arr(PATH)})


def check(data, schema):
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: str(list(e.path)))
    if errors:
        raise ValueError("\n".join(f"{'/'.join(map(str, e.path)) or '/'}: {e.message}" for e in errors[:15]))


def new_version(number=1, approval=False):
    return {"version": number, "file": None, "production": "planned", "validity": "current",
            "review": {"status": "pending", "note": ""},
            "approval": {"status": "pending" if approval else "not_required", "evidence": ""},
            "prompt": "", "tool": "", "dependencies": [], "gates": [], "note": ""}
