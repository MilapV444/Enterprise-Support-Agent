import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADP_ROOT = os.path.join(ROOT, "docs", "decisions", "adp")

COMPONENT_DIRS = {
    "ADP": "00-orchestration-core",
    "UA": "01-user-application",
    "KR": "02-knowledge-retrieval",
    "MS": "03-memory-state",
    "TA": "04-tools-actions",
    "MA": "05-multi-agent-communication",
    "SG": "06-safety-security-governance",
    "DP": "07-data-persistence",
    "EV": "08-evaluation-experimentation",
    "OB": "09-observability-monitoring",
    "RP": "10-reliability-performance-scale",
    "CR": "11-cost-resource-management",
    "HL": "12-human-in-the-loop",
    "TQ": "13-testing-quality",
    "DL": "14-deployment-llmops",
    "CI": "15-continuous-improvement",
}


def organize():
    # 1. Map files to target directories
    files = [f for f in os.listdir(ADP_ROOT) if f.endswith(".md") and os.path.isfile(os.path.join(ADP_ROOT, f))]
    print(f"Found {len(files)} files directly in {ADP_ROOT}")

    if len(files) == 0:
        print("No files to move in root of ADP directory. They may already be moved.")
        return

    # Create target directories
    for d in COMPONENT_DIRS.values():
        os.makedirs(os.path.join(ADP_ROOT, d), exist_ok=True)

    file_mapping = {}
    for f in files:
        prefix = f.split("-")[0]
        if prefix not in COMPONENT_DIRS:
            raise ValueError(f"Unknown prefix for file {f}")
        file_mapping[f] = COMPONENT_DIRS[prefix]

    # 2. Move files
    for fname, target_dir in file_mapping.items():
        src = os.path.join(ADP_ROOT, fname)
        dst = os.path.join(ADP_ROOT, target_dir, fname)
        shutil.move(src, dst)
        print(f"Moved {fname} -> {target_dir}/")

    print(f"All {len(files)} files moved successfully.")

    # 3. Update references inside all moved markdown files
    total_replacements = 0
    all_moved_files = []
    for root, dirs, fnames in os.walk(ADP_ROOT):
        for fn in fnames:
            if fn.endswith(".md"):
                all_moved_files.append(os.path.join(root, fn))

    for filepath in all_moved_files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        updated_content = content
        for fname, target_dir in file_mapping.items():
            # Old link patterns
            old_str1 = f"docs/decisions/adp/{fname}"
            new_str1 = f"docs/decisions/adp/{target_dir}/{fname}"
            if old_str1 in updated_content:
                updated_content = updated_content.replace(old_str1, new_str1)
                total_replacements += 1

            old_str2 = f"docs%2Fdecisions%2Fadp%2F{fname}"
            new_str2 = f"docs%2Fdecisions%2Fadp%2F{target_dir}%2F{fname}"
            if old_str2 in updated_content:
                updated_content = updated_content.replace(old_str2, new_str2)
                total_replacements += 1

        if updated_content != content:
            with open(filepath, "w", encoding="utf-8", newline="\n") as f:
                f.write(updated_content)

    print(f"Updated references inside ADP markdown files: {total_replacements} replacements made.")


if __name__ == "__main__":
    organize()
