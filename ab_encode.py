import os
import subprocess
import re
import argparse
import pprint
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# --- CONFIGURATION ---
EXTENSIONS = ('.mp3', '.wav', '.flac', '.m4a', '.ogg')

def natural_sort_key(s):
    """Ensures files sort like: 1, 2, 3... 10"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def verify_audio(file_path):
    """Industry Standard: Uses ffprobe to check if the audio file is structurally valid."""
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return False

    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", file_path]
    try:
        # If ffprobe returns an error code or empty output, the file is corrupt.
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return float(result.stdout.strip()) > 0
    except (subprocess.CalledProcessError, ValueError):
        return False

def process_folder(root, bitrate, channels, cleanup):
    raw_files = [f for f in os.listdir(root) if f.lower().endswith(EXTENSIONS)]
    source_files = sorted(raw_files, key=natural_sort_key)

    if not source_files or any(f.lower().endswith('.m4b') for f in os.listdir(root)):
        return {"status": "⏩ Skipped (Empty/M4B Exists)", "folder": root}

    folder_name = os.path.basename(root)
    output_path = os.path.join(root, f"{folder_name}.m4b")
    list_file = os.path.join(root, f"list_{folder_name}.txt")

    # Safely Generate Concat List
    with open(list_file, "w") as f:
        for audio in source_files:
            abs_path = os.path.abspath(os.path.join(root, audio))
            safe_path = abs_path.replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c:a", "aac", "-b:a", bitrate, "-ac", channels,
        "-ar", "44100", "-metadata", f"title={folder_name}",
        "-movflags", "+faststart", output_path
    ]

    try:
        subprocess.run(cmd, check=True)

        # --- VERIFICATION & CLEANUP ---
        if verify_audio(output_path):
            if cleanup:
                for audio in source_files:
                    os.remove(os.path.join(root, audio))
                return {"status": "✅ Success & Sources Deleted", "folder": folder_name}
            return {"status": "✅ Success (Sources Kept)", "folder": folder_name}
        else:
            return {"status": "⚠️ Verification Failed", "folder": folder_name}

    except subprocess.CalledProcessError:
        return {"status": "❌ Encoding Error", "folder": folder_name}
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)

def main():
    parser = argparse.ArgumentParser(
        description="🎧 Audiobook M4B Builder with Auto-Verification & Cleanup.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("directory", help="Target root directory containing audiobook folders.")
    parser.add_argument("-b", "--bitrate", type=str, default="64k", help="Target bitrate (e.g., 64k, 128k).")
    parser.add_argument("-c", "--channels", type=str, default="1", choices=["1", "2"], help="Audio channels (1=Mono, 2=Stereo).")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Number of concurrent CPU workers.")
    parser.add_argument("--cleanup", action="store_true", help="⚠️ DANGER: Delete original audio files after successful verification.")

    args = parser.parse_args()

    target_dir = os.path.abspath(args.directory)
    if not os.path.isdir(target_dir):
        print(f"❌ Error: Directory '{target_dir}' does not exist.")
        return

    tasks = []
    for root, dirs, files in os.walk(target_dir):
        if any(f.lower().endswith(EXTENSIONS) for f in files):
            tasks.append(root)

    print(f"🚀 Processing on:\n📂 {target_dir}")
    print(f"⚙️ Workers: {args.workers} | Auto-Cleanup: {'ON ⚠️' if args.cleanup else 'OFF'}")

    worker_func = partial(process_folder, bitrate=args.bitrate, channels=args.channels, cleanup=args.cleanup)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(worker_func, tasks))

    # --- PPRINT SUMMARY REPORT ---
    summary = {}
    for res in results:
        status = res["status"]
        if status not in summary:
            summary[status] = []
        summary[status].append(res["folder"])

    print("\n📊 FINAL EXECUTION REPORT:")
    print("-" * 30)
    pp = pprint.PrettyPrinter(indent=4, width=80)
    pp.pprint(summary)

if __name__ == "__main__":
    main()
