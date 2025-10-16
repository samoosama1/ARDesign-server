import os


def scan_and_print_files(root_dir):
    """
    Recursively scans a directory for .py and .html files and prints their
    path and content.

    Args:
        root_dir (str): The path to the root directory to start scanning from.
    """
    # Check if the provided root directory exists
    if not os.path.isdir(root_dir):
        print(f"Error: Directory '{root_dir}' not found.")
        return

    print(f"--- Starting scan in directory: {os.path.abspath(root_dir)} ---\n")

    # os.walk generates the file names in a directory tree
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            # Check if the file has a .py or .html extension
            if filename == 'script.py':
                continue
            if filename.endswith(('.py', '.html')):
                file_path = os.path.join(dirpath, filename)

                print("=" * 80)
                print(f"Path: {file_path}")
                print("-" * 80)

                try:
                    # Open and read the file's content
                    # Using utf-8 encoding and ignoring errors for robustness
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        print(content)
                except Exception as e:
                    print(f"!!! An error occurred while reading the file: {e} !!!")

                print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    # --- CONFIGURATION ---
    # Set the root folder you want to scan.
    # To scan the directory where the script is located, use '.'
    # To scan a different directory, replace '.' with the full path,
    # e.g., "C:/Users/YourUser/Documents" or "/home/user/projects"
    root_folder_to_scan = '.'

    scan_and_print_files(root_folder_to_scan)
