"""Optional firmware build/test adapters; missing toolchains are reported, not faked.

Targets:
  host    CMake + host C compiler: builds firmware/app and runs its unit tests
  stm32   CMake preset stm32-debug: needs STM32CubeMX output + arm-none-eabi-gcc
  arduino PlatformIO environment "uno"

The Arm GNU toolchain is located via ARM_GNU_TOOLCHAIN_BIN, PATH, or standard
install locations; its bin/ is prepended to PATH for the build subprocess only.
STM32CubeMX itself is never required to build (only its generated output).
"""

import glob
import os
from pathlib import Path
import plistlib
import re
import shutil

from tools.core.common import KitError, now, run, write_json

TARGETS = {
    "host": {"tools": ["cmake", "ctest", "cc"],
             "commands": [["cmake", "--preset", "host-tests"], ["cmake", "--build", "--preset", "host-tests"],
                          ["ctest", "--preset", "host-tests"]],
             "requires": "CMakePresets.json"},
    "stm32": {"tools": ["cmake", "arm-none-eabi-gcc"],
              "commands": [["cmake", "--preset", "stm32-debug"], ["cmake", "--build", "--preset", "stm32-debug"]],
              "requires": "CMakePresets.json"},
    "arduino": {"tools": ["pio"], "commands": [["pio", "run", "-e", "uno"]], "requires": "platformio.ini"},
}


def _stale_cmake_cache(fw, preset):
    cache = fw / "build" / preset / "CMakeCache.txt"
    if not cache.is_file():
        return False
    for line in cache.read_text(errors="replace").splitlines():
        if line.startswith("CMAKE_HOME_DIRECTORY:INTERNAL="):
            recorded = Path(line.split("=", 1)[1])
            return not recorded.exists() or recorded.resolve() != fw.resolve()
    return False


ARM_SEARCH = (  # newest version wins within the matches
    "~/Tools/arm-gnu/*/bin",
    "~/.local/toolchains/*/bin",
    "/Applications/ArmGNUToolchain/*/arm-none-eabi/bin",
    "/opt/ST/STM32CubeCLT*/GNU-tools-for-STM32/bin",
    "/Applications/STMicroelectronics/STM32CubeIDE.app/Contents/Eclipse/plugins/*gnu-tools-for-stm32*/tools/bin",
    "/Applications/STM32CubeIDE.app/Contents/Eclipse/plugins/*gnu-tools-for-stm32*/tools/bin",
)
CUBEMX_APPS = ("/Applications/STMicroelectronics/STM32CubeMX.app", "/Applications/STM32CubeMX.app",
               "~/Applications/STMicroelectronics/STM32CubeMX.app")


def _version_key(path):
    return [int(n) for n in re.findall(r"\d+", str(path))]


def arm_toolchain():
    """(bin_dir, source) of arm-none-eabi-gcc, or (None, reason)."""
    configured = os.environ.get("ARM_GNU_TOOLCHAIN_BIN")
    if configured:
        bin_dir = Path(configured).expanduser()
        if (bin_dir / "arm-none-eabi-gcc").is_file():
            return bin_dir, "ARM_GNU_TOOLCHAIN_BIN"
        return None, "ARM_GNU_TOOLCHAIN_BIN=%s does not contain arm-none-eabi-gcc" % configured
    found = shutil.which("arm-none-eabi-gcc")
    if found:
        return Path(found).parent, "PATH"
    candidates = [Path(p) for pattern in ARM_SEARCH for p in glob.glob(os.path.expanduser(pattern))
                  if (Path(p) / "arm-none-eabi-gcc").is_file()]
    if candidates:
        return sorted(candidates, key=_version_key)[-1], "standard location"
    return None, "not on PATH and not in: " + ", ".join(ARM_SEARCH)


def _first_line(argv):
    record = run(argv, timeout=30)
    text = (record["stdout"] or record["stderr"]).strip().splitlines()
    return text[0] if record["exit_code"] == 0 and text else None


