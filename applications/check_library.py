import sys
from pathlib import Path

# 1. Get the path to the 'applications' folder (where this script is)
current_dir = Path(__file__).resolve().parent

# 2. Go up one level to the Project Root, then into 'src'
#    Structure: applications/ -> (up) -> Root -> (down) -> src
src_path = current_dir.parent / "src/pyragify"

# 3. Add this path to sys.path so Python looks there for modules
sys.path.append(str(src_path))

from processor import RepoContentProcessor
from pyragify.powerbi_processor import pbi_processor

if __name__ == "__main__":
    # repo_path = Path(sys.argv[1])
    # output_dir = Path(sys.argv[2])
<<<<<<< HEAD
    home_folder = '/home/ebpowell/GIT_REPO/'
    repo_name ='ABWC/ABWC_Transitions/Model'
    repo_path = Path(home_folder + repo_name)
    output_dir = Path(home_folder + repo_name + '/output')
=======
    repo_path = Path('/home/ebpowell/GIT_REPO/ABWC/ABWC Transitions/Model')
    output_dir = Path('/home/ebpowell/GIT_REPO//ABWC/ABWC Transitions/output')
>>>>>>> fbf2080 (I changes something)
    hashes_file = output_dir / "hashes.json"
    if hashes_file.exists():
        hashes_file.unlink()
    skip_folders = [".venv", "venv", "build", "dist", "__pycache__",".idea", ".git", "output"]
    skip_patterns = ["**/*.pyc", "**/__pycache__", "**/venv", "**/.venv"]
    
    # Use pbi_processor to handle PowerBI files
    processor = RepoContentProcessor(repo_path, output_dir, skip_patterns=skip_patterns, skip_dirs=skip_folders, processor_class=pbi_processor)
    processor.process_repo()