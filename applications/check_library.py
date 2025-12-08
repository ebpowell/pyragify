import sys
from pathlib import Path

# Add src to sys.path to ensure we can import the package
sys.path.append(str(Path(__file__).parents[1] / "src"))

from pyragify.processor import RepoContentProcessor


from pyragify.powerbi_processor import pbi_processor

if __name__ == "__main__":
    # repo_path = Path(sys.argv[1])
    # output_dir = Path(sys.argv[2])
    repo_path = Path('/home/ebpowell/GIT_REPO/ai_bi_code')
    output_dir = Path('/home/ebpowell/GIT_REPO/ai_bi_code/output')
    hashes_file = output_dir / "hashes.json"
    if hashes_file.exists():
        hashes_file.unlink()
    skip_folders = [".venv", "venv", "build", "dist", "__pycache__",".idea", ".git", "output"]
    skip_patterns = ["**/*.pyc", "**/__pycache__", "**/venv", "**/.venv"]
    
    # Use pbi_processor to handle PowerBI files
    processor = RepoContentProcessor(repo_path, output_dir, skip_patterns=skip_patterns, skip_dirs=skip_folders, processor_class=pbi_processor)
    processor.process_repo()
