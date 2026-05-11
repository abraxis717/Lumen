#!/usr/bin/env python3
"""Vault – plugin-based system for managing AI components.

Usage:
    python vault.py list
    python vault.py validate <plugin-name>
    python vault.py compile
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

VAULT_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = VAULT_DIR / "plugins"
OUTPUT_DIR = PLUGINS_DIR / "compiler-output"

REQUIRED_FIELDS = {"name", "type", "version", "description", "dependencies", "status"}
VALID_TYPES = {"model", "proxy", "tool", "hook", "other"}


def discover_plugins():
    """Scan plugins/ directory and return {name: data} dict."""
    plugins = {}
    if not PLUGINS_DIR.is_dir():
        return plugins
    for entry in sorted(os.scandir(PLUGINS_DIR), key=lambda e: e.name):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        vj = Path(entry.path) / "vault.json"
        if not vj.is_file():
            continue
        try:
            with open(vj, "r") as f:
                data = json.load(f)
            data["_dir"] = entry.path
            plugins[data["name"]] = data
        except (json.JSONDecodeError, KeyError) as exc:
            print(f"  WARNING: could not load {entry.name}: {exc}", file=sys.stderr)
    return plugins


def load_plugin(name):
    """Load a single plugin by name."""
    plugins = discover_plugins()
    if name not in plugins:
        return None, f"Plugin '{name}' not found (known: {', '.join(sorted(plugins.keys()))})"
    return plugins[name], None


# ------------------------------------------------------------------ #
#  LIST
# ------------------------------------------------------------------ #

def cmd_list(args):
    plugins = discover_plugins()
    if not plugins:
        print("No plugins found.")
        return

    # Header
    header = f"{'NAME':<24} {'TYPE':<10} {'VERSION':<10} {'STATUS':<10} {'DEPS'}"
    print(header)
    print("-" * len(header))

    for name in sorted(plugins):
        p = plugins[name]
        deps = ", ".join(p.get("dependencies") or []) or "—"
        print(f"{name:<24} {p.get('type','?'):<10} {p.get('version','?'):<10} {p.get('status','?'):<10} {deps}")

    print(f"\nTotal: {len(plugins)} plugin(s)")


# ------------------------------------------------------------------ #
#  VALIDATE
# ------------------------------------------------------------------ #

def cmd_validate(args):
    name = args.name
    plugin, err = load_plugin(name)
    if err:
        print(f"ERROR: {err}")
        sys.exit(1)

    issues = []
    pdir = plugin["_dir"]

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in plugin:
            issues.append(f"Missing required field: '{field}'")

    # Type check
    if plugin.get("type") not in VALID_TYPES:
        issues.append(f"Invalid type '{plugin.get('type')}' — expected one of {sorted(VALID_TYPES)}")

    # Activation block (optional but if present should have command)
    if "activation" in plugin:
        if "command" not in plugin["activation"]:
            issues.append("activation block present but missing 'command'")

    # Provided files (e.g. model_path)
    provides = plugin.get("provides", {}) or {}
    for key in ("model_path",):
        val = provides.get(key)
        if val and not os.path.isfile(val):
            issues.append(f"'provides.{key}' references non-existent file: {val}")

    # Dependencies exist in the plugins directory
    all_names = discover_plugins().keys()
    for dep in plugin.get("dependencies", []) or []:
        if dep not in all_names:
            issues.append(f"Dependency '{dep}' not found in plugins directory")

    if issues:
        print(f"Plugin '{name}': FAILED ({len(issues)} issue(s))")
        for i in issues:
            print(f"  - {i}")
        sys.exit(1)
    else:
        print(f"Plugin '{name}': OK")
        print(f"  type={plugin.get('type')}  version={plugin.get('version')}  status={plugin.get('status')}")
        deps = plugin.get("dependencies") or []
        if deps:
            print(f"  depends on: {', '.join(deps)}")
        if provides:
            print(f"  provides: {json.dumps(provides, indent=6)}")


# ------------------------------------------------------------------ #
#  COMPILE  (topological sort + script generation)
# ------------------------------------------------------------------ #

def topological_sort(active_plugins):
    """Kahn's algorithm. Returns ordered list of plugin names or raises on cycle."""
    in_degree = {name: 0 for name in active_plugins}
    adj = {name: [] for name in active_plugins}

    for name, data in active_plugins.items():
        for dep in (data.get("dependencies") or []):
            if dep in active_plugins:
                adj[dep].append(name)
                in_degree[name] += 1

    queue = [n for n in active_plugins if in_degree[n] == 0]
    queue.sort()  # deterministic tie-break
    order = []

    while queue:
        node = queue.pop(0)
        order.append(node)
        for neighbour in sorted(adj[node]):
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    if len(order) != len(active_plugins):
        remaining = set(active_plugins) - set(order)
        raise ValueError(f"Circular dependency detected among: {sorted(remaining)}")
    return order


