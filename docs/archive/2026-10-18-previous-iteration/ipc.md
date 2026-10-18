# IPC setup and diagnostics

Install the optional client through `scripts/install-environment.sh`, then use
that environment with `KICAD_KIT_PYTHON` or run its Python directly:

```sh
"$HOME/Library/Application Support/PCB-Project-Template/venv/bin/python" tools/kit.py ipc
```

Enable KiCad's API server in PCB Editor Preferences (Plugins > Enable KiCad API), open a board,
and use the socket for that instance. For a plugin launched by KiCad,
`KICAD_API_SOCKET` and `KICAD_API_TOKEN` identify the server. For a standalone
client, set the socket environment variable to the actual active socket if
standard discovery cannot locate it. Do not put tokens in source files or reports.

`tools/ipc.py` imports the optional `kipy` client, performs `ping()` and requests
both the connected server version and client API version. It runs in a bounded
subprocess. Merely importing the package or reading the client API version does
not count as contacting KiCad. `CONNECTED` requires the live calls to succeed;
missing packages, refused connections and timeouts return `UNAVAILABLE` and
exit code 3. No design mutation occurs. The CLI version check is independent of
the server version; inspect the reported server when multiple installations run.

The tested optional package baseline is `kicad-python==0.8.0`. Its import is
`kipy`, not `pcbnew`. Legacy action plugins use KiCad's bundled Python and SWIG
bindings; installing an IPC client does not change that interpreter. Default
CLI verification needs neither IPC nor a running editor.

References: [KiCad IPC addon guide](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/),
[Python API](https://docs.kicad.org/kicad-python/kicad.html),
[client package](https://pypi.org/project/kicad-python/0.8.0/).
