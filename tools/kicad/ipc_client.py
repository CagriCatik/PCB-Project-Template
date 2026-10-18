"""KiCad IPC client session (requires kicad-python; runs in the kit venv).

Run as ``python -m tools.kicad.ipc_client --socket ipc:///tmp/kicad/api.sock`` to
print one JSON probe result. The parent process (tools/kicad/ipc.py) bounds it with a
timeout so a hung socket can never block the CLI. All queries are read-only.
"""

import argparse
import json
import sys


class IpcSession:
    """Connection lifecycle around kipy.KiCad: connect, validate, query, close."""

    def __init__(self, socket_path=None, timeout_ms=3000, client_name="pcb-project-template"):
        self.socket_path = socket_path
        self.timeout_ms = timeout_ms
        self.client_name = client_name
        self.kicad = None

    def __enter__(self):
        from kipy import KiCad

        kwargs = {"timeout_ms": self.timeout_ms, "client_name": self.client_name}
        if self.socket_path:
            kwargs["socket_path"] = self.socket_path
        self.kicad = KiCad(**kwargs)
        self.kicad.ping()  # connection validation before any query
        return self

    def __exit__(self, *exc):
        client = getattr(self.kicad, "_client", None)
        conn = getattr(client, "_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        self.kicad = None
        return False

    def versions(self):
        return {"server": str(self.kicad.get_version()), "client_api": str(self.kicad.get_api_version())}

    def open_documents(self):
        from kipy.proto.common.types import DocumentType

        docs = {}
        for label, kind in (("project", DocumentType.DOCTYPE_PROJECT), ("schematic", DocumentType.DOCTYPE_SCHEMATIC),
                            ("pcb", DocumentType.DOCTYPE_PCB)):
            try:
                docs[label] = [_doc(d) for d in self.kicad.get_open_documents(kind)]
            except Exception as exc:  # editors not open answer with an API error
                docs[label] = {"error": _describe(exc)}
        return docs

    def board_info(self):
        board = self.kicad.get_board()
        info = {"name": getattr(board, "name", None)}
        for key, call in (
            ("footprints", lambda: len(board.get_footprints())),
            ("nets", lambda: len(board.get_nets())),
            ("tracks", lambda: len(board.get_tracks())),
            ("vias", lambda: len(board.get_vias())),
            ("zones", lambda: len(board.get_zones())),
            ("copper_layers", board.get_copper_layer_count),
        ):
            try:
                info[key] = call()
            except Exception as exc:
                info[key] = {"error": _describe(exc)}
        try:
            tb = board.get_title_block_info()
            info["title_block"] = {"title": tb.title, "revision": tb.revision, "date": tb.date}
        except Exception as exc:
            info["title_block"] = {"error": _describe(exc)}
        return info


def _doc(spec):
    out = {"type": int(getattr(spec, "type", 0))}
    for field in ("board_filename",):
        if getattr(spec, field, ""):
            out[field] = getattr(spec, field)
    project = getattr(spec, "project", None)
    if project is not None:
        out["project"] = {"name": getattr(project, "name", ""), "path": getattr(project, "path", "")}
    return out


def _describe(exc):
    return "%s: %s" % (type(exc).__name__, exc)


def classify(exc):
    name = type(exc).__name__
    text = str(exc).lower()
    if name == "ConnectionError" or "connection refused" in text or "timed out" in text:
        return "connection_failed"
    if name == "ApiError":
        return "api_error"
    if name == "FutureVersionError":
        return "version_mismatch"
    return "unexpected_error"


def probe(socket_path=None, timeout_ms=3000, include_board=True):
    result = {"socket": socket_path, "reachable": False}
    try:
        import kipy  # noqa: F401
        import importlib.metadata

        result["client_package"] = "kicad-python " + importlib.metadata.version("kicad-python")
    except ImportError:
        result.update({"error_class": "client_missing", "error": "kicad-python is not installed in " + sys.executable})
        return result
    try:
        with IpcSession(socket_path, timeout_ms) as session:
            result["reachable"] = True
            result["versions"] = session.versions()
            result["documents"] = session.open_documents()
            if include_board:
                try:
                    result["board"] = session.board_info()
                except Exception as exc:
                    result["board"] = {"error": _describe(exc), "error_class": classify(exc)}
    except Exception as exc:
        result.update({"error": _describe(exc), "error_class": classify(exc)})
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--socket")
    parser.add_argument("--timeout-ms", type=int, default=3000)
    parser.add_argument("--no-board", action="store_true")
    args = parser.parse_args()
    print(json.dumps(probe(args.socket, args.timeout_ms, not args.no_board)))
