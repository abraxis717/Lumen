import yaml
import hashlib
import os

def load_pack(path: str):
    with open(f"{path}/manifest.yaml") as f:
        manifest = yaml.safe_load(f)
    # hash verification stub — implement full later
    print("HCPF loaded:", manifest["pack_name"])
    return manifest