def stm32_environment():
    """Read-only inventory of the STM32 tools on this machine."""
    cubemx = next((Path(os.path.expanduser(p)) for p in CUBEMX_APPS if Path(os.path.expanduser(p)).is_dir()), None)
    version = None
    if cubemx and (cubemx / "Contents/Info.plist").is_file():
        with open(cubemx / "Contents/Info.plist", "rb") as fp:
            version = plistlib.load(fp).get("CFBundleShortVersionString")
    repo = Path(os.environ.get("STM32CUBE_REPOSITORY", "~/STM32Cube/Repository")).expanduser()
    packages = sorted(p.name for p in repo.glob("STM32Cube_FW_*") if p.is_dir()) if repo.is_dir() else []
    bin_dir, source = arm_toolchain()
    return {
        "stm32cubemx": {"path": str(cubemx) if cubemx else None, "version": version,
                        "note": "optional: only its generated CMake output is needed to build"},
        "stm32cube_packages": {"repository": str(repo), "packages": packages},
        "arm_gnu_toolchain": {"bin": str(bin_dir) if bin_dir else None, "found_via": source,
                              "version": _first_line([bin_dir / "arm-none-eabi-gcc", "--version"]) if bin_dir else None},
        "cmake": _first_line(["cmake", "--version"]) if shutil.which("cmake") else None,
        "ninja": _first_line(["ninja", "--version"]) if shutil.which("ninja") else None,
        "openocd": _first_line(["openocd", "--version"]) if shutil.which("openocd") else None,
    }


def toolchains():
    found = {tool: shutil.which(tool) for tool in sorted({t for spec in TARGETS.values() for t in spec["tools"]})}
    bin_dir, _ = arm_toolchain()
    if bin_dir:
        found["arm-none-eabi-gcc"] = str(bin_dir / "arm-none-eabi-gcc")
    return found


def elf_report(fw, preset, bin_dir, log):
    """Architecture and size of the linked ELF, read with the cross binutils."""
    elves = sorted((fw / "build" / preset).glob("*.elf"))
    if not elves:
        return {"elf": None}
    elf = elves[0]
    header = run([bin_dir / "arm-none-eabi-readelf", "-h", elf], timeout=60)["stdout"]
    fields = dict(re.findall(r"^\s*(Class|Machine|Flags|Type):\s*(.+?)\s*$", header, re.M))
    size = run([bin_dir / "arm-none-eabi-size", elf], timeout=60)["stdout"].split()
    sizes = dict(zip(size[:3], (int(v) for v in size[6:9]))) if len(size) >= 9 else {}
    usage = re.findall(r"^\s*(FLASH|RAM|CCMRAM|SRAM\w*):\s+(\S+ \S+)\s+(\S+ \S+)\s+([\d.]+%)", log, re.M)
    return {"elf": str(elf), "bytes": elf.stat().st_size, "elf_header": fields, "size": sizes,
            "memory_usage": [{"region": r, "used": u, "size": t, "percent": p} for r, u, t, p in usage]}


def build(root, target="host"):
    if target not in TARGETS:
        raise KitError("Unknown firmware target %r (host, stm32, arduino)." % target)
    root = Path(root).resolve()
    fw = root / "firmware"
    spec = TARGETS[target]
    if not (fw / spec["requires"]).is_file():
        raise KitError("No firmware/%s in this project; the %s target is not configured (the Generic PCB "
                       "template has no firmware)." % (spec["requires"], target), 17)
    env, bin_dir = None, None
    missing = [t for t in spec["tools"] if t != "arm-none-eabi-gcc" and not shutil.which(t)]
    if "arm-none-eabi-gcc" in spec["tools"]:
        bin_dir, source = arm_toolchain()
        if bin_dir:
            env = {"PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", "")}
        else:
            missing.append("arm-none-eabi-gcc (%s; install the Arm GNU Toolchain or set ARM_GNU_TOOLCHAIN_BIN)"
                           % source)
    result = {"target": target, "at": now(), "commands": [], "missing_tools": missing,
              "toolchain_bin": str(bin_dir) if bin_dir else None}
    if missing:
        result["status"] = "MISSING_TOOLCHAIN"
    else:
        commands = [list(c) for c in spec["commands"]]
        if commands[0][:2] == ["cmake", "--preset"] and _stale_cmake_cache(fw, commands[0][2]):
            # The project was moved or copied: CMake caches absolute source paths in the
            # generated build tree, so reconfigure from scratch (CMake >= 3.24).
            commands[0].append("--fresh")
            result["reconfigured_after_relocation"] = True
        for command in commands:
            record = run(command, cwd=fw, timeout=900, env=env)
            result["commands"].append(record)
            if record["exit_code"]:
                break
        result["status"] = "PASS" if all(r["exit_code"] == 0 for r in result["commands"]) else "FAIL"
        if target == "stm32" and result["status"] == "PASS":
            log = "".join(r["stdout"] for r in result["commands"])
            result["artifact"] = elf_report(fw, "stm32-debug", bin_dir, log)
    write_json(root / "qa/generated/firmware" / (target + ".json"), result)
    if result["status"] == "MISSING_TOOLCHAIN":
        raise KitError("Firmware target %s needs: %s (not found on PATH)." % (target, ", ".join(missing)), 17)
    return result