def cmd_compile(args):
    all_plugins = discover_plugins()
    if not all_plugins:
        print("No plugins found to compile.")
        return

    # Separate active / inactive
    active = {n: d for n, d in all_plugins.items() if d.get("status") == "active"}
    inactive = {n: d for n, d in all_plugins.items() if d.get("status") != "active"}

    if inactive:
        print(f"Skipping inactive plugin(s): {', '.join(sorted(inactive))}")

    if not active:
        print("No active plugins to compile.")
        return

    # Validate each active plugin first
    print("Validating active plugins …")
    for name in sorted(active):
        plugin, err = load_plugin(name)
        if err:
            print(f"  {name}: SKIPPED ({err})")
            sys.exit(1)
        issues = []
        provides = plugin.get("provides", {}) or {}
        for key in ("model_path",):
            val = provides.get(key)
            if val and not os.path.isfile(val):
                issues.append(f"'provides.{key}' not found: {val}")
        for dep in (plugin.get("dependencies") or []):
            if dep not in all_plugins:
                issues.append(f"Dependency '{dep}' not found")
            elif all_plugins[dep].get("status") != "active":
                issues.append(f"Dependency '{dep}' is inactive")
        if issues:
            print(f"  {name}: FAILED")
            for i in issues:
                print(f"    - {i}")
            sys.exit(1)
        print(f"  {name}: OK")

    # Topological sort
    order = topological_sort(active)
    print(f"\nDependency order: {' → '.join(order)}")

    # Ensure output dir exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- start_all.sh ----
    sh_lines = [
        "#!/usr/bin/env bash",
        "# Auto-generated by vault.py compile",
        f"# Date: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"# Plugins: {len(order)} active",
        "set -euo pipefail",
        "",
        'echo "=== Vault: launching plugins in dependency order ==="',
        "",
    ]

    for i, name in enumerate(order):
        plugin = active[name]
        cmd = plugin.get("activation", {}).get("command", "")
        env = plugin.get("activation", {}).get("env", {})
        sh_lines.append(f"# --- {name} ({plugin.get('type')}) ---")

        for env_var, env_val in (env or {}).items():
            if env_val == "":
                sh_lines.append(f'export {env_var}=""')
            else:
                sh_lines.append(f'export {env_var}="{env_val}"')

        sh_lines.append(f'nohup {cmd} >> "{OUTPUT_DIR}/{name}.log" 2>&1 &')
        sh_lines.append(f'echo "  started: {name} (PID: $!)"')
        sh_lines.append(f"sleep 3")
        sh_lines.append("")

    sh_lines.append('echo "=== All plugins started ==="')
    sh_lines.append("")

    sh_path = OUTPUT_DIR / "start_all.sh"
    sh_path.write_text("\n".join(sh_lines) + "\n")
    sh_path.chmod(0o755)
    print(f"\nGenerated: {sh_path}")

    # ---- hermes_config.yaml ----
    yaml_lines = [
        "# Auto-generated by vault.py compile",
        f"# Date: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "# Include this snippet in your ~/.hermes/config.yaml or merge it manually.",
        "",
        "provider: custom",
        "custom_providers:",
    ]

    for name in order:
        plugin = active[name]
        provides = plugin.get("provides", {}) or {}
        base_url = provides.get("base_url", "")
        model_name = provides.get("model_path", "").split("/")[-1].replace(".gguf", "") or name
        context_len = provides.get("context_length")

        yaml_lines.append(f"  - name: {name}")
        yaml_lines.append(f"    type: {plugin.get('type', 'model')}")
        yaml_lines.append(f"    base_url: \"{base_url}\"")
        yaml_lines.append(f"    model: \"{name}\"")
        if context_len is not None:
            yaml_lines.append(f"    context_length: {context_len}")
        yaml_lines.append("")

    cfg_path = OUTPUT_DIR / "hermes_config.yaml"
    cfg_path.write_text("\n".join(yaml_lines) + "\n")
    print(f"Generated: {cfg_path}")

    print("\nDone. Review the generated files before launching.")


# ------------------------------------------------------------------ #
#  CLI entry point
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(description="Vault – AI component plugin manager")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all plugins and their status")

    val_p = sub.add_parser("validate", help="Validate a single plugin")
    val_p.add_argument("name", help="Plugin name to validate")

    sub.add_parser("compile", help="Compile active plugins into launch script + config")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "compile":
        cmd_compile(args)


if __name__ == "__main__":
    main()
