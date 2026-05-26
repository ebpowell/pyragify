import sys
from pathlib import Path

# 1. Get the path to the 'applications' folder (where this script is)
current_dir = Path(__file__).resolve().parent

# 2. Go up one level to the Project Root, then into 'src'
#    Structure: applications/ -> (up) -> Root -> (down) -> src
src_path = current_dir.parent / "src/pyragify"

# 3. Add this path to sys.path so Python looks there for modules
sys.path.append(str(src_path))
# import cli:app
from processor import RepoContentProcessor, FileProcessor

if __name__ == "__main__":
    # repo_folder = '/mnt/c/Users/uvp/'
    repo_folder = '/home/ebpowell/GIT_REPO/'
    repo_name = 'itsd_capacity_planning'
    repo_path = Path(repo_folder + repo_name)
    output_dir = Path(repo_folder + '/output/'+repo_name)
    hashes_file = output_dir / "hashes.json"
    if hashes_file.exists():
        hashes_file.unlink()
    skip_folders = [".venv", "venv", "build", "dist", "__pycache__", ".idea", ".git", "output"]
    skip_patterns = ["**/*.pyc", "**/__pycache__", "**/venv", "**/.venv"]

    processor = RepoContentProcessor(repo_path, output_dir, skip_patterns=skip_patterns, skip_dirs=skip_folders,
                                     processor_class=FileProcessor)
    processor.process_repo()
    # cli:app()